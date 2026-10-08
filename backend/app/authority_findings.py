"""Immutable lawyer observations, scoped to an exact private/public context.

Recorded judgments never become source approval, applicability inference or a
qualification score. Public bytes and free-text observations share the guard.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, StrictInt, model_validator
from sqlalchemy import func, select

from . import analysis_authorities as authorities
from .auth import authenticate, require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .exports import render_export
from .practice import StrictInput, _audit

RECIPE = 'private-authority-findings-v1'
SUPPORTED_RECIPES = {RECIPE}
KIND = 'analysis_authority_review'
HEAD = 'authority_review_head'
ADMISSION = 'authority_review_admission'
SCOPE = 'lawyer_observations_on_selected_authorities_only'
MAX_BYTES = 2 * 1024 * 1024
MAX_REVIEWS = 100
DIMENSIONS = {
    'applicability': 'Somut olgu, taraf ve usul konumuna uygulanabilirlik',
    'history': 'Hüküm sürümü, olay tarihi ve geçiş hükümleri',
    'conditions': 'Maddi koşullar, istisnalar ve eksik unsurlar',
    'relationship': 'Atıf, uygulama, ayrım ve hukuki etki sınırları',
    'adverse': 'Karşı dayanaklar, farklı yorumlar ve araştırma kapsamı',
    'certainty': 'Sonuç gücü, belirsizlik ve eksik kanıt',
}
Dimension = Literal['applicability', 'history', 'conditions', 'relationship', 'adverse', 'certainty']


class Observation(StrictInput):
    dimension: Dimension
    outcome: Literal['supported', 'needs_change', 'unresolved', 'not_assessed']
    note: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def explained(self):
        if len(self.note.strip()) < 3:
            raise ValueError('Explain every observation, including unknowns')
        return self


class SourceAssessment(StrictInput):
    assertion_id: str = Field(min_length=1, max_length=512)
    passage_id: str = Field(min_length=1, max_length=512)
    authority_id: str = Field(min_length=1, max_length=512)
    target_ids: list[str] = Field(min_length=1, max_length=12)
    observations: list[Observation] = Field(min_length=6, max_length=6)

    @model_validator(mode='after')
    def distinct(self):
        if (len(set(self.target_ids)) != len(self.target_ids)
                or any(not 1 <= len(value) <= 129 for value in self.target_ids)
                or {item.dimension for item in self.observations} != set(DIMENSIONS)):
            raise ValueError('Use distinct exact targets and all six dimensions')
        return self


class Assessment(StrictInput):
    sources: list[SourceAssessment] = Field(min_length=1, max_length=8)
    note: str = Field(min_length=3, max_length=2000)
    review_seconds: StrictInt | None = Field(default=None, ge=1, le=28800)

    @model_validator(mode='after')
    def bounded(self):
        if (len({_identity(item.model_dump()) for item in self.sources}) != len(self.sources)
                or len(self.note.strip()) < 3 or len(canonical(self.model_dump()).encode()) > 128 * 1024):
            raise ValueError('Use distinct explained source assessments within 128 KiB')
        return self


class Save(Assessment):
    expected_basis_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_review_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')


def _identity(value):
    return tuple(value[key] for key in authorities.IDENTITY)


def _prefix(ident):
    return 'aaf-' + digest(ident)[:24] + '-'


def _head_id(ident):
    return 'afh-' + digest(ident)[:32]


def _admission_id(ident):
    return 'afa-' + digest(ident)[:32]


def _bounded(value, *, reserve=0):
    if len(canonical(value).encode()) + reserve > MAX_BYTES:
        raise HTTPException(409, 'Dayanak incelemesi 2 MiB sınırını aşıyor; kısmi kayıt oluşturulamaz.')
    return value


def _lawyer(session, matter_id, user):
    require_matter(session, matter_id, user)
    current = session.get(User, user.id, populate_existing=True)
    if current.role not in {'lawyer', 'admin'}:
        raise HTTPException(403, 'Bu kayıt için avukat çalışma rolü gerekli.')
    return current


def _head(store, session, matter_id, analysis_id, context_id, user):
    row = session.get(Record, _head_id(context_id), populate_existing=True)
    if not row:
        return None
    row = require_child(session, row.id, HEAD, matter_id, user)
    data = store.decode(row)
    if (data.get('analysis_id') != analysis_id or data.get('context_id') != context_id
            or not data.get('latest_review_id', '').startswith(_prefix(context_id))):
        raise HTTPException(409, 'Dayanak incelemesinin sırası doğrulanamadı.')
    _, latest, _, _ = _require(store, session, matter_id, analysis_id, context_id, data['latest_review_id'], user)
    if latest['sequence'] != data.get('sequence'):
        raise HTTPException(409, 'Dayanak incelemesinin sırası eşleşmiyor.')
    return data


def _public_data(app, session, matter_id, analysis_id, context_id, user):
    _, data, _, _ = authorities._require(app.state.store, session, matter_id, analysis_id, context_id, user)
    return authorities._product(app.state.store, session, matter_id, data['manifest']['product_id'], user,
                                allow_stale=True)[1]


def _basis(value):
    return digest(canonical({'context_id': value['id'], 'context_manifest_sha256': value['manifest_sha256'],
        'context_packet_sha256': value['packet_sha256'], 'context_recipe': authorities.RECIPE,
        'recipe': RECIPE, 'dimensions': DIMENSIONS}))


def _context(app, session, matter_id, analysis_id, context_id, user):
    value = authorities._view(app, session, matter_id, analysis_id, context_id, user)
    if not value['public_source_access'] or value['freshness']['status'] != 'current':
        raise HTTPException(409, 'Güncel ve izinli kaynak bağlamı gerekli; yeni inceleme kaydedilemez.')
    head = _head(app.state.store, session, matter_id, analysis_id, context_id, user)
    matter = require_matter(session, matter_id, user)
    return _bounded({'authority_context': value, 'basis_sha256': _basis(value),
        'expected_review_id': head['latest_review_id'] if head else None,
        'dimensions': DIMENSIONS, 'recipe': RECIPE, 'scope': SCOPE,
        'can_record': app.state.store.decode(matter).get('status') != 'archived',
        'qualification_granted': False}, reserve=2048)


def _validate(body, value):
    expected = {_identity(item['selection']): set(item['selection']['target_ids'])
                for item in value['manifest']['sources']}
    actual = {_identity(item.model_dump()): set(item.target_ids) for item in body.sources}
    if actual != expected:
        raise HTTPException(422, 'Her kaynak ilişkisi ve bağlı taslak adımları tam olarak değerlendirilmelidir.')


def _require(store, session, matter_id, analysis_id, context_id, review_id, user):
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    row = require_child(session, review_id, KIND, matter_id, user)
    data = store.decode(row)
    admission = require_child(session, _admission_id(review_id), ADMISSION, matter_id, user)
    proof = store.decode(admission)
    try:
        if (data['review_sha256'] != digest(canonical({key: value for key, value in data.items() if key != 'review_sha256'}))
                or data['analysis_id'] != analysis_id or data['context_id'] != context_id
                or data['context_snapshot']['id'] != context_id
                or data['context_snapshot']['manifest_sha256'] != data['context_manifest_sha256']
                or data['recipe'] not in SUPPORTED_RECIPES or data['scope'] != SCOPE
                or row.owner_id != data['reviewer_id'] or admission.owner_id != row.owner_id
                or proof['review_id'] != row.id or proof['review_sha256'] != data['review_sha256']):
            raise ValueError('Invalid authority review binding')
    except (ValueError, KeyError, TypeError):
        raise HTTPException(409, 'Saklanan dayanak incelemesinin bütünlüğü doğrulanamadı.') from None
    return row, data, admission, proof


def _view(app, session, matter_id, analysis_id, context_id, review_id, user):
    store = app.state.store
    row, data, _, proof = _require(store, session, matter_id, analysis_id, context_id, review_id, user)
    result = {'id': row.id, 'context_id': context_id, 'sequence': data['sequence'],
        'reviewer_id': data['reviewer_id'], 'reviewer_name': data['reviewer_name'],
        'recorded_at': data['recorded_at'], 'review_sha256': data['review_sha256'],
        'snapshot': None, 'public_source_access': False, 'is_latest_review': False,
        'freshness': {'status': 'withheld', 'reasons': []}, 'qualification_granted': False,
        'legal_approval': 'not_granted', 'runtime_authorization': 'none'}
    if not proof.get('publication_guard_completed'):
        result['freshness']['reasons'] = ['post_commit_authorization_pending']
        return result
    try:
        public = _public_data(app, session, matter_id, analysis_id, context_id, user)
        with authorities._guard(app, public):
            context = authorities._view(app, session, matter_id, analysis_id, context_id, user)
            if (not context['public_source_access'] or context['manifest'] is None
                    or context['manifest_sha256'] != data['context_manifest_sha256']
                    or context['packet_sha256'] != data['context_snapshot']['packet_sha256']):
                raise HTTPException(409)
            reasons = []
            if context['freshness']['status'] != 'current':
                reasons.append('authority_context_changed')
            if _basis(context) != data['basis_sha256']:
                reasons.append('assessment_recipe_changed')
            head = _head(store, session, matter_id, analysis_id, context_id, user)
            latest = bool(head and head['latest_review_id'] == row.id)
            if not latest:
                reasons.append('newer_review_exists')
            reviewer = session.get(User, data['reviewer_id'], populate_existing=True)
            try:
                if not reviewer or reviewer.role not in {'lawyer', 'admin'}:
                    raise HTTPException(403)
                require_matter(session, matter_id, reviewer)
            except HTTPException:
                reasons.append('reviewer_access_changed')
            result.update(snapshot=data, public_source_access=True, is_latest_review=latest,
                          freshness={'status': 'stale' if reasons else 'current', 'reasons': reasons})
        require_child(session, review_id, KIND, matter_id, user)
        return _bounded(result)
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        # Notes may themselves quote sources; withhold them with the public bytes.
        require_child(session, review_id, KIND, matter_id, user)
        result.update(snapshot=None, public_source_access=False,
                      freshness={'status': 'withheld', 'reasons': ['public_context_unavailable']})
        return result


def _finalize(app, matter_id, analysis_id, context_id, review_id, user):
    store = app.state.store
    with store.session() as session:
        matter = require_matter(session, matter_id, user)
        session.refresh(matter, with_for_update=True)
        _lawyer(session, matter_id, user)
        row, _, admission, proof = _require(store, session, matter_id, analysis_id, context_id, review_id, user)
        if row.owner_id != user.id:
            raise HTTPException(403)
        proof.update(publication_guard_completed=True, completed_at=now())
        store.update(admission, proof)
        session.commit()


def _lines(value):
    data = value['snapshot']
    lines = ['GİZLİ — AVUKAT KAMU DAYANAK İNCELEMESİ',
        f"İnceleyen: {data['reviewer_name']} · Sıra: {data['sequence']}",
        'Bu kayıt kaynak onayı, hukuki yeterlilik veya makine uygulanabilirlik kararı değildir.',
        'İnceleme SHA-256: ' + value['review_sha256'], 'Bağlam SHA-256: ' + data['context_manifest_sha256'],
        'Avukat notu: ' + data['assessment']['note'],
        'Beyan edilen inceleme süresi (saniye): ' + str(data['assessment']['review_seconds'])]
    for source in data['assessment']['sources']:
        lines.extend(['Kaynak ilişkisi: ' + canonical({key: source[key] for key in authorities.IDENTITY}),
                      'Taslak hedefleri: ' + ', '.join(source['target_ids'])])
        lines.extend(data['dimensions'][item['dimension']] + ': ' + item['outcome'] + ' · ' + item['note']
                     for item in source['observations'])
    return lines + authorities._export_lines(data['context_snapshot'])


def authority_findings_router():
    router = APIRouter(prefix='/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews',
                       tags=['private-authority-findings'])

    @router.get('/context')
    def context(matter_id: str, analysis_id: str, context_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            _lawyer(session, matter_id, user)
            value = _context(request.app, session, matter_id, analysis_id, context_id, user)
            _lawyer(session, matter_id, user)
            return value

    @router.get('')
    def listing(matter_id: str, analysis_id: str, context_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            authorities._require(store, session, matter_id, analysis_id, context_id, user)
            rows = session.scalars(select(Record).where(Record.kind == KIND, Record.matter_id == matter_id,
                Record.firm_id == user.firm_id, Record.id.startswith(_prefix(context_id)))
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            result = []
            for row in rows:
                _, data, _, _ = _require(store, session, matter_id, analysis_id, context_id, row.id, user)
                result.append({key: data[key] for key in ('sequence', 'reviewer_name', 'recorded_at') } | {'id': row.id})
            return result

    @router.post('', status_code=201)
    def save(matter_id: str, analysis_id: str, context_id: str, body: Save, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        ident = _prefix(context_id) + digest(user.id + ':' + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={'request_id'})))
        assessment = body.model_dump(exclude={'request_id', 'expected_basis_sha256', 'expected_review_id'})
        committed = False
        try:
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                current_user = _lawyer(session, matter_id, user)
                authorities._require(store, session, matter_id, analysis_id, context_id, user)
                existing = session.get(Record, ident)
                if existing:
                    _, data, _, _ = _require(store, session, matter_id, analysis_id, context_id, ident, user)
                    if data['request_sha256'] != request_sha or existing.owner_id != user.id:
                        raise HTTPException(409, 'İstek kimliği başka bir incelemeye bağlı.')
                    return _view(app, session, matter_id, analysis_id, context_id, ident, user)
                if store.decode(matter).get('status') == 'archived':
                    raise HTTPException(409, 'Arşivlenmiş çalışma alanında yeni inceleme kaydedilemez.')
                public = _public_data(app, session, matter_id, analysis_id, context_id, user)
                with authorities._guard(app, public):
                    context = _context(app, session, matter_id, analysis_id, context_id, user)
                    if (body.expected_basis_sha256 != context['basis_sha256']
                            or body.expected_review_id != context['expected_review_id']):
                        raise HTTPException(409, 'Bağlam veya inceleme sırası değişti; inceleme girdilerini yenileyin.')
                    value = context['authority_context']
                    _validate(body, value)
                    total = session.scalar(select(func.count()).select_from(Record).where(
                        Record.kind == KIND, Record.matter_id == matter_id, Record.id.startswith(_prefix(context_id))))
                    if total >= MAX_REVIEWS:
                        raise HTTPException(409, 'Bu bağlamın 100 inceleme sınırına ulaşıldı; geçmiş sessizce atlanamaz.')
                    head = _head(store, session, matter_id, analysis_id, context_id, user)
                    sequence = head['sequence'] + 1 if head else 1
                    data = {'recipe': RECIPE, 'scope': SCOPE, 'context_id': context_id, 'analysis_id': analysis_id,
                        'context_manifest_sha256': value['manifest_sha256'], 'context_snapshot': value,
                        'basis_sha256': context['basis_sha256'], 'assessment': assessment, 'dimensions': context['dimensions'],
                        'previous_review_id': body.expected_review_id, 'sequence': sequence,
                        'reviewer_id': current_user.id, 'reviewer_name': current_user.name, 'recorded_at': now(),
                        'request_sha256': request_sha, 'immutable': True, 'qualification_granted': False,
                        'legal_approval': 'not_granted', 'model_use': 'none', 'runtime_authorization': 'none'}
                    data['review_sha256'] = digest(canonical(data))
                    _bounded(data, reserve=2048)
                    store.add(session, KIND, user, data, matter_id, record_id=ident)
                    store.add(session, ADMISSION, user, {'review_id': ident, 'review_sha256': data['review_sha256'],
                        'publication_guard_completed': False}, matter_id, record_id=_admission_id(ident))
                    pointer = {'analysis_id': analysis_id, 'context_id': context_id, 'latest_review_id': ident, 'sequence': sequence}
                    if head:
                        store.update(session.get(Record, _head_id(context_id)), pointer)
                    else:
                        store.add(session, HEAD, user, pointer, matter_id, record_id=_head_id(context_id))
                    _audit(session, user, 'authority_findings_recorded', ident, matter_id)
                    session.flush()
                    session.expire_all()
                    latest = _context(app, session, matter_id, analysis_id, context_id, user)
                    if latest['basis_sha256'] != body.expected_basis_sha256 or latest['expected_review_id'] != ident:
                        raise HTTPException(409, 'Kayıt sırasında incelemenin dayanakları değişti.')
                    _lawyer(session, matter_id, user)
                    if store.decode(require_matter(session, matter_id, user)).get('status') == 'archived':
                        raise HTTPException(409, 'Çalışma alanı arşivlendi.')
                    session.commit()
                    committed = True
            _finalize(app, matter_id, analysis_id, context_id, ident, user)
            with store.session() as session:
                return _view(app, session, matter_id, analysis_id, context_id, ident, user)
        except Exception:
            if not committed:
                raise
            return JSONResponse(status_code=409, content={'detail': 'İnceleme kaydedildi; son izin kontrolü tamamlanamadı. Yeni bağlam incelemesi gerekli.',
                'outcome': 'committed_needs_revalidation', 'needs_revalidation': True, 'id': ident})

    @router.get('/{review_id}')
    def detail(matter_id: str, analysis_id: str, context_id: str, review_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            return _view(request.app, session, matter_id, analysis_id, context_id, review_id, user)

    @router.get('/{review_id}/export')
    def export(matter_id: str, analysis_id: str, context_id: str, review_id: str, request: Request,
               format: Literal['json', 'docx', 'pdf'] = 'json', user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            value = _view(app, session, matter_id, analysis_id, context_id, review_id, user)
            if not value['public_source_access'] or value['freshness']['status'] != 'current':
                raise HTTPException(409, 'Güncel ve izinli son inceleme gerekli; aktarım durduruldu.')
            public = _public_data(app, session, matter_id, analysis_id, context_id, user)
            with authorities._guard(app, public):
                response = (Response(canonical(value), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="private-authority-review-{review_id}.json"'})
                    if format == 'json' else render_export(_lines(value), review_id, format))
                session.expire_all()
                latest = _view(app, session, matter_id, analysis_id, context_id, review_id, user)
                if (latest['freshness']['status'] != 'current' or not latest['public_source_access']
                        or latest['review_sha256'] != value['review_sha256']):
                    raise HTTPException(409, 'Aktarım sırasında incelemenin dayanakları değişti.')
            require_child(session, review_id, KIND, matter_id, user)
            return response

    return router
