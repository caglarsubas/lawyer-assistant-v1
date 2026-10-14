"""Private source nominations and independent, immutable lawyer decisions.

Source passages keep their exact release/representation identity. An annotation
does not resolve an authority, change an analysis or grant legal approval.
Every operation uses one current source guard; no nested source transactions.
"""

from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, model_validator
from rdflib import URIRef
from sqlalchemy import select

from . import analysis_authorities as authorities
from . import analysis_reviews, analysis_workbench
from .analysis_adjudication import target_values
from .auth import authenticate, require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .exports import render_export
from .firm_rbac import require_permission
from .graph import GraphBackendError
from .practice import StrictInput, _audit
from .research import _product_graph_pin
from .source_corpus import EvidenceLookup, _project

RECIPE = 'private-source-analysis-context-v1'
REVIEW_RECIPE = 'independent-source-analysis-review-v1'
KIND = 'source_analysis_context'
REVIEW = 'source_analysis_review'
HEAD = 'source_analysis_review_head'
ADMISSION = 'source_analysis_admission'
MAX_BYTES = 2 * 1024 * 1024
MAX_REVIEWS = 100
IDENTITY = ('passage_id', 'source_version_id', 'quote_sha256')
Relationship = Literal['support_candidate', 'adverse_candidate', 'material_distinction', 'background', 'unresolved']
DIMENSIONS = {
    'quote_identity': 'Özgün pasaj, sürüm, konum ve alıntı sınırları',
    'target_alignment': 'Seçilen analiz adımları ile bağlantı ve karşı dayanaklar',
    'temporal_limits': 'Olay tarihi, bilinmeyen uygulanabilirlik ve derlem sınırları',
}


class Selection(StrictInput):
    passage_id: str = Field(min_length=1, max_length=512)
    source_version_id: str = Field(min_length=1, max_length=512)
    quote_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    target_ids: list[str] = Field(min_length=1, max_length=12)
    relationship: Relationship
    note: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def bounded(self):
        EvidenceLookup(passage_id=self.passage_id, source_version_id=self.source_version_id,
                       expected_release_id='0' * 64, expected_serving_sha256='0' * 64)
        if (len(set(self.target_ids)) != len(self.target_ids)
                or any(not 1 <= len(item) <= 129 for item in self.target_ids) or len(self.note.strip()) < 3):
            raise ValueError('Use distinct bounded targets and explain the relationship')
        return self


class Specification(StrictInput):
    version_id: str = Field(min_length=1, max_length=64)
    product_id: str = Field(min_length=1, max_length=64)
    expected_release_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_serving_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=3, max_length=2000)
    selections: list[Selection] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def distinct(self):
        if (len({item.passage_id for item in self.selections}) != len(self.selections)
                or len(self.title.strip()) < 3 or len(self.purpose.strip()) < 3):
            raise ValueError('Use distinct source occurrences and an explained purpose')
        return self


class Freeze(Specification):
    expected_preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class Observation(StrictInput):
    dimension: Literal['quote_identity', 'target_alignment', 'temporal_limits']
    outcome: Literal['confirmed', 'needs_change', 'not_assessed']
    note: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def explained(self):
        if len(self.note.strip()) < 3:
            raise ValueError('Explain every observation')
        return self


class SourceAssessment(Selection):
    observations: list[Observation] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def complete(self):
        if {item.dimension for item in self.observations} != set(DIMENSIONS):
            raise ValueError('Address every distinct review dimension')
        return self


class ReviewInput(StrictInput):
    expected_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_review_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    decision: Literal['reviewed_conditional', 'changes_requested']
    sources: list[SourceAssessment] = Field(min_length=1, max_length=8)
    note: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def bounded(self):
        outcomes = {item.outcome for source in self.sources for item in source.observations}
        if (len({item.passage_id for item in self.sources}) != len(self.sources)
                or len(self.note.strip()) < 3 or len(canonical(self.model_dump()).encode()) > 128 * 1024
                or (self.decision == 'reviewed_conditional' and outcomes != {'confirmed'})
                or (self.decision == 'changes_requested' and 'needs_change' not in outcomes)):
            raise ValueError('Use distinct, complete and explained review decisions')
        return self


def _bounded(value, reserve=0):
    if len(canonical(value).encode()) + reserve > MAX_BYTES:
        raise HTTPException(409, 'Kaynak incelemesi boyut sınırını aşıyor; kısmi kayıt oluşturulamaz.')
    return value


def _id(prefix, ident):
    return prefix + digest(ident)[:32]


def _prefix(matter_id, analysis_id):
    return 'sac-' + digest(matter_id + ':' + analysis_id)[:20] + '-'


def _product(store, session, matter_id, ident, user):
    row = require_child(session, ident, 'product', matter_id, user)
    session.refresh(row)
    data = store.decode(row)
    try:
        pin = _product_graph_pin(data)
        sources = data['source_candidates']
        if pin is None or not sources['hits'] or data['status'] not in {'ready', 'needs_review'}:
            raise ValueError('No current retained source capture')
    except (ValueError, KeyError, TypeError, GraphBackendError):
        raise HTTPException(409, 'Güncel ve izinli kaynak adaylarını içeren araştırma kaydı gerekli.') from None
    return row, data, pin, sources


def _analysis_pin(store, session, matter_id, analysis_id, value, user):
    row, version, content, context = value
    return digest(canonical({'record': store.view(row), 'version': store.view(version), 'content': content, 'context': context,
        'private_basis': authorities._basis(store, session, matter_id, analysis_id, content, user, context['expected_review_id'])}))


@contextmanager
def _operation(app, session, matter_id, analysis_id, version_id, product_id, user):
    """Check existing authority dependencies sequentially, outside our source guard.

    The matter row serializes sanctioned private edits/reviews. A final complete
    analysis check also catches a change after a committed write/guard exit.
    The held source guard still proves every original source and retained grant.
    """
    store = app.state.store
    matter = require_matter(session, matter_id, user)
    session.refresh(matter, with_for_update=True)
    session.expire_all()
    prepared = authorities._analysis(store, session, matter_id, analysis_id, version_id, user)
    pin = _analysis_pin(store, session, matter_id, analysis_id, prepared, user)
    _, public, _, _ = _product(store, session, matter_id, product_id, user)
    public_sha = digest(canonical(public))
    with authorities._guard(app, public):
        yield prepared
    session.expire_all()
    current = authorities._analysis(store, session, matter_id, analysis_id, version_id, user)
    _, public, _, _ = _product(store, session, matter_id, product_id, user)
    if (_analysis_pin(store, session, matter_id, analysis_id, current, user) != pin
            or digest(canonical(public)) != public_sha):
        raise HTTPException(409, 'İşlem sırasında özel analiz veya araştırma dayanakları değişti.')


def _private_analysis(store, session, matter_id, analysis_id, version_id, user, prepared):
    row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    session.refresh(row)
    _, snapshot = analysis_reviews._version(store, session, matter_id, analysis_id, version_id, user)
    content, context = snapshot['content'], prepared[3]
    # No guarded authority helper is called while our source guard is held.
    # Complete authority freshness is checked by _operation on both sides.
    if (content != prepared[2] or row.revision != context['expected_revision']
            or analysis_reviews.review_pin(store, session, matter_id, analysis_id, version_id, user) != context['expected_review_id']
            or analysis_workbench._freshness(store, session, matter_id, user, content, include_authorities=False)['status'] != 'current'
            or store.decode(row)['latest_version_id'] != version_id):
        raise HTTPException(409, 'Özel analiz dayanakları değişti; yeniden inceleme gerekli.')
    return row, snapshot, content, context


def _preview(app, session, matter_id, analysis_id, spec, user, prepared):
    # Caller holds the one product/source guard, including retained grants.
    spec = Specification.model_validate(spec.model_dump(warnings=False))
    store = app.state.store
    row, version, content, context = _private_analysis(store, session, matter_id, analysis_id, spec.version_id, user, prepared)
    if not context['current_version'] or context['freshness']['status'] != 'current':
        raise HTTPException(409, 'Güncel dayanaklı son analiz sürümünü seçin.')
    product, data, pin, candidates = _product(store, session, matter_id, spec.product_id, user)
    if (pin['release_id'] != spec.expected_release_id or pin['serving_sha256'] != spec.expected_serving_sha256):
        raise HTTPException(409, 'Kaynak yayın sürümü değişti; önizlemeyi yenileyin.')
    targets, sources = target_values(content), []
    release = app.state.graph.release
    for selected in spec.selections:
        if not set(selected.target_ids) <= targets.keys():
            raise HTTPException(422, 'Seçilen hedefler tam analiz sürümünde bulunmalıdır.')
        matches = [hit for hit in candidates['hits'] if all(hit.get(key) == getattr(selected, key) for key in IDENTITY)]
        if len(matches) != 1:
            raise HTTPException(422, 'Pasaj, belge sürümü ve alıntı özeti tam araştırma adayından seçilmelidir.')
        # validate_retained already proved every hit inside the held guard.
        evidence = _project(release, URIRef(selected.passage_id))
        sources.append({'selection': selected.model_dump(), 'evidence': evidence,
            'target_snapshots': {key: targets[key] for key in selected.target_ids}})
    manifest = {'recipe': RECIPE, 'matter_id': matter_id, 'analysis_id': analysis_id, **spec.model_dump(),
        'analysis_author_id': version['authored_by'], 'analysis_owner_id': row.owner_id, 'analysis_revision': row.revision,
        'analysis_content_sha256': context['content_sha256'], 'analysis_content': content,
        'analysis_review_id': context['expected_review_id'],
        'private_basis': authorities._basis(store, session, matter_id, analysis_id, content, user, context['expected_review_id']),
        'product_revision': product.revision, 'product_sha256': digest(canonical(data)),
        'graph_release_pin': pin, 'research_snapshot': candidates['snapshot'],
        'coverage': candidates['coverage'], 'limitations': candidates['limitations'],
        'sources': sources, 'event_date': content['event_date'],
        'scope': 'private_source_nominations_only', 'authority_resolution': 'not_performed',
        'matter_applicability': 'not_assessed', 'temporal_applicability': 'not_assessed',
        'finality': 'unknown', 'legal_approval': 'not_granted', 'qualification_granted': False,
        'production_qualified': False, 'model_use': 'none', 'runtime_authorization': 'none'}
    # A complete 128 KiB review and response envelope must still fit later.
    return _bounded({'manifest': manifest, 'preview_sha256': digest(canonical(manifest))}, reserve=140000)


def _require(store, session, matter_id, analysis_id, ident, user, *, review=False, context_id=None):
    row = require_child(session, ident, REVIEW if review else KIND, matter_id, user)
    data = store.decode(row)
    admission = require_child(session, _id('saa-', ident), ADMISSION, matter_id, user)
    proof = store.decode(admission)
    try:
        if (data['packet_sha256'] != digest(canonical({key: value for key, value in data.items() if key != 'packet_sha256'}))
                or data['analysis_id'] != analysis_id or data['matter_id'] != matter_id
                or proof['packet_id'] != ident or proof['packet_sha256'] != data['packet_sha256']
                or admission.owner_id != row.owner_id or data['recorded_by'] != row.owner_id):
            raise ValueError('Invalid packet identity')
        if review:
            ReviewInput.model_validate(data['input'])
            if data['context_id'] != context_id or data['input']['expected_manifest_sha256'] != data['manifest_sha256']:
                raise ValueError('Invalid review context')
        elif (digest(canonical(data['manifest'])) != data['manifest_sha256']
                or data['manifest']['analysis_id'] != analysis_id or data['manifest']['matter_id'] != matter_id):
            raise ValueError('Invalid manifest')
    except (ValueError, KeyError, TypeError):
        raise HTTPException(409, 'Saklanan kaynak incelemesinin bütünlüğü doğrulanamadı.') from None
    return row, data, admission, proof


def _head(store, session, matter_id, analysis_id, ident, user):
    row = session.get(Record, _id('sah-', ident), populate_existing=True)
    if not row:
        return None
    require_child(session, row.id, HEAD, matter_id, user)
    value = store.decode(row)
    _, latest, _, _ = _require(store, session, matter_id, analysis_id, value['latest_review_id'], user, review=True, context_id=ident)
    if latest['sequence'] != value['sequence']:
        raise HTTPException(409, 'İnceleme sırası doğrulanamadı.')
    return value


def _reviewer(session, matter_id, user, packet):
    current = require_permission(session, user, 'matter.review')
    require_matter(session, matter_id, current)
    if current.role not in {'lawyer', 'admin'} or current.id in {
            packet['recorded_by'], packet['manifest']['analysis_author_id'], packet['manifest']['analysis_owner_id']}:
        raise HTTPException(403, 'Analiz ve kaynak seçimini yapanlardan farklı, yetkili bir avukat incelemeci gerekli.')
    return current


def _inspect(app, session, matter_id, analysis_id, ident, user, prepared, review_id=None):
    """Under the caller's guard: reconstitute the frozen basis, never substitute."""
    store = app.state.store
    _, packet, _, proof = _require(store, session, matter_id, analysis_id, ident, user)
    result = {'id': ident, 'version_id': packet['manifest']['version_id'], 'recorded_at': packet['recorded_at'],
        'manifest_sha256': packet['manifest_sha256'], 'packet_sha256': packet['packet_sha256'],
        'manifest': None, 'public_source_access': False, 'freshness': {'status': 'stale', 'reasons': []},
        'review': {'effective_state': 'unreviewed', 'latest_review_id': None, 'snapshot': None},
        'qualification_granted': False, 'legal_approval': 'not_granted', 'runtime_authorization': 'none'}
    reasons = []
    if not proof.get('guard_completed'):
        reasons.append('post_commit_authorization_pending')
    try:
        spec = Specification.model_validate({key: packet['manifest'][key] for key in Specification.model_fields})
        current = _preview(app, session, matter_id, analysis_id, spec, user, prepared)
        if current['preview_sha256'] != packet['manifest_sha256']:
            reasons.append('private_or_research_basis_changed')
    except HTTPException as exc:
        if exc.status_code not in {404, 409, 422}:
            raise
        reasons.append('private_or_research_basis_unavailable')
    head = _head(store, session, matter_id, analysis_id, ident, user)
    if head:
        result['review']['latest_review_id'] = head['latest_review_id']
    selected_review = review_id or (head['latest_review_id'] if head else None)
    if selected_review:
        _, event, _, review_proof = _require(store, session, matter_id, analysis_id, selected_review, user, review=True, context_id=ident)
        reviewer = session.get(User, event['recorded_by'], populate_existing=True)
        try:
            if reviewer is None:
                raise HTTPException(403)
            _reviewer(session, matter_id, reviewer, packet)
        except HTTPException:
            reasons.append('reviewer_access_changed')
        if (not review_proof.get('guard_completed') or event['manifest_sha256'] != packet['manifest_sha256']
                or event['recipe'] != REVIEW_RECIPE or event['dimensions'] != DIMENSIONS):
            reasons.append('review_basis_changed_or_pending')
        result['review'].update(id=selected_review, is_latest=bool(head and selected_review == head['latest_review_id']))
        if not reasons:
            result['review'].update(effective_state=event['input']['decision'], snapshot=event)
    if reasons:
        result['freshness']['reasons'] = list(dict.fromkeys(reasons))
        if selected_review:
            result['review']['effective_state'] = 'stale'
        return result
    result.update(manifest=packet['manifest'], public_source_access=True, freshness={'status': 'current', 'reasons': []})
    return _bounded(result)


def _read(app, session, matter_id, analysis_id, ident, user, review_id=None):
    store = app.state.store
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    _, packet, _, _ = _require(store, session, matter_id, analysis_id, ident, user)
    try:
        with _operation(app, session, matter_id, analysis_id, packet['manifest']['version_id'], packet['manifest']['product_id'], user) as prepared:
            result = _inspect(app, session, matter_id, analysis_id, ident, user, prepared, review_id)
            require_child(session, ident, KIND, matter_id, user)
        _post_review_check(store, session, matter_id, analysis_id, ident, user, packet, result)
        require_child(session, ident, KIND, matter_id, user)
        return result
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        # Free-text decisions can contain quotes; withhold them together.
        require_child(session, ident, KIND, matter_id, user)
        return {'id': ident, 'manifest': None, 'public_source_access': False,
            'freshness': {'status': 'withheld', 'reasons': ['source_authorization_or_evidence_unavailable']},
            'review': {'effective_state': 'stale', 'snapshot': None},
            'qualification_granted': False, 'legal_approval': 'not_granted', 'runtime_authorization': 'none'}


def _post_review_check(store, session, matter_id, analysis_id, ident, user, packet, result):
    """Recheck private review state after source guard exit, without source reads."""
    event = result['review'].get('snapshot')
    if not event:
        return
    session.expire_all()
    head = _head(store, session, matter_id, analysis_id, ident, user)
    _, current, _, proof = _require(store, session, matter_id, analysis_id, result['review']['id'], user, review=True, context_id=ident)
    reviewer = session.get(User, current['recorded_by'], populate_existing=True)
    try:
        if reviewer is None:
            raise HTTPException(403)
        _reviewer(session, matter_id, reviewer, packet)
    except HTTPException:
        raise HTTPException(409, 'Bağımsız incelemecinin güncel yetkisi doğrulanamadı.') from None
    if (not head or head['latest_review_id'] != result['review']['latest_review_id']
            or current != event or not proof.get('guard_completed')
            or current['recipe'] != REVIEW_RECIPE or current['dimensions'] != DIMENSIONS):
        raise HTTPException(409, 'İnceleme sırası veya dayanakları işlem sırasında değişti.')


def _finalize(store, matter_id, analysis_id, ident, user, *, review=False, context_id=None):
    with store.session() as session:
        matter = require_matter(session, matter_id, user)
        session.refresh(matter, with_for_update=True)
        row, _, admission, proof = _require(store, session, matter_id, analysis_id, ident, user, review=review, context_id=context_id)
        if row.owner_id != user.id:
            raise HTTPException(403)
        proof.update(guard_completed=True, completed_at=now())
        store.update(admission, proof)
        session.commit()


def _save_packet(store, session, matter_id, analysis_id, ident, user, data, *, review=False):
    data.update(matter_id=matter_id, analysis_id=analysis_id, recorded_by=user.id, recorded_at=now(), immutable=True)
    data['packet_sha256'] = digest(canonical(data))
    _bounded(data, reserve=4096)
    store.add(session, REVIEW if review else KIND, user, data, matter_id, record_id=ident)
    store.add(session, ADMISSION, user, {'packet_id': ident, 'packet_sha256': data['packet_sha256'],
              'guard_completed': False}, matter_id, record_id=_id('saa-', ident))
    _audit(session, user, 'source_analysis_review_recorded' if review else 'source_analysis_context_frozen', ident, matter_id)


def _validate_review(body, packet):
    expected = {tuple(source['selection'][key] for key in IDENTITY): set(source['selection']['target_ids'])
                for source in packet['manifest']['sources']}
    actual = {tuple(getattr(source, key) for key in IDENTITY): set(source.target_ids) for source in body.sources}
    if actual != expected:
        raise HTTPException(422, 'Her tam kaynak ve bağlı analiz adımı ayrı ve eksiksiz değerlendirilmelidir.')


def _pending(ident):
    return JSONResponse(status_code=409, content={'id': ident, 'outcome': 'committed_needs_revalidation',
        'detail': 'Kayıt saklandı; son izin kontrolü tamamlanamadı. Yeni önizleme ve ayrı kayıt gerekli.'})


def _export_lines(value):
    manifest, event = value['manifest'], value['review']['snapshot']
    lines = ['GİZLİ — KAYNAK VE ANALİZ İNCELEMESİ', manifest['title'], manifest['purpose'],
        'Avukatın koşullu beyanıdır; hukuki onay veya bağlayıcı etki oluşturmaz.',
        'Özgün boşluk ve satır sonları için JSON veya kaynak pasajını inceleyin.',
        'Analiz sürümü: ' + manifest['version_id'], 'Analiz SHA-256: ' + manifest['analysis_content_sha256'],
        'Kaynak bağlamı SHA-256: ' + value['manifest_sha256'], 'Yayın: ' + canonical(manifest['graph_release_pin']),
        'Derlem kapsamı: ' + canonical(manifest['coverage']), *manifest['limitations'],
        'Olay tarihi: ' + str(manifest['event_date']), 'Hukuki ve zamansal uygulanabilirlik: değerlendirilmedi. Kesinleşme: bilinmiyor.']
    for source in manifest['sources']:
        selected, evidence = source['selection'], source['evidence']
        lines.extend(['Seçimi yapan avukatın beyanı: ' + selected['relationship'], selected['note'],
            'Analiz adımları: ' + canonical(source['target_snapshots']),
            'Pasaj: ' + evidence['passage_id'], 'Kaynak sürümü: ' + evidence['source_version_id'],
            'Özgün yer: ' + evidence['locator'] + f" / [{evidence['start_offset']}, {evidence['end_offset']})",
            evidence['text'], 'Alıntı SHA-256: ' + evidence['quote_sha256'],
            'Kaynak/metin/konum SHA-256: ' + canonical({key: evidence[key] for key in (
                'source_sha256', 'text_sha256', 'locator_map_sha256')})])
    lines.extend(['Bağımsız incelemeci: ' + event['recorded_by'], 'İnceleme: ' + value['review']['id'],
        'İnceleme SHA-256: ' + event['packet_sha256'], 'Karar: ' + event['input']['decision'], event['input']['note']])
    for source in event['input']['sources']:
        lines.extend(['İncelemecinin bağlantı beyanı: ' + source['relationship'], source['note'],
                      'Hedefler: ' + ', '.join(source['target_ids']), 'Pasaj: ' + source['passage_id']])
        lines.extend(item['dimension'] + ' / ' + item['outcome'] + ': ' + item['note'] for item in source['observations'])
    return lines


def source_analysis_router():
    router = APIRouter(prefix='/api/v1/matters/{matter_id}/analyses/{analysis_id}/source-contexts', tags=['private-source-analysis-review'])

    @router.get('/candidates')
    def candidates(matter_id: str, analysis_id: str, product_id: str, version_id: str, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            with _operation(app, session, matter_id, analysis_id, version_id, product_id, user) as prepared:
                _, _, content, context = prepared
                _, _, pin, sources = _product(store, session, matter_id, product_id, user)
                result = _bounded({'sources': sources['hits'], 'snapshot': sources['snapshot'], 'graph_release_pin': pin,
                    'coverage': sources['coverage'], 'limitations': sources['limitations'], 'targets': target_values(content),
                    'current_version': context['current_version'], 'private_freshness': context['freshness']})
                require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            return result

    @router.post('/preview')
    def preview(matter_id: str, analysis_id: str, body: Specification, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            with _operation(app, session, matter_id, analysis_id, body.version_id, body.product_id, user) as prepared:
                result = _preview(app, session, matter_id, analysis_id, body, user, prepared)
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            return result

    @router.post('', status_code=201)
    def freeze(matter_id: str, analysis_id: str, body: Freeze, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        spec = Specification.model_validate(body.model_dump(exclude={'request_id', 'expected_preview_sha256'}))
        ident = _prefix(matter_id, analysis_id) + digest(user.id + ':' + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={'request_id'})))
        committed = False
        try:
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                if session.get(Record, ident):
                    _, packet, _, _ = _require(store, session, matter_id, analysis_id, ident, user)
                    if packet['request_sha256'] != request_sha or packet['recorded_by'] != user.id:
                        raise HTTPException(409, 'İstek kimliği farklı bir kayda bağlı.')
                    return _read(app, session, matter_id, analysis_id, ident, user)
                if store.decode(matter).get('status') == 'archived':
                    raise HTTPException(409, 'Arşivlenmiş alanda kayıt oluşturulamaz.')
                with _operation(app, session, matter_id, analysis_id, spec.version_id, spec.product_id, user) as prepared:
                    value = _preview(app, session, matter_id, analysis_id, spec, user, prepared)
                    if value['preview_sha256'] != body.expected_preview_sha256:
                        raise HTTPException(409, 'Önizleme değişti; dayanakları yeniden açın.')
                    _save_packet(store, session, matter_id, analysis_id, ident, user, {'manifest': value['manifest'],
                        'manifest_sha256': value['preview_sha256'], 'request_sha256': request_sha})
                    session.flush()
                    session.expire_all()
                    if _preview(app, session, matter_id, analysis_id, spec, user, prepared)['preview_sha256'] != body.expected_preview_sha256:
                        raise HTTPException(409, 'Kayıt sırasında dayanaklar değişti.')
                    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
                    session.commit()
                    committed = True
            _finalize(store, matter_id, analysis_id, ident, user)
            with store.session() as session:
                return _read(app, session, matter_id, analysis_id, ident, user)
        except Exception:
            if committed:
                return _pending(ident)
            raise

    @router.get('')
    def history(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            rows = session.scalars(select(Record).where(Record.kind == KIND, Record.matter_id == matter_id,
                Record.firm_id == user.firm_id, Record.id.startswith(_prefix(matter_id, analysis_id)))
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            # Metadata only: names and notes may repeat a subsequently withdrawn quote.
            return [{'id': row.id, 'recorded_at': row.created_at} for row in rows]

    @router.get('/{context_id}')
    def detail(matter_id: str, analysis_id: str, context_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            return _read(request.app, session, matter_id, analysis_id, context_id, user)

    @router.get('/{context_id}/reviews/context')
    def review_context(matter_id: str, analysis_id: str, context_id: str, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            _, packet, _, _ = _require(store, session, matter_id, analysis_id, context_id, user)
            _reviewer(session, matter_id, user, packet)
            # Fresh source/private context may renew a revoked review; no historical event is edited.
            with _operation(app, session, matter_id, analysis_id, packet['manifest']['version_id'], packet['manifest']['product_id'], user) as prepared:
                spec = Specification.model_validate({key: packet['manifest'][key] for key in Specification.model_fields})
                current = _preview(app, session, matter_id, analysis_id, spec, user, prepared)
                if current['preview_sha256'] != packet['manifest_sha256']:
                    raise HTTPException(409, 'Kaynak veya özel dayanaklar değişti; yeni bağlam gerekli.')
                _, _, _, proof = _require(store, session, matter_id, analysis_id, context_id, user)
                if not proof.get('guard_completed'):
                    raise HTTPException(409, 'Bağlamın son izin kontrolü tamamlanmadı.')
                head = _head(store, session, matter_id, analysis_id, context_id, user)
                result = _bounded({'manifest': current['manifest'], 'expected_manifest_sha256': current['preview_sha256'],
                    'expected_review_id': head['latest_review_id'] if head else None, 'dimensions': DIMENSIONS,
                    'independent_reviewer_required': True, 'qualification_granted': False}, reserve=4096)
                _reviewer(session, matter_id, user, packet)
            _reviewer(session, matter_id, user, packet)
            return result

    @router.post('/{context_id}/reviews', status_code=201)
    def record_review(matter_id: str, analysis_id: str, context_id: str, body: ReviewInput, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        ident = 'sar-' + digest(context_id)[:20] + '-' + digest(user.id + ':' + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={'request_id'})))
        committed = False
        try:
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                _, packet, _, proof = _require(store, session, matter_id, analysis_id, context_id, user)
                _reviewer(session, matter_id, user, packet)
                if session.get(Record, ident):
                    _, event, _, _ = _require(store, session, matter_id, analysis_id, ident, user, review=True, context_id=context_id)
                    if event['request_sha256'] != request_sha or event['recorded_by'] != user.id:
                        raise HTTPException(409, 'İstek kimliği farklı bir incelemeye bağlı.')
                    return _read(app, session, matter_id, analysis_id, context_id, user, ident)
                if not proof.get('guard_completed') or store.decode(matter).get('status') == 'archived':
                    raise HTTPException(409, 'Yeni inceleme için açık alan ve tamamlanmış bağlam gerekli.')
                with _operation(app, session, matter_id, analysis_id, packet['manifest']['version_id'], packet['manifest']['product_id'], user) as prepared:
                    # One guard, without calling another guarded route or lookup.
                    spec = Specification.model_validate({key: packet['manifest'][key] for key in Specification.model_fields})
                    current = _preview(app, session, matter_id, analysis_id, spec, user, prepared)
                    if current['preview_sha256'] != packet['manifest_sha256'] or body.expected_manifest_sha256 != packet['manifest_sha256']:
                        raise HTTPException(409, 'İncelenen tam kaynak veya analiz sürümü değişti.')
                    head = _head(store, session, matter_id, analysis_id, context_id, user)
                    if body.expected_review_id != (head['latest_review_id'] if head else None):
                        raise HTTPException(409, 'İnceleme sırası değişti; yeniden açın.')
                    sequence = head['sequence'] + 1 if head else 1
                    if sequence > MAX_REVIEWS:
                        raise HTTPException(409, 'İnceleme sayısı sınırına ulaşıldı; ayrı yeni bağlam gerekli.')
                    _validate_review(body, packet)
                    _save_packet(store, session, matter_id, analysis_id, ident, user, {'context_id': context_id,
                        'manifest_sha256': packet['manifest_sha256'], 'input': body.model_dump(), 'request_sha256': request_sha,
                        'recipe': REVIEW_RECIPE, 'dimensions': DIMENSIONS, 'sequence': sequence,
                        'previous_review_id': body.expected_review_id, 'legal_approval': 'not_granted'}, review=True)
                    head_row = session.get(Record, _id('sah-', context_id))
                    head_data = {'latest_review_id': ident, 'sequence': sequence}
                    if head_row:
                        store.update(head_row, head_data)
                    else:
                        store.add(session, HEAD, user, head_data, matter_id, record_id=_id('sah-', context_id))
                    session.flush()
                    session.expire_all()
                    if _preview(app, session, matter_id, analysis_id, spec, user, prepared)['preview_sha256'] != packet['manifest_sha256']:
                        raise HTTPException(409, 'İnceleme sırasında dayanaklar değişti.')
                    _reviewer(session, matter_id, user, packet)
                    session.commit()
                    committed = True
            _finalize(store, matter_id, analysis_id, ident, user, review=True, context_id=context_id)
            with store.session() as session:
                return _read(app, session, matter_id, analysis_id, context_id, user, ident)
        except Exception:
            if committed:
                return _pending(ident)
            raise

    @router.get('/{context_id}/reviews')
    def review_history(matter_id: str, analysis_id: str, context_id: str, request: Request, user=Depends(authenticate),
                       limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            _require(store, session, matter_id, analysis_id, context_id, user)
            prefix = 'sar-' + digest(context_id)[:20] + '-'
            rows = session.scalars(select(Record).where(Record.kind == REVIEW, Record.matter_id == matter_id,
                Record.firm_id == user.firm_id, Record.id.startswith(prefix))
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            return [{'id': row.id, 'recorded_by': row.owner_id, 'recorded_at': row.created_at} for row in rows]

    @router.get('/{context_id}/reviews/{review_id}')
    def review_detail(matter_id: str, analysis_id: str, context_id: str, review_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            return _read(request.app, session, matter_id, analysis_id, context_id, user, review_id)

    @router.get('/{context_id}/export')
    def export(matter_id: str, analysis_id: str, context_id: str, request: Request,
               format: Literal['json', 'docx', 'pdf'] = 'json', user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            _, packet, _, _ = _require(store, session, matter_id, analysis_id, context_id, user)
            with _operation(app, session, matter_id, analysis_id, packet['manifest']['version_id'], packet['manifest']['product_id'], user) as prepared:
                value = _inspect(app, session, matter_id, analysis_id, context_id, user, prepared)
                if not value['public_source_access'] or value['review']['effective_state'] != 'reviewed_conditional':
                    raise HTTPException(409, 'Güncel bağımsız olumlu inceleme gerekli; dışa aktarım durduruldu.')
                response = (Response(canonical(value), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="private-source-analysis-{context_id}.json"'})
                    if format == 'json' else render_export(_export_lines(value), context_id, format))
                session.expire_all()
                if _inspect(app, session, matter_id, analysis_id, context_id, user, prepared) != value:
                    raise HTTPException(409, 'Dışa aktarım sırasında inceleme dayanakları değişti.')
                require_child(session, context_id, KIND, matter_id, user)
            _post_review_check(store, session, matter_id, analysis_id, context_id, user, packet, value)
            require_child(session, context_id, KIND, matter_id, user)
            return response

    return router
