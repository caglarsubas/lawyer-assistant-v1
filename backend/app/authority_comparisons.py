"""Human dispositions against frozen public findings and two private versions.

Current describes technical bindings, never repair, applicability or legal truth.
All free text shares the original public-source authorization boundary.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, StrictInt, model_validator
from sqlalchemy import func, select

from . import analysis_authorities as authorities
from . import analysis_reviews, analysis_workbench
from . import authority_findings as findings
from .analysis_adjudication import target_values
from .auth import authenticate, require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .exports import render_export
from .firm_rbac import require_permission
from .practice import StrictInput, _audit

RECIPE = 'private-authority-revision-comparison-v1'
SUPPORTED_RECIPES = {RECIPE}
KIND = 'authority_revision_comparison'
HEAD = 'authority_comparison_head'
ADMISSION = 'authority_comparison_admission'
SCOPE = 'human_dispositions_on_selected_authority_findings_only'
MAX_BYTES = 4 * 1024 * 1024
MAX_COMPARISONS = 100


class Disposition(StrictInput):
    source_index: StrictInt = Field(ge=0, le=7)
    dimension: findings.Dimension
    outcome: Literal['addressed', 'retained', 'removed', 'unresolved', 'not_assessed']
    note: str = Field(min_length=3, max_length=2000)
    after_target_ids: list[str] = Field(default_factory=list, max_length=12)
    private_source_refs: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def explained(self):
        if (len(self.note.strip()) < 3 or len(set(self.after_target_ids)) != len(self.after_target_ids)
                or len(set(self.private_source_refs)) != len(self.private_source_refs)
                or any(not 1 <= len(key) <= 256 for key in [*self.after_target_ids, *self.private_source_refs])):
            raise ValueError('Use explained distinct bounded references')
        return self


class Save(StrictInput):
    candidate_version_id: str = Field(min_length=1, max_length=64)
    expected_basis_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_comparison_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    dispositions: list[Disposition] = Field(min_length=6, max_length=48)
    note: str = Field(min_length=3, max_length=2000)
    review_seconds: StrictInt | None = Field(default=None, ge=1, le=28800)

    @model_validator(mode='after')
    def bounded(self):
        if (len(self.note.strip()) < 3
                or len({(item.source_index, item.dimension) for item in self.dispositions}) != len(self.dispositions)
                or len(canonical(self.model_dump()).encode()) > 128 * 1024):
            raise ValueError('Use distinct complete explained dispositions within 128 KiB')
        return self


def _prefix(review_id):
    return 'acr-' + digest(review_id)[:24] + '-'


def _head_id(review_id):
    return 'ach-' + digest(review_id)[:32]


def _admission_id(ident):
    return 'aca-' + digest(ident)[:32]


def _bounded(value, *, reserve=0):
    if len(canonical(value).encode()) + reserve > MAX_BYTES:
        raise HTTPException(409, 'Karşılaştırma 4 MiB sınırını aşıyor; kısmi kayıt oluşturulamaz.')
    return value


def _require(store, session, matter_id, analysis_id, context_id, review_id, ident, user):
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    row = require_child(session, ident, KIND, matter_id, user)
    data = store.decode(row)
    admission = require_child(session, _admission_id(ident), ADMISSION, matter_id, user)
    proof = store.decode(admission)
    try:
        if (data['comparison_sha256'] != digest(canonical({key: val for key, val in data.items() if key != 'comparison_sha256'}))
                or data['analysis_id'] != analysis_id or data['context_id'] != context_id or data['review_id'] != review_id
                or data['recipe'] not in SUPPORTED_RECIPES or data['scope'] != SCOPE
                or data['basis_sha256'] != digest(canonical(data['comparison_snapshot']))
                or row.owner_id != data['reviewer_id'] or admission.owner_id != row.owner_id
                or proof['comparison_id'] != ident or proof['comparison_sha256'] != data['comparison_sha256']):
            raise ValueError('Invalid comparison binding')
    except (KeyError, TypeError, ValueError):
        raise HTTPException(409, 'Saklanan karşılaştırmanın bütünlüğü doğrulanamadı.') from None
    return row, data, admission, proof


def _head(store, session, matter_id, analysis_id, context_id, review_id, user):
    row = session.get(Record, _head_id(review_id), populate_existing=True)
    if not row:
        return None
    row = require_child(session, row.id, HEAD, matter_id, user)
    data = store.decode(row)
    if (data.get('review_id') != review_id or not data.get('latest_comparison_id', '').startswith(_prefix(review_id))):
        raise HTTPException(409, 'Karşılaştırma sırası doğrulanamadı.')
    _, latest, _, _ = _require(store, session, matter_id, analysis_id, context_id, review_id, data['latest_comparison_id'], user)
    if latest['sequence'] != data.get('sequence'):
        raise HTTPException(409, 'Karşılaştırma sırası eşleşmiyor.')
    return data


def _without_analysis(basis, analysis_id):
    return {**basis, 'records': [item for item in basis['records'] if item['id'] != analysis_id]}


def _capture(app, session, matter_id, analysis_id, context_id, review_id, candidate_id, user):
    store = app.state.store
    review = findings._view(app, session, matter_id, analysis_id, context_id, review_id, user)
    if not review['public_source_access'] or not review['snapshot']:
        raise HTTPException(409, 'Özgün dayanak incelemesinin izinleri doğrulanamadı.')
    frozen = review['snapshot']
    context = authorities._view(app, session, matter_id, analysis_id, context_id, user)
    if not context['public_source_access'] or not context['manifest']:
        raise HTTPException(409, 'Kamu kaynak bağlamı bekletiliyor.')
    manifest = context['manifest']
    _, before = analysis_reviews._version(store, session, matter_id, analysis_id, manifest['version_id'], user)
    row, after_row, after, after_context = analysis_reviews._context(store, session, matter_id, analysis_id, candidate_id, user)
    _, after_version = analysis_reviews._version(store, session, matter_id, analysis_id, candidate_id, user)
    if after_version['version'] <= before['version'] or candidate_id == manifest['version_id']:
        raise HTTPException(409, 'Aynı analizde daha yeni bir özel taslak sürümü gerekli.')
    if digest(canonical(before['content'])) != manifest['analysis_content_sha256']:
        raise HTTPException(409, 'Özgün analiz sürümü saklanan bağlamla eşleşmiyor.')
    before_pin = analysis_reviews.review_pin(store, session, matter_id, analysis_id, manifest['version_id'], user)
    before_basis = authorities._basis(store, session, matter_id, analysis_id, before['content'], user, before_pin)
    reasons = [reason for reason in review['freshness']['reasons'] if reason != 'authority_context_changed']
    reasons.extend(reason for reason in context['freshness']['reasons'] if reason not in {'private_analysis_changed', 'research_record_changed'})
    if (before_pin != manifest['analysis_review_id']
            or _without_analysis(before_basis, analysis_id) != _without_analysis(manifest['private_basis'], analysis_id)):
        reasons.append('original_private_dependencies_changed')
    if analysis_workbench._freshness(store, session, matter_id, user, before['content'])['status'] != 'current':
        reasons.append('original_evidence_changed')
    if after_context['freshness']['status'] != 'current':
        reasons.append('candidate_evidence_changed')
    if not after_context['current_version']:
        reasons.append('newer_draft_exists')
    elif any(store.decode(row).get(key) != value for key, value in after.items()):
        reasons.append('candidate_live_content_changed')
    left, right = target_values(before['content']), target_values(after)
    comparison = {'recipe': RECIPE, 'scope': SCOPE, 'context_id': context_id, 'review_id': review_id,
        'authority_review_sha256': review['review_sha256'], 'authority_review_snapshot': frozen,
        'base_version_id': manifest['version_id'], 'base_version': before['version'],
        'base_content_sha256': manifest['analysis_content_sha256'],
        'candidate_version_id': after_row.id, 'candidate_version': after_version['version'],
        'candidate_content_sha256': digest(canonical(after)), 'candidate_content': after,
        'before_targets': left, 'after_targets': right,
        'changes': [{'target_id': key, 'before': left.get(key), 'after': right.get(key)}
                    for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)],
        'private_sources': [{'source_ref': side + ':' + item['evidence_id'], **item}
                            for side, draft in (('before', before['content']), ('after', after)) for item in draft['evidence']],
        'dimensions': findings.DIMENSIONS,
        'historical_context_changes': context['freshness']['reasons'],
        'dependencies': {'research_sha256': digest(canonical(findings._public_data(app, session, matter_id, analysis_id, context_id, user))),
            'before': before_basis, 'after': authorities._basis(store, session, matter_id, analysis_id,
            after, user, after_context['expected_review_id']), 'authority_review_latest': review['is_latest_review'],
            'reviewer_access_reasons': review['freshness']['reasons'],
            'context_reasons': context['freshness']['reasons'], 'comparison_reasons': sorted(set(reasons))},
        'qualification_granted': False, 'legal_approval': 'not_granted', 'model_use': 'none'}
    head = _head(store, session, matter_id, analysis_id, context_id, review_id, user)
    return _bounded({'comparison': comparison, 'basis_sha256': digest(canonical(comparison)),
        'expected_comparison_id': head['latest_comparison_id'] if head else None,
        'freshness': {'status': 'stale' if reasons else 'current', 'reasons': sorted(set(reasons))},
        'can_record': not reasons and store.decode(row).get('latest_version_id') == candidate_id
            and store.decode(require_matter(session, matter_id, user)).get('status') != 'archived'}, reserve=2048)


def _validate(body, capture):
    comparison = capture['comparison']
    sources = comparison['authority_review_snapshot']['assessment']['sources']
    expected = {(index, dimension) for index, source in enumerate(sources) for dimension in findings.DIMENSIONS}
    if {(item.source_index, item.dimension) for item in body.dispositions} != expected:
        raise HTTPException(422, 'Özgün incelemedeki her kaynak ve altı bulgu ayrı değerlendirilmelidir.')
    targets = set(comparison['after_targets'])
    refs = {item['source_ref'] for item in comparison['private_sources']}
    after_refs = {ref for ref in refs if ref.startswith('after:')}
    for item in body.dispositions:
        linked = set(sources[item.source_index]['target_ids'])
        selected = set(item.after_target_ids)
        if not selected <= targets or not set(item.private_source_refs) <= refs:
            raise HTTPException(422, 'Yalnız sabit sürüm adımları ve özel alıntıları seçilebilir.')
        changed = {key for key in selected if comparison['before_targets'].get(key) != comparison['after_targets'][key]}
        if item.outcome == 'addressed' and (not changed or not set(item.private_source_refs) & after_refs):
            raise HTTPException(422, 'Ele alındı beyanı gerçek yeni adım değişikliği ve yeni sürüm alıntısı gerektirir.')
        if item.outcome == 'retained' and (not linked <= selected or any(
                comparison['before_targets'].get(key) != comparison['after_targets'].get(key) for key in linked)):
            raise HTTPException(422, 'Korundu beyanı özgün bağlı adımların tümünün değişmeden kalmasını gerektirir.')
        if item.outcome == 'removed' and (linked & targets or selected):
            raise HTTPException(422, 'Çıkarıldı beyanı özgün bağlı adımların tümünün gerçekten kaldırılmasını gerektirir.')


def _view(app, session, matter_id, analysis_id, context_id, review_id, ident, user):
    store = app.state.store
    row, data, _, proof = _require(store, session, matter_id, analysis_id, context_id, review_id, ident, user)
    result = {key: data[key] for key in ('sequence', 'reviewer_name', 'reviewer_id', 'recorded_at', 'comparison_sha256')}
    result.update(id=row.id, snapshot=None, public_source_access=False, is_latest_comparison=False,
        freshness={'status': 'withheld', 'reasons': []}, qualification_granted=False, legal_approval='not_granted')
    if not proof.get('publication_guard_completed'):
        result['freshness']['reasons'] = ['post_commit_authorization_pending']
        return result
    try:
        public = findings._public_data(app, session, matter_id, analysis_id, context_id, user)
        with authorities._guard(app, public):
            current = _capture(app, session, matter_id, analysis_id, context_id, review_id,
                               data['comparison_snapshot']['candidate_version_id'], user)
            reasons = list(current['freshness']['reasons'])
            if current['basis_sha256'] != data['basis_sha256']:
                reasons.append('comparison_dependencies_changed')
            head = _head(store, session, matter_id, analysis_id, context_id, review_id, user)
            latest = bool(head and head['latest_comparison_id'] == ident)
            if not latest:
                reasons.append('newer_comparison_exists')
            reviewer = session.get(User, data['reviewer_id'], populate_existing=True)
            try:
                if not reviewer or reviewer.role not in {'lawyer', 'admin'}:
                    raise HTTPException(403)
                require_matter(session, matter_id, reviewer)
                require_permission(session, reviewer, "matter.review")
            except HTTPException:
                reasons.append('comparison_reviewer_access_changed')
            result.update(snapshot=data, public_source_access=True, is_latest_comparison=latest,
                freshness={'status': 'stale' if reasons else 'current', 'reasons': sorted(set(reasons))})
        require_child(session, ident, KIND, matter_id, user)
        return _bounded(result)
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        require_child(session, ident, KIND, matter_id, user)
        result.update(snapshot=None, public_source_access=False,
                      freshness={'status': 'withheld', 'reasons': ['comparison_context_unavailable']})
        return result


def _finalize(app, matter_id, analysis_id, context_id, review_id, ident, user):
    store = app.state.store
    with store.session() as session:
        matter = require_matter(session, matter_id, user)
        session.refresh(matter, with_for_update=True)
        findings._lawyer(session, matter_id, user)
        row, _, admission, proof = _require(store, session, matter_id, analysis_id, context_id, review_id, ident, user)
        if row.owner_id != user.id:
            raise HTTPException(403)
        proof.update(publication_guard_completed=True, completed_at=now())
        store.update(admission, proof)
        session.commit()


def _lines(value):
    data = value['snapshot']
    comparison = data['comparison_snapshot']
    lines = ['GİZLİ — DAYANAK BULGULARINA BAĞLI TASLAK KARŞILAŞTIRMASI',
        'Beyanlar avukata aittir; hukuki onay, bulgu giderme veya fayda ölçümü değildir.',
        'Karşılaştırma SHA-256: ' + data['comparison_sha256'], 'Dayanak özeti: ' + data['basis_sha256'],
        f"İnceleyen: {data['reviewer_name']} / {data['reviewer_id']}",
        f"Önceki sürüm: {comparison['base_version_id']} / {comparison['base_content_sha256']}",
        f"Yeni sürüm: {comparison['candidate_version_id']} / {comparison['candidate_content_sha256']}",
        data['assessment']['note'], 'Beyan edilen süre: ' + str(data['assessment']['review_seconds'])]
    for item in data['assessment']['dispositions']:
        source = comparison['authority_review_snapshot']['assessment']['sources'][item['source_index']]
        original = next(obs for obs in source['observations'] if obs['dimension'] == item['dimension'])
        lines.extend([f"Kaynak {item['source_index'] + 1} / {item['dimension']} / özgün: {original['outcome']}: {original['note']}",
            f"Avukat beyanı: {item['outcome']}: {item['note']}", 'Özgün adımlar: ' + ', '.join(source['target_ids']),
            'Yeni adımlar: ' + ', '.join(item['after_target_ids']), 'Özel alıntılar: ' + ', '.join(item['private_source_refs'])])
    lines.append('Adım değişiklikleri: ' + canonical(comparison['changes']))
    lines.append('Özel özgün alıntılar: ' + canonical(comparison['private_sources']))
    original = comparison['authority_review_snapshot']
    return lines + findings._lines({'snapshot': original, 'review_sha256': comparison['authority_review_sha256']})


def authority_comparisons_router():
    router = APIRouter(prefix='/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews/{review_id}/comparisons',
                       tags=['private-authority-revision-comparison'])

    @router.get('/context')
    def context(matter_id: str, analysis_id: str, context_id: str, review_id: str, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            findings._lawyer(session, matter_id, user)
            row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            public = findings._public_data(app, session, matter_id, analysis_id, context_id, user)
            with authorities._guard(app, public):
                value = _capture(app, session, matter_id, analysis_id, context_id, review_id, store.decode(row)['latest_version_id'], user)
            findings._lawyer(session, matter_id, user)
            return value

    @router.get('')
    def listing(matter_id: str, analysis_id: str, context_id: str, review_id: str, request: Request,
                user=Depends(authenticate), limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            findings._require(store, session, matter_id, analysis_id, context_id, review_id, user)
            rows = session.scalars(select(Record).where(Record.kind == KIND, Record.matter_id == matter_id,
                Record.firm_id == user.firm_id, Record.id.startswith(_prefix(review_id)))
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            result = []
            for row in rows:
                _, data, _, _ = _require(store, session, matter_id, analysis_id, context_id, review_id, row.id, user)
                result.append({key: data[key] for key in ('sequence', 'reviewer_name', 'recorded_at')} | {'id': row.id})
            return result

    @router.post('', status_code=201)
    def save(matter_id: str, analysis_id: str, context_id: str, review_id: str, body: Save, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        ident = _prefix(review_id) + digest(user.id + ':' + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={'request_id'})))
        committed = False
        try:
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                current_user = findings._lawyer(session, matter_id, user)
                findings._require(store, session, matter_id, analysis_id, context_id, review_id, user)
                if session.get(Record, ident):
                    row, data, _, _ = _require(store, session, matter_id, analysis_id, context_id, review_id, ident, user)
                    if data['request_sha256'] != request_sha or row.owner_id != user.id:
                        raise HTTPException(409, 'İstek kimliği başka bir karşılaştırmaya bağlı.')
                    return _view(app, session, matter_id, analysis_id, context_id, review_id, ident, user)
                public = findings._public_data(app, session, matter_id, analysis_id, context_id, user)
                with authorities._guard(app, public):
                    capture = _capture(app, session, matter_id, analysis_id, context_id, review_id, body.candidate_version_id, user)
                    if (not capture['can_record'] or capture['basis_sha256'] != body.expected_basis_sha256
                            or capture['expected_comparison_id'] != body.expected_comparison_id):
                        raise HTTPException(409, 'Sürüm, bulgular veya karşılaştırma sırası değişti; girdileri yenileyin.')
                    _validate(body, capture)
                    total = session.scalar(select(func.count()).select_from(Record).where(Record.kind == KIND,
                        Record.matter_id == matter_id, Record.id.startswith(_prefix(review_id))))
                    if total >= MAX_COMPARISONS:
                        raise HTTPException(409, 'Bu incelemenin 100 karşılaştırma sınırına ulaşıldı.')
                    head = _head(store, session, matter_id, analysis_id, context_id, review_id, user)
                    data = {'recipe': RECIPE, 'scope': SCOPE, 'analysis_id': analysis_id, 'context_id': context_id,
                        'review_id': review_id, 'comparison_snapshot': capture['comparison'], 'basis_sha256': capture['basis_sha256'],
                        'assessment': body.model_dump(include={'dispositions', 'note', 'review_seconds'}),
                        'previous_comparison_id': body.expected_comparison_id, 'sequence': head['sequence'] + 1 if head else 1,
                        'reviewer_id': current_user.id, 'reviewer_name': current_user.name, 'recorded_at': now(),
                        'request_sha256': request_sha, 'immutable': True, 'qualification_granted': False,
                        'legal_approval': 'not_granted', 'model_use': 'none', 'runtime_authorization': 'none'}
                    data['comparison_sha256'] = digest(canonical(data))
                    _bounded(data, reserve=2048)
                    store.add(session, KIND, user, data, matter_id, record_id=ident)
                    store.add(session, ADMISSION, user, {'comparison_id': ident, 'comparison_sha256': data['comparison_sha256'],
                        'publication_guard_completed': False}, matter_id, record_id=_admission_id(ident))
                    pointer = {'review_id': review_id, 'latest_comparison_id': ident, 'sequence': data['sequence']}
                    if head:
                        store.update(session.get(Record, _head_id(review_id)), pointer)
                    else:
                        store.add(session, HEAD, user, pointer, matter_id, record_id=_head_id(review_id))
                    _audit(session, user, 'authority_revision_compared', ident, matter_id)
                    session.flush()
                    session.expire_all()
                    latest = _capture(app, session, matter_id, analysis_id, context_id, review_id, body.candidate_version_id, user)
                    if not latest['can_record'] or latest['basis_sha256'] != body.expected_basis_sha256 or latest['expected_comparison_id'] != ident:
                        raise HTTPException(409, 'Kayıt sırasında dayanaklar değişti.')
                    findings._lawyer(session, matter_id, user)
                    session.commit()
                    committed = True
            _finalize(app, matter_id, analysis_id, context_id, review_id, ident, user)
            with store.session() as session:
                return _view(app, session, matter_id, analysis_id, context_id, review_id, ident, user)
        except Exception:
            if not committed:
                raise
            return JSONResponse(status_code=409, content={'detail': 'Karşılaştırma kaydedildi; son izin kontrolü tamamlanamadı. Yeni girdilerle ayrı kayıt gerekli.',
                'outcome': 'committed_needs_revalidation', 'needs_revalidation': True, 'id': ident})

    @router.get('/{comparison_id}')
    def detail(matter_id: str, analysis_id: str, context_id: str, review_id: str, comparison_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            return _view(request.app, session, matter_id, analysis_id, context_id, review_id, comparison_id, user)

    @router.get('/{comparison_id}/export')
    def export(matter_id: str, analysis_id: str, context_id: str, review_id: str, comparison_id: str, request: Request,
               format: Literal['json', 'docx', 'pdf'] = 'json', user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            value = _view(app, session, matter_id, analysis_id, context_id, review_id, comparison_id, user)
            if not value['public_source_access'] or value['freshness']['status'] != 'current':
                raise HTTPException(409, 'Güncel ve izinli son karşılaştırma gerekli; aktarım kapalı.')
            public = findings._public_data(app, session, matter_id, analysis_id, context_id, user)
            with authorities._guard(app, public):
                response = (Response(canonical(value), media_type='application/json', headers={
                    'Content-Disposition': f'attachment; filename="private-authority-comparison-{comparison_id}.json"'})
                    if format == 'json' else render_export(_lines(value), comparison_id, format))
                session.expire_all()
                latest = _view(app, session, matter_id, analysis_id, context_id, review_id, comparison_id, user)
                if latest['freshness']['status'] != 'current' or not latest['public_source_access'] or latest['comparison_sha256'] != value['comparison_sha256']:
                    raise HTTPException(409, 'Aktarım sırasında karşılaştırmanın dayanakları değişti.')
            require_child(session, comparison_id, KIND, matter_id, user)
            return response

    return router
