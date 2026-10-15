"""Explicit private replacement maps; old quotes/reviews are never inherited."""

from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator
from rdflib import URIRef

from .db import digest
from .evidence_prompt import canonical
from .practice import StrictInput

RECIPE = 'private-source-context-renewal-v1'
MAX_DEPTH = 8
EVIDENCE_KEYS = ('passage_id', 'source_version_id', 'document_id', 'quote_sha256',
                 'source_sha256', 'text_sha256', 'locator_map_sha256', 'start_offset', 'end_offset', 'offset_unit')


class Mapping(StrictInput):
    parent_passage_id: str = Field(min_length=1, max_length=512)
    new_passage_ids: list[str] = Field(max_length=8)
    disposition: Literal['retained', 'replaced', 'omitted', 'unresolved']
    note: str = Field(min_length=3, max_length=1000)

    @model_validator(mode='after')
    def explained(self):
        if (len(self.note.strip()) < 3 or len(set(self.new_passage_ids)) != len(self.new_passage_ids)
                or any(not 1 <= len(item) <= 512 for item in self.new_passage_ids)
                or (self.disposition in {'retained', 'replaced'} and not self.new_passage_ids)
                or (self.disposition == 'omitted' and self.new_passage_ids)):
            raise ValueError('Explain each distinct replacement or omission')
        return self


class Renewal(StrictInput):
    parent_context_id: str = Field(pattern=r'^sac-[a-f0-9]{20}-[a-f0-9]{32}$')
    expected_parent_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_parent_review_id: str | None = Field(default=None, min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=2000)
    mappings: list[Mapping] = Field(min_length=1, max_length=8)
    added_passage_ids: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def complete(self):
        if (len(self.reason.strip()) < 3
                or len({item.parent_passage_id for item in self.mappings}) != len(self.mappings)
                or len(set(self.added_passage_ids)) != len(self.added_passage_ids)
                or any(not 1 <= len(item) <= 512 for item in self.added_passage_ids)):
            raise ValueError('Declare every distinct parent and added source')
        return self


class Assessment(StrictInput):
    expected_comparison_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    outcome: Literal['confirmed', 'needs_change', 'not_assessed']
    note: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def explained(self):
        if len(self.note.strip()) < 3:
            raise ValueError('Explain the independent replacement assessment')
        return self


def parent(store, session, matter_id, analysis_id, renewal, user):
    # Local import avoids routing/module initialization cycles.
    from . import source_analysis_reviews as reviews

    renewal = Renewal.model_validate(renewal)
    _, packet, _, proof = reviews._require(store, session, matter_id, analysis_id, renewal.parent_context_id, user)
    head = reviews._head(store, session, matter_id, analysis_id, renewal.parent_context_id, user)
    review_id = head['latest_review_id'] if head else None
    if (not proof.get('guard_completed') or packet['manifest_sha256'] != renewal.expected_parent_manifest_sha256
            or review_id != renewal.expected_parent_review_id):
        raise HTTPException(409, 'Önceki bağlamın tam kayıt veya inceleme bağı değişti; yenilemeyi tekrar açın.')
    if head:
        _, _, _, review_proof = reviews._require(store, session, matter_id, analysis_id, review_id, user,
            review=True, context_id=renewal.parent_context_id)
        if not review_proof.get('guard_completed'):
            raise HTTPException(409, 'Önceki incelemenin son izin kontrolü bekleniyor; geçmiş kayıt yenilenemez.')
    depth = packet['manifest'].get('renewal_comparison', {}).get('depth', 0) + 1
    if depth > MAX_DEPTH:
        raise HTTPException(409, 'Sekiz bağlı yenileme sınırına ulaşıldı; ayrı bir kaynak seçimi gerekli.')
    return packet, review_id, depth


def metadata(store, session, matter_id, analysis_id, context_id, user):
    from . import source_analysis_reviews as reviews

    _, packet, _, proof = reviews._require(store, session, matter_id, analysis_id, context_id, user)
    head = reviews._head(store, session, matter_id, analysis_id, context_id, user)
    manifest = packet['manifest']
    return {'id': context_id, 'manifest_sha256': packet['manifest_sha256'],
        'matter_id': matter_id, 'analysis_id': analysis_id,
        'review_id': head['latest_review_id'] if head else None, 'admission_completed': bool(proof.get('guard_completed')),
        'version_id': manifest['version_id'], 'product_id': manifest['product_id'],
        'graph_release_pin': manifest['graph_release_pin'], 'recorded_by': packet['recorded_by'],
        'sources': [{'identity': {key: source['evidence'][key] for key in EVIDENCE_KEYS},
            'targets': {key: digest(canonical(value)) for key, value in source['target_snapshots'].items()}}
            for source in manifest['sources']],
        'old_quotes_and_notes': 'withheld_use_original_guarded_context',
        'review_inheritance': 'none', 'legal_equivalence': 'not_assessed'}


def retained_sources(app, session, matter_id, analysis_id, renewal, user):
    """Retained evidence keeps the original whole-release guard, sequentially.

    Replacement/omission metadata cannot authorize old quotes or dependencies.
    Never nest the original guard inside the new research guard.
    """
    from . import analysis_authorities as authorities
    from .source_corpus import _project

    renewal = Renewal.model_validate(renewal)
    retained = {row.parent_passage_id for row in renewal.mappings if row.disposition == 'retained'}
    if not retained:
        return
    packet, _, _ = parent(app.state.store, session, matter_id, analysis_id, renewal, user)
    manifest = packet['manifest']
    with authorities._guard(app, {'snapshots': {'graph_release_pin': manifest['graph_release_pin']}}):
        for source in manifest['sources']:
            if source['evidence']['passage_id'] in retained:
                current = _project(app.state.graph.release, URIRef(source['evidence']['passage_id']))
                if any(current[key] != source['evidence'][key] for key in EVIDENCE_KEYS):
                    raise HTTPException(409, 'Saklanan özgün pasaj değişti; aynı sürüm yerine geçirilemez.')


def comparison(store, session, matter_id, analysis_id, renewal, manifest, user):
    renewal = Renewal.model_validate(renewal)
    packet, review_id, depth = parent(store, session, matter_id, analysis_id, renewal, user)
    return comparison_from_parent(renewal, manifest, packet, review_id, depth)


def comparison_from_parent(renewal, manifest, packet, review_id, depth):
    """Rebuild one immutable link; caller separately authenticates both packets."""
    previous = packet['manifest']
    old = {source['evidence']['passage_id']: source for source in previous['sources']}
    new = {source['evidence']['passage_id']: source for source in manifest['sources']}
    linked = {ident for row in renewal.mappings for ident in row.new_passage_ids}
    added = set(renewal.added_passage_ids)
    if ({row.parent_passage_id for row in renewal.mappings} != set(old)
            or linked & added or linked | added != set(new)):
        raise HTTPException(422, 'Her önceki kaynak ve her yeni seçim açıkça eşlenmeli veya ayrı açıklanmalıdır.')
    entries = []
    for row in renewal.mappings:
        before = old[row.parent_passage_id]
        identity = {key: before['evidence'][key] for key in EVIDENCE_KEYS}
        old_targets = {key: digest(canonical(value)) for key, value in before['target_snapshots'].items()}
        successors = []
        for ident in row.new_passage_ids:
            after = new[ident]
            new_identity = {key: after['evidence'][key] for key in EVIDENCE_KEYS}
            targets = {key: digest(canonical(value)) for key, value in after['target_snapshots'].items()}
            successors.append({'identity': new_identity, 'targets': targets,
                'exact_evidence_same': identity == new_identity,
                'exact_targets_same': old_targets == targets})
        if row.disposition == 'retained' and (len(successors) != 1 or not successors[0]['exact_evidence_same']):
            raise HTTPException(422, 'Saklanan kaynak beyanı aynı tam pasaj, sürüm, bayt özeti ve konumu gerektirir.')
        entries.append({'parent_identity': identity, 'parent_targets': old_targets,
            'disposition': row.disposition, 'note': row.note, 'successors': successors})
    return {'recipe': RECIPE, 'depth': depth, 'parent_context_id': renewal.parent_context_id,
        'parent_manifest_sha256': packet['manifest_sha256'], 'parent_packet_sha256': packet['packet_sha256'],
        'parent_review_id': review_id, 'parent_version_id': previous['version_id'], 'parent_product_id': previous['product_id'],
        'parent_graph_release_pin': previous['graph_release_pin'],
        'release_changed': previous['graph_release_pin'] != manifest['graph_release_pin'],
        'analysis_changed': previous['analysis_content_sha256'] != manifest['analysis_content_sha256'],
        'research_changed': previous['product_sha256'] != manifest['product_sha256'],
        'entries': entries, 'added_passage_ids': renewal.added_passage_ids,
        'old_quotes_and_notes': 'withheld_use_original_guarded_context', 'review_inheritance': 'none',
        'original_dependencies': 'retained_in_immutable_parent_not_reauthorized', 'legal_equivalence': 'not_assessed'}
