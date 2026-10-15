"""Exact submitting-actor observation, without source reads or write recovery."""

from fastapi import HTTPException
from pydantic import Field

from . import source_context_navigation as navigation
from . import source_review_lineage as lineage
from .auth import require_child, require_matter
from .db import Record, digest, now
from .evidence_prompt import canonical
from .practice import StrictInput

RECIPE = 'private-source-review-reconciliation-v1'


class Receipt(StrictInput):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_review_id: str | None = Field(default=None, pattern=r'^sar-[a-f0-9]{20}-[a-f0-9]{32}$')
    version_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')


def observe(store, session, matter_id, analysis_id, context_id, receipt, user):
    from . import source_analysis_reviews as reviews

    if not navigation.CONTEXT_ID.fullmatch(context_id) or not context_id.startswith(reviews._prefix(matter_id, analysis_id)):
        raise HTTPException(404, 'Kaynak bağlamı bulunamadı.')
    if receipt.expected_review_id:
        lineage._route(context_id, receipt.expected_review_id)
    matter = require_matter(session, matter_id, user)
    session.refresh(matter, with_for_update=True)
    session.expire_all()
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    require_child(session, context_id, reviews.KIND, matter_id, user)
    result = {'recipe': RECIPE, 'matter_id': matter_id, 'analysis_id': analysis_id, 'context_id': context_id,
        'observed_at': now(), 'receipt': receipt.model_dump(), 'outcome': 'not_observed',
        'context': None, 'review': None, 'admission': None, 'current_head': 'not_checked',
        'source_verification': 'not_checked', 'legal_readiness': 'not_established',
        'qualification_granted': False, 'effects_replayed': False}
    ident = 'sar-' + digest(context_id)[:20] + '-' + digest(user.id + ':' + receipt.request_id)[:32]
    row = session.get(Record, ident)
    if not row:
        return result
    result['outcome'] = 'unavailable'
    # The lookup is scoped to this authenticated submitter, never today's head.
    # Authenticate both routing records and the owner before decrypting the event.
    if row.kind != reviews.REVIEW or row.matter_id != matter_id or row.firm_id != user.firm_id or row.owner_id != user.id:
        return result
    try:
        _, packet, _, proof = reviews._require(store, session, matter_id, analysis_id, context_id, user)
        reviews._reviewer(session, matter_id, user, packet)
        spec = reviews._manifest_spec(packet['manifest'])
        if (packet['manifest']['recipe'] != reviews.RECIPE or packet.get('immutable') is not True or type(proof.get('guard_completed')) is not bool
                or spec.version_id != receipt.version_id or packet['manifest_sha256'] != receipt.expected_manifest_sha256):
            return result
        _, event, _, event_proof = reviews._require(store, session, matter_id, analysis_id, ident, user, review=True, context_id=context_id)
        submitted = reviews.ReviewInput.model_validate(event['input'])
        meta = lineage._event(store, session, matter_id, analysis_id, context_id, ident, user, packet['manifest_sha256'])
        if (meta['integrity'] != 'verified' or type(event_proof.get('guard_completed')) is not bool
                or event.get('immutable') is not True or event['recorded_by'] != user.id
                or submitted.request_id != receipt.request_id or submitted.expected_review_id != receipt.expected_review_id
                or event['request_sha256'] != receipt.expected_request_sha256
                or event['request_sha256'] != digest(canonical(reviews._review_value(submitted, {'request_id'})))):
            return result
        reviews._validate_review(submitted, packet)
        predecessor = None
        predecessor_admission = 'not_recorded'
        if receipt.expected_review_id:
            _, previous_event, _, previous_proof = reviews._require(store, session, matter_id, analysis_id,
                receipt.expected_review_id, user, review=True, context_id=context_id)
            predecessor = lineage._event(store, session, matter_id, analysis_id, context_id, receipt.expected_review_id,
                user, packet['manifest_sha256'])
            if (previous_event.get('immutable') is not True or type(previous_proof.get('guard_completed')) is not bool or predecessor['integrity'] != 'verified'
                    or predecessor['sequence'] != meta['sequence'] - 1):
                return result
            predecessor_admission = predecessor['admission']
        reviews._reviewer(session, matter_id, user, packet)
        result.update(outcome='verified', context={'id': context_id, 'version_id': spec.version_id,
            'manifest_sha256': packet['manifest_sha256'], 'packet_sha256': packet['packet_sha256']},
            review={**meta, 'previous_review_packet_sha256': predecessor['packet_sha256'] if predecessor else None},
            admission={'context': 'complete' if proof['guard_completed'] else 'pending',
                'review': meta['admission'], 'predecessor': predecessor_admission})
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 409, 422}:
            raise
    except (KeyError, ValueError, TypeError):
        pass
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    require_child(session, context_id, reviews.KIND, matter_id, user)
    require_child(session, ident, reviews.REVIEW, matter_id, user)
    return reviews._bounded(result)
