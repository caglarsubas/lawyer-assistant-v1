"""Offline, source-linked reference intake. Byte integrity is never legal approval."""

import hashlib
from collections import Counter, defaultdict
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .qualification import MAX_COMPONENT_BYTES, parse_component
from .qualification_catalog import SourceCatalog
from .qualification_evidence import MAX_FILE_BYTES, MAX_REFERENCE_FILES, MAX_TOTAL_BYTES, read_exact_directory
from .qualification_scoring import SNAPSHOT_KEYS, AdjudicatedTask, Protocol, digest, instant, unique
from .research_qualification import Digest, Practice, RecordId, StrictRecord

MAX_CASES = 1000
MAX_SOURCES = 300
MAX_LINKS = 64
DIMENSIONS = {'applicability', 'historical_version', 'conditions_exceptions',
              'authority_treatment', 'adverse_authority', 'uncertainty'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Source(StrictRecord):
    id: RecordId
    sample_kind: Literal['real', 'synthetic']
    source_family_id: RecordId | None
    kind: Literal['norm', 'decision', 'other']
    source_identity_sha256: Digest
    proceeding_identity_sha256: Digest | None
    representation_sha256: Digest
    passages_sha256: Digest
    rights_record_sha256: Digest | None
    history_record_sha256: Digest | None

    @model_validator(mode='after')
    def scope(self):
        if (self.sample_kind == 'real') != (self.source_family_id is not None):
            raise ValueError('Real sources need a catalog family; synthetic sources cannot claim one')
        if self.kind != 'decision' and self.proceeding_identity_sha256 is not None:
            raise ValueError('Proceeding identities describe decisions only')
        return self


class Passage(StrictRecord):
    ordinal: int = Field(ge=0, le=10000)
    locator: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=20000)


class Passages(StrictRecord):
    schema_version: Literal['legal-reference-passages-v1']
    source_id: RecordId
    representation_sha256: Digest
    passages: list[Passage] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def distinct(self):
        unique([item.ordinal for item in self.passages])
        return self


class Citation(StrictRecord):
    source_id: RecordId
    ordinal: int = Field(ge=0, le=10000)
    passage_text_sha256: Digest
    authority_id: RecordId
    role: Literal['support', 'adverse', 'context', 'unresolved']


class Observation(StrictRecord):
    dimension: Literal['applicability', 'historical_version', 'conditions_exceptions',
                       'authority_treatment', 'adverse_authority', 'uncertainty']
    status: Literal['not_assessed', 'unresolved', 'recorded']
    evidence_sha256: Digest | None

    @model_validator(mode='after')
    def explained(self):
        if (self.status == 'recorded') != (self.evidence_sha256 is not None):
            raise ValueError('Recorded observations require evidence; unknown remains unknown')
        return self


class Reference(StrictRecord):
    schema_version: Literal['legal-reference-answer-v1']
    case_id: RecordId
    task_input_sha256: Digest
    snapshot_sha256: Digest
    rubric_sha256: Digest
    prepared_at: str = Field(min_length=1, max_length=80)
    relevant_on: str | None = Field(default=None, min_length=10, max_length=10)
    reviewer_ids: list[RecordId] = Field(max_length=10)
    independence_record_sha256: Digest | None
    coverage: Literal['partial', 'declared_complete']
    adverse_search: Literal['not_assessed', 'incomplete', 'declared_complete']
    gold_authorities: list[RecordId] = Field(max_length=MAX_LINKS)
    citations: list[Citation] = Field(min_length=1, max_length=MAX_LINKS)
    observations: list[Observation] = Field(min_length=6, max_length=6)

    @model_validator(mode='after')
    def coherent(self):
        instant(self.prepared_at)
        if self.relevant_on is not None and date.fromisoformat(self.relevant_on).isoformat() != self.relevant_on:
            raise ValueError('Invalid relevant legal date')
        unique(self.reviewer_ids)
        unique(self.gold_authorities)
        unique([(item.source_id, item.ordinal, item.authority_id, item.role) for item in self.citations])
        if {item.dimension for item in self.observations} != DIMENSIONS:
            raise ValueError('All six reference dimensions must remain explicit')
        if self.independence_record_sha256 is not None and len(self.reviewer_ids) < 2:
            raise ValueError('Independence records need at least two declared reviewers')
        if (set(self.gold_authorities) - {item.authority_id for item in self.citations if item.role != 'unresolved'}
                or {item.authority_id for item in self.citations if item.role == 'adverse'} - set(self.gold_authorities)):
            raise ValueError('Gold authorities need exact references; adverse authorities remain explicit')
        return self


class Case(StrictRecord):
    id: RecordId
    sample_kind: Literal['real', 'synthetic']
    data_classification: Literal['public_scenario', 'synthetic_fixture']
    practice: Practice
    period: Literal['pre_1920', '1920_1981', '1982_2015', '2016_onward', 'unknown', 'synthetic']
    split: Literal['development', 'held_out']
    family_sha256: Digest
    family_basis: Literal['declared_proceeding', 'declared_near_duplicate', 'synthetic_fixture', 'unresolved']
    family_review_sha256: Digest | None
    task_input_sha256: Digest
    reference_sha256: Digest
    source_ids: list[RecordId] = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def scope(self):
        if (self.sample_kind == 'real') != (self.data_classification == 'public_scenario'):
            raise ValueError('Matter-private data belongs in the authorized application store')
        if self.sample_kind == 'real' and self.family_basis == 'synthetic_fixture':
            raise ValueError('Synthetic families cannot become real cases')
        if self.sample_kind == 'real' and self.period == 'synthetic':
            raise ValueError('Synthetic periods cannot become real cases')
        if self.family_basis == 'unresolved' and self.family_review_sha256 is not None:
            raise ValueError('Unresolved family review remains unknown')
        unique(self.source_ids)
        return self


class Casebook(StrictRecord):
    schema_version: Literal['legal-reference-casebook-v1']
    registered_at: str = Field(min_length=1, max_length=80)
    protocol_sha256: Digest
    snapshot_sha256: Digest
    rubric_sha256: Digest
    source_catalog_sha256: Digest
    sources: list[Source] = Field(min_length=1, max_length=MAX_SOURCES)
    cases: list[Case] = Field(min_length=1, max_length=MAX_CASES)
    reference_record_sha256: list[Digest] = Field(max_length=7000)

    @model_validator(mode='after')
    def inventory(self):
        instant(self.registered_at)
        unique([item.id for item in self.sources])
        unique([item.id for item in self.cases])
        unique(self.reference_record_sha256)
        return self


class Adjudication(StrictRecord):
    """Post-run evidence binds the entire validated row except its own digest."""
    schema_version: Literal['legal-reference-adjudication-v1']
    casebook_sha256: Digest
    case_id: RecordId
    reference_sha256: Digest
    row_content_sha256: Digest


def _inventory(book, references, rows, *, declared=False):
    specs = {}

    def add(key, limit=MAX_COMPONENT_BYTES):
        if key is not None:
            specs[f'{key}.bin'] = max(limit, specs.get(f'{key}.bin', 0))

    for source in book.sources:
        add(source.representation_sha256, MAX_FILE_BYTES)
        for key in (source.passages_sha256, source.rights_record_sha256, source.history_record_sha256):
            add(key)
    for case in book.cases:
        for key in (case.task_input_sha256, case.reference_sha256, case.family_review_sha256):
            add(key)
    for reference in references.values():
        add(reference.independence_record_sha256)
        for observation in reference.observations:
            add(observation.evidence_sha256)
    if declared:
        for key in book.reference_record_sha256:
            add(key)
    for row in rows:
        add(row.adjudication_evidence_sha256)
    return specs


def inspect_casebook(directory, artifacts_directory, source_catalog, rows=None, *, registration_directory=None,
                     witness_registry_directory=None, trusted_registry_sha256=None):
    """Stable exact captures; reports contain counts/hashes, never submitted prose."""
    witness_options = (registration_directory, witness_registry_directory, trusted_registry_sha256)
    if any(item is not None for item in witness_options) and any(item is None for item in witness_options):
        raise ValueError('Registration verification requires all witness inputs')
    meta_specs = dict.fromkeys(('casebook.json', 'protocol.json', 'snapshot.json'), MAX_COMPONENT_BYTES)
    captured = read_exact_directory(directory, meta_specs, MAX_COMPONENT_BYTES * 3)
    catalog_specs = {'source-catalog.json': MAX_COMPONENT_BYTES}
    catalog_bytes = read_exact_directory(source_catalog, catalog_specs, MAX_COMPONENT_BYTES)
    catalog = SourceCatalog.model_validate(parse_component(catalog_bytes['source-catalog.json']))
    book = Casebook.model_validate(parse_component(captured['casebook.json']))
    protocol = Protocol.model_validate(parse_component(captured['protocol.json']))
    snapshot = parse_component(captured['snapshot.json'])
    if (not isinstance(snapshot, dict) or set(snapshot) != SNAPSHOT_KEYS
            or any(not isinstance(v, str) or not 1 <= len(v) <= 200 for v in snapshot.values())
            or book.protocol_sha256 != digest(protocol.model_dump())
            or book.snapshot_sha256 != digest(snapshot) or book.snapshot_sha256 != protocol.snapshot_sha256
            or book.rubric_sha256 != protocol.rubric_sha256
            or book.source_catalog_sha256 != sha(catalog_bytes['source-catalog.json'])
            or instant(book.registered_at) < instant(protocol.registered_at)):
        raise ValueError('Reference casebook pins do not match')
    if rows is not None and (type(rows) is not list or len(rows) > MAX_CASES):
        raise ValueError('Measured rows exceed the bounded reference inventory')
    tasks = [AdjudicatedTask.model_validate(row) for row in rows] if rows is not None else []
    if any(row.mode != protocol.mode or row.provider != protocol.provider
           or row.provider_configuration_sha256 != protocol.provider_configuration_sha256 for row in tasks):
        raise ValueError('Measured provider scope differs from the frozen protocol')
    sources = {item.id: item for item in book.sources}
    if set(sources) != {ident for case in book.cases for ident in case.source_ids}:
        raise ValueError('Every source must be used; all case sources must resolve')
    catalog_ids = {item.id for item in catalog.sources}
    if any(item.sample_kind == 'real' and item.source_family_id not in catalog_ids for item in book.sources):
        raise ValueError('Unknown national source family')
    # All observation records are explicitly declared before opening any artifact;
    # expanded references must resolve to this exact inventory, with no unused files.
    specs = _inventory(book, {}, tasks, declared=True)
    artifacts = read_exact_directory(artifacts_directory, specs, MAX_TOTAL_BYTES, maximum_files=MAX_REFERENCE_FILES)
    parsed = {case.id: Reference.model_validate(parse_component(artifacts[f'{case.reference_sha256}.bin']))
              for case in book.cases}
    if _inventory(book, parsed, tasks) != specs:
        raise ValueError('Reference record inventory differs')
    if any(not value or sha(value) != name[:-4] for name, value in artifacts.items()):
        raise ValueError('Physical reference evidence differs')
    passages = {}
    for source in book.sources:
        passage_set = Passages.model_validate(parse_component(artifacts[f'{source.passages_sha256}.bin']))
        if passage_set.source_id != source.id or passage_set.representation_sha256 != source.representation_sha256:
            raise ValueError('Passages do not bind their original source representation')
        passages[source.id] = {item.ordinal: item for item in passage_set.passages}
    for case in book.cases:
        ref = parsed[case.id]
        if (ref.case_id != case.id or ref.task_input_sha256 != case.task_input_sha256
                or ref.snapshot_sha256 != book.snapshot_sha256 or ref.rubric_sha256 != book.rubric_sha256
                or instant(ref.prepared_at) > instant(book.registered_at)
                or any(sources[ident].sample_kind != case.sample_kind for ident in case.source_ids)):
            raise ValueError('Mixed or post-registration reference inputs')
        for citation in ref.citations:
            passage = passages.get(citation.source_id, {}).get(citation.ordinal)
            if (citation.source_id not in case.source_ids or passage is None
                    or sha(passage.text.encode()) != citation.passage_text_sha256):
                raise ValueError('Reference citation does not resolve to an exact passage')
        if (case.split == 'development' and case.family_sha256 not in protocol.development_family_sha256
                or case.split == 'held_out' and case.family_sha256 in protocol.development_family_sha256):
            raise ValueError('Protocol development reservation differs')
    report = _report(book, parsed, sources, tasks, artifacts, sha(captured['casebook.json']), rows is not None)
    report['registration_witness'] = {'status': 'not_supplied', 'registration_time_authenticated': False}
    if registration_directory is not None:
        from .registration_witness import verify_registration

        report['registration_witness'] = verify_registration(
            registration_directory, witness_registry_directory, trusted_registry_sha256, captured,
            book.source_catalog_sha256, book.registered_at, [row.measured_at for row in tasks])
    if (read_exact_directory(directory, meta_specs, MAX_COMPONENT_BYTES * 3) != captured
            or read_exact_directory(source_catalog, catalog_specs, MAX_COMPONENT_BYTES) != catalog_bytes
            or read_exact_directory(artifacts_directory, specs, MAX_TOTAL_BYTES, maximum_files=MAX_REFERENCE_FILES) != artifacts):
        raise ValueError('Reference casebook changed during inspection')
    if registration_directory is not None and report['registration_witness'] != verify_registration(
            registration_directory, witness_registry_directory, trusted_registry_sha256, captured,
            book.source_catalog_sha256, book.registered_at, [row.measured_at for row in tasks]):
        raise ValueError('Registration changed during complete casebook inspection')
    report['input_files'] = {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in captured.items()}
    report['verified_artifact_count'] = len(artifacts)
    report['verified_artifact_bytes'] = sum(map(len, artifacts.values()))
    return report


def _report(book, references, sources, tasks, artifacts, book_sha, measured):
    # Union shared inputs and decision/proceeding identities transitively. Shared
    # statutes are deliberately not case families; no fuzzy identity is inferred.
    parents = {case.id: case.id for case in book.cases}

    def root(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    seen = {}
    for case in book.cases:
        keys = [('family', case.family_sha256), ('task', case.task_input_sha256)]
        for ident in case.source_ids:
            source = sources[ident]
            if source.kind == 'decision':
                keys.extend([('decision', source.source_identity_sha256), ('representation', source.representation_sha256)])
                if source.proceeding_identity_sha256 is not None:
                    keys.append(('proceeding', source.proceeding_identity_sha256))
        for key in keys:
            if key in seen:
                parents[root(case.id)] = root(seen[key])
            else:
                seen[key] = case.id
    groups = defaultdict(list)
    for case in book.cases:
        groups[root(case.id)].append(case)
    cross_split = sum(len({case.split for case in group}) > 1 for group in groups.values())
    inconsistent = sum(len({case.family_sha256 for case in group}) > 1 for group in groups.values())
    overlap_origin = sum(len({case.sample_kind for case in group}) > 1 for group in groups.values())
    unknown_families = sum(case.family_basis == 'unresolved' or case.family_review_sha256 is None for case in book.cases)
    gaps = Counter()
    for case in book.cases:
        ref = references[case.id]
        gaps['two_declared_reviewers'] += len(ref.reviewer_ids) < 2
        gaps['independence_record'] += ref.independence_record_sha256 is None
        gaps['complete_reference'] += ref.coverage != 'declared_complete'
        gaps['adverse_search'] += ref.adverse_search != 'declared_complete'
        gaps['legal_date'] += ref.relevant_on is None
        gaps['historical_period'] += case.period == 'unknown'
        for dimension in ref.observations:
            gaps[dimension.dimension] += dimension.status != 'recorded'
        gaps['source_rights_record'] += any(sources[ident].rights_record_sha256 is None for ident in case.source_ids)
        gaps['source_history_record'] += any(sources[ident].history_record_sha256 is None for ident in case.source_ids)
    held = {case.id: case for case in book.cases if case.split == 'held_out'}
    unique([row.score.task_id for row in tasks])
    for row in tasks:
        case = held.get(row.score.task_id)
        if (case is None or row.task_input_sha256 != case.task_input_sha256
                or row.split_family_sha256 != case.family_sha256 or row.sample_kind != case.sample_kind
                or row.score.domain != case.practice or row.score.period != case.period or not row.score.held_out
                or row.protocol_sha256 != book.protocol_sha256 or row.snapshot_sha256 != book.snapshot_sha256
                or row.rubric_sha256 != book.rubric_sha256 or instant(row.measured_at) < instant(book.registered_at)):
            raise ValueError('Measured row differs from frozen reference case')
        ref = references[case.id]
        gold = set(ref.gold_authorities)
        adverse = {citation.authority_id for citation in ref.citations if citation.role == 'adverse'}
        if set(row.score.gold_authorities) != gold or set(row.analysis.gold_adverse_authorities) != adverse:
            raise ValueError('Measured gold authorities differ from the source-linked reference')
        proof = Adjudication.model_validate(parse_component(artifacts[f'{row.adjudication_evidence_sha256}.bin']))
        if (proof.casebook_sha256 != book_sha or proof.case_id != case.id
                or proof.reference_sha256 != case.reference_sha256
                or proof.row_content_sha256 != digest(row.model_dump(exclude={'adjudication_evidence_sha256'}))):
            raise ValueError('Adjudication evidence does not bind the exact scored row')
    missing = len(set(held) - {row.score.task_id for row in tasks})
    intake = not (cross_split or inconsistent or overlap_origin or unknown_families or any(gaps.values()))
    gate = bool(measured and held and not missing and intake
                and all(case.sample_kind == 'real' for case in held.values()))
    return {'schema_version': 'legal-reference-casebook-report-v1', 'structurally_valid': True,
            'runtime_authorization': 'none', 'production_qualified': False, 'legal_qualification': False,
            'source_authenticity_verified': False, 'original_transcription_verified': False,
            'reviewer_independence_verified': False, 'privacy_verified': False,
            'registration_time_authenticated': False, 'sample_representativeness_verified': False,
            'intake_checks_pass': intake, 'reference_case_binding_pass': gate, 'evaluation_rows_supplied': measured,
            'counts': {kind: {split: sum(case.sample_kind == kind and case.split == split for case in book.cases)
                              for split in ('development', 'held_out')} for kind in ('real', 'synthetic')},
            'practice_counts': {kind: dict(Counter(case.practice for case in book.cases if case.sample_kind == kind))
                                for kind in ('real', 'synthetic')},
            'period_counts': {kind: dict(Counter(case.period for case in book.cases if case.sample_kind == kind))
                              for kind in ('real', 'synthetic')},
            'family_checks': {'declared_families': len({case.family_sha256 for case in book.cases}),
                              'identity_components': len(groups), 'cross_split_components': cross_split,
                              'inconsistent_family_components': inconsistent, 'mixed_origin_components': overlap_origin,
                              'unknown_family_records': unknown_families, 'near_duplicate_discovery': 'not_performed'},
            'reference_gaps': dict(gaps), 'measured_rows': len(tasks), 'missing_held_out_rows': missing,
            'quality_metrics': None, 'preparation_time_gain': None}
