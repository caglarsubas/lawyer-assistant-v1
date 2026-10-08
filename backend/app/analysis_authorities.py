"""Private, immutable public-source context; no legal approval or model dispatch."""

from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field, TypeAdapter, model_validator
from sqlalchemy import select

from . import analysis_reviews, analysis_workbench
from .analysis_adjudication import target_values
from .analysis_contracts import ISODate
from .auth import authenticate, require_child, require_matter
from .db import Record, digest, now
from .evidence_prompt import canonical
from .exports import render_export
from .graph import GraphBackendError, valid_on
from .practice import StrictInput, _audit
from .research import _product_graph_pin, guard_product_graph

RECIPE = 'private-public-authority-context-v1'
SUPPORTED_RECIPES = {RECIPE}
KIND = 'analysis_authority_context'
ADMISSION = 'analysis_authority_admission'
MAX_BYTES = 1024 * 1024
IDENTITY = ('assertion_id', 'passage_id', 'authority_id')


class Selected(StrictInput):
    assertion_id: str = Field(min_length=1, max_length=512)
    passage_id: str = Field(min_length=1, max_length=512)
    authority_id: str = Field(min_length=1, max_length=512)
    target_ids: list[str] = Field(min_length=1, max_length=12)
    relationship: Literal['support_candidate', 'adverse_candidate', 'material_distinction', 'background', 'unresolved']
    note: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def targets(self):
        if len(set(self.target_ids)) != len(self.target_ids) or any(not 1 <= len(item) <= 129 for item in self.target_ids):
            raise ValueError('Use distinct bounded draft targets')
        if len(self.note.strip()) < 3:
            raise ValueError('Explain the selected relationship')
        return self


class Specification(StrictInput):
    version_id: str = Field(min_length=1, max_length=64)
    product_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=3, max_length=2000)
    selections: list[Selected] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def unique(self):
        if len({tuple(getattr(item, key) for key in IDENTITY) for item in self.selections}) != len(self.selections):
            raise ValueError('Select each evidenced authority occurrence once')
        if len(self.title.strip()) < 3 or len(self.purpose.strip()) < 3:
            raise ValueError('Describe the context and research purpose')
        return self


class Freeze(Specification):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


def _bounded(value, *, reserved_bytes=0):
    if len(canonical(value).encode()) + reserved_bytes > MAX_BYTES:
        raise HTTPException(409, 'Kamu dayanak bağlamı 1 MiB sınırını aşıyor; kısmi kayıt oluşturulamaz.')
    return value


def _analysis(store, session, matter_id, analysis_id, version_id, user):
    row, version, content, context = analysis_reviews._context(store, session, matter_id, analysis_id, version_id, user)
    return row, version, content, context


def _product(store, session, matter_id, product_id, user, *, allow_stale=False):
    row = require_child(session, product_id, 'product', matter_id, user)
    session.refresh(row)
    data = store.decode(row)
    try:
        pin = _product_graph_pin(data)
        point = TypeAdapter(ISODate).validate_python(data['authority_candidates']['snapshot']['as_of'])
        hits = data['authority_candidates']['hits']
        if pin is None or not isinstance(hits, list) or len(hits) > 40 or (not allow_stale and data['status'] in {'stale', 'invalidated'}):
            raise ValueError('Ineligible retained research')
        if len({tuple(item.get(key) for key in IDENTITY) for item in hits}) != len(hits):
            raise ValueError('Ambiguous authority occurrences')
    except (ValueError, KeyError, TypeError, GraphBackendError):
        raise HTTPException(409, 'Tarihli ve izinli kamu kaynakları içeren güncel araştırma kaydı gerekli.') from None
    return row, data, pin, point, hits


@contextmanager
def _guard(app, data):
    try:
        with guard_product_graph(data, app.state.graph):
            yield
    except (GraphBackendError, ValueError):
        raise HTTPException(409, 'Kamu kaynak sürümünün güncel yayın izni veya bütünlüğü doğrulanamadı.') from None


def _evidence(app, hit, point):
    try:
        return app.state.graph.release.authority_context(hit, as_of=point)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(409, 'Seçilen kamu pasajı imzalı kaynak ve tarih kaydıyla eşleşmiyor.') from None


def _basis(store, session, matter_id, analysis_id, content, user, review_id=None):
    # Already-stale human-readable reasons must not conceal a second change.
    identities = {analysis_id: 'practice_analysis'}
    if review_id:
        identities[review_id] = analysis_reviews.KIND
    identities.update({item['id']: 'fact' for item in content['fact_snapshots']})
    identities.update({item['document_id']: 'document' for item in content['source_snapshots']})
    records = []
    for ident, kind in sorted(identities.items()):
        row = session.get(Record, ident, populate_existing=True)
        if row and (row.matter_id != matter_id or row.firm_id != user.firm_id):
            raise HTTPException(403, 'Özel dayanağın çalışma alanı kapsamı değişti.')
        if row and row.kind != kind:
            raise HTTPException(409, 'Özel dayanağın kayıt türü değişti.')
        records.append({'id': ident, 'kind': kind, 'sha256': digest(canonical(store.view(row))) if row else None})
    return {'records': records, 'contradictions': analysis_workbench._contradictions(
        store, session, matter_id, user.firm_id, {item['id'] for item in content['fact_snapshots']}),
        'analysis_recipe': analysis_workbench.RECIPE, 'review_recipe': analysis_reviews.RECIPE}


def _preview(app, session, matter_id, analysis_id, body, user):
    store = app.state.store
    row, version, content, context = _analysis(store, session, matter_id, analysis_id, body.version_id, user)
    if not context['current_version'] or context['freshness']['status'] != 'current':
        raise HTTPException(409, 'Bağlam için güncel dayanaklı en son analiz sürümünü seçin.')
    product, data, pin, point, hits = _product(store, session, matter_id, body.product_id, user)
    targets = target_values(content)
    sources = []
    for item in body.selections:
        if not set(item.target_ids) <= set(targets):
            raise HTTPException(422, 'Bağlantı hedefleri seçilen analiz sürümünde bulunmalıdır.')
        matches = [hit for hit in hits if all(hit.get(key) == getattr(item, key) for key in IDENTITY)]
        if len(matches) != 1:
            raise HTTPException(422, 'Kamu kaynağı bu araştırmanın tam kaynak adayından seçilmelidir.')
        source = _evidence(app, matches[0], point)
        event = content['event_date']
        within = (valid_on(source['valid_from'], source['valid_to'], event,
                  end_status=source['validity_end_status'], checked_through=source['validity_checked_through'])
                  if event else None)
        version_state = (source['target_provision_version'] or {}).get('validity')
        version_within = (valid_on(version_state['start'], version_state['end'], event,
            end_status=version_state['kind'], checked_through=version_state.get('checked_through'))
            if event and version_state and version_state['kind'] != 'unknown' else None)
        sources.append({'selection': item.model_dump(), 'evidence': source,
                        'target_snapshots': {key: targets[key] for key in item.target_ids},
                        'temporal_alignment': {'research_as_of': point, 'analysis_event_date': event,
                            'dates_equal': point == event if event else None, 'within_assertion_interval': within,
                            'target_version_within_interval': version_within,
                            'applicability': 'not_assessed'}})
    manifest = {'recipe': RECIPE, 'scope': 'private_public_authority_context_only', 'matter_id': matter_id,
        'analysis_id': analysis_id, **body.model_dump(), 'analysis_revision': row.revision,
        'analysis_content_sha256': digest(canonical(content)), 'analysis_content': content,
        'analysis_review_id': context['expected_review_id'], 'private_basis': _basis(store, session, matter_id, analysis_id, content, user, context['expected_review_id']),
        'product_revision': product.revision, 'product_sha256': digest(canonical(data)),
        'graph_release_pin': pin, 'research_snapshot': data['authority_candidates']['snapshot'],
        'sources': sources, 'legal_approval': 'not_granted', 'qualification_granted': False,
        'production_qualified': False, 'runtime_authorization': 'none', 'model_use': 'none',
        'binding_effect': 'not_assessed', 'matter_applicability': 'not_assessed'}
    # Leave space for the saved response's IDs, repeated title, seals and state.
    # An accepted preview must not become unreadable solely from its envelope.
    return _bounded({'manifest': manifest, 'preview_sha256': digest(canonical(manifest))}, reserved_bytes=2048)


def _admission_id(ident):
    return 'aam-' + digest(ident)[:32]


def _require(store, session, matter_id, analysis_id, ident, user):
    row = require_child(session, ident, KIND, matter_id, user)
    value = store.decode(row)
    admission = require_child(session, _admission_id(ident), ADMISSION, matter_id, user)
    proof = store.decode(admission)
    try:
        if (value['packet_sha256'] != digest(canonical({key: item for key, item in value.items() if key != 'packet_sha256'}))
                or value['manifest_sha256'] != digest(canonical(value['manifest']))
                or value['manifest']['matter_id'] != matter_id or value['manifest']['analysis_id'] != analysis_id
                or value['manifest']['recipe'] not in SUPPORTED_RECIPES
                or proof['packet_id'] != row.id or proof['manifest_sha256'] != value['manifest_sha256']
                or admission.owner_id != row.owner_id):
            raise ValueError('Invalid context binding')
    except (KeyError, TypeError, ValueError):
        raise HTTPException(409, 'Saklanan kamu dayanak bağlamının bütünlüğü doğrulanamadı.') from None
    return row, value, admission, proof


def _view(app, session, matter_id, analysis_id, ident, user):
    store = app.state.store
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    row, value, _, proof = _require(store, session, matter_id, analysis_id, ident, user)
    manifest = value['manifest']
    result = {'id': row.id, 'title': manifest['title'], 'version_id': manifest['version_id'],
        'registered_at': value['registered_at'], 'manifest_sha256': value['manifest_sha256'],
        'packet_sha256': value['packet_sha256'], 'manifest': None, 'public_source_access': False,
        'freshness': {'status': 'withheld', 'reasons': []}, 'qualification_granted': False,
        'production_qualified': False, 'runtime_authorization': 'none'}
    if not proof.get('publication_guard_completed'):
        result['freshness']['reasons'] = ['post_commit_authorization_pending']
        return result
    # Missing records are withheld; foreign routing remains an authorization error.
    try:
        _, data, pin, point, _ = _product(store, session, matter_id, manifest['product_id'], user, allow_stale=True)
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        result['freshness']['reasons'] = ['retained_research_unavailable']
        return result
    try:
        with _guard(app, data):
            if pin != manifest['graph_release_pin']:
                raise HTTPException(409, 'Kamu yayın sürümü değişti.')
            for source in manifest['sources']:
                # Reopen the frozen nomination against the exact current release.
                current = _evidence(app, source['evidence'], source['temporal_alignment']['research_as_of'])
                if current != source['evidence']:
                    raise HTTPException(409, 'Saklanan kamu dayanağı değişti.')
            reasons = []
            _, version, content, context = _analysis(store, session, matter_id, analysis_id, manifest['version_id'], user)
            if (not context['current_version'] or context['freshness']['status'] != 'current'
                    or digest(canonical(content)) != manifest['analysis_content_sha256']
                    or context['expected_review_id'] != manifest['analysis_review_id']
                    or _basis(store, session, matter_id, analysis_id, content, user, context['expected_review_id']) != manifest['private_basis']):
                reasons.append('private_analysis_changed')
            if digest(canonical(data)) != manifest['product_sha256']:
                reasons.append('research_record_changed')
            if manifest['recipe'] != RECIPE:
                reasons.append('context_recipe_changed')
            require_child(session, ident, KIND, matter_id, user)
            require_child(session, manifest['product_id'], 'product', matter_id, user)
            result.update(manifest=manifest, public_source_access=True,
                          freshness={'status': 'stale' if reasons else 'current', 'reasons': reasons})
        require_child(session, ident, KIND, matter_id, user)
        return _bounded(result)
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        # Guard exit failures must discard all public bytes already assembled.
        result.update(manifest=None, public_source_access=False,
                      freshness={'status': 'withheld', 'reasons': ['public_authorization_or_evidence_unavailable']})
        return result


def _finalize(store, matter_id, analysis_id, ident, user):
    """Record a clean post-commit guard exit separately from immutable content.

    This is completion evidence for the original save, never ongoing permission.
    Every later inspection/export still reopens the current publication guard.
    """
    with store.session() as session:
        matter = require_matter(session, matter_id, user)
        session.refresh(matter, with_for_update=True)
        _, _, row, data = _require(store, session, matter_id, analysis_id, ident, user)
        if row.owner_id != user.id:
            raise HTTPException(403, 'Kayıt tamamlama yetkisi bulunamadı.')
        data.update(publication_guard_completed=True, completed_at=now())
        store.update(row, data)
        session.commit()


def _export_lines(view):
    value = view['manifest']
    lines = [view['title'], 'GİZLİ — KAMU DAYANAK BAĞLAMI — ' + view['freshness']['status'].upper(),
             value['purpose'], 'Bu kayıt hukuki onay, bağlayıcı etki veya somut olaya uygulanabilirlik belirlemez.',
             'Model çağrısı ve otomatik hukuki sentez yapılmaz.',
             'Analiz sürümü: ' + value['version_id'], 'Bağlam özeti: ' + view['manifest_sha256'],
             'Yayın sürümü: ' + canonical(value['graph_release_pin'])]
    for source in value['sources']:
        selected, evidence = source['selection'], source['evidence']
        lines.extend(['Avukat bağlantı beyanı: ' + selected['relationship'], selected['note'],
            'Hedefler: ' + ', '.join(selected['target_ids']), 'Saklanan analiz adımları: ' + canonical(source['target_snapshots']),
            'Araştırma/olay tarihi: ' + canonical(source['temporal_alignment']),
            'Özgün kaynak: ' + evidence['document_id'] + ' / ' + evidence['source_version_id'],
            'Özgün yer: ' + evidence['locator'] + f" / [{evidence['start_offset']}, {evidence['end_offset']})",
            evidence['text'], 'Alıntı SHA-256: ' + evidence['quote_sha256'],
            'Kaynak/çıkarılmış metin/konum SHA-256: ' + canonical({key: evidence[key] for key in ('source_sha256', 'text_sha256', 'locator_map_sha256')}),
            'Kaynakta beyan edilen ilişki: ' + evidence['predicate'],
            'Hedef tarihsel hüküm sürümü: ' + canonical(evidence['target_provision_version'])])
    lines.extend('Güncellik: ' + reason for reason in view['freshness']['reasons'])
    return lines


def authority_context_router():
    router = APIRouter(prefix='/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts', tags=['private-public-authority-context'])

    @router.get('/research-products')
    def products(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate),
                 limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            rows = session.scalars(select(Record).where(Record.kind == 'product', Record.matter_id == matter_id,
                Record.firm_id == user.firm_id).order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            return [{'id': row.id, 'title': store.decode(row)['title']} for row in rows]

    @router.get('/candidates')
    def candidates(matter_id: str, analysis_id: str, product_id: str, version_id: str, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            _, _, content, context = _analysis(store, session, matter_id, analysis_id, version_id, user)
            _, data, pin, point, hits = _product(store, session, matter_id, product_id, user)
            with _guard(app, data):
                value = _bounded({'sources': [_evidence(app, hit, point) for hit in hits], 'graph_release_pin': pin,
                    'research_as_of': point, 'analysis_event_date': content['event_date'],
                    'targets': target_values(content), 'private_freshness': context['freshness'],
                    'current_version': context['current_version'], 'legal_approval': 'not_granted'})
                require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            return value

    @router.post('/preview')
    def preview(matter_id: str, analysis_id: str, body: Specification, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            _, data, _, _, _ = _product(store, session, matter_id, body.product_id, user)
            with _guard(app, data):
                value = _preview(app, session, matter_id, analysis_id, body, user)
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            return value

    @router.post('', status_code=201)
    def freeze(matter_id: str, analysis_id: str, body: Freeze, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        spec = Specification.model_validate(body.model_dump(exclude={'request_id', 'expected_preview_sha256'}))
        ident = 'aac-' + digest(matter_id + ':' + analysis_id)[:20] + '-' + digest(user.id + ':' + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={'request_id'})))
        committed = False
        try:
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                existing = session.get(Record, ident)
                if existing:
                    _, data, _, _ = _require(store, session, matter_id, analysis_id, ident, user)
                    if existing.owner_id != user.id or data['request_sha256'] != request_sha:
                        raise HTTPException(409, 'İstek kimliği başka bir bağlama bağlı.')
                    return _view(app, session, matter_id, analysis_id, ident, user)
                if store.decode(matter).get('status') == 'archived':
                    raise HTTPException(409, 'Arşivlenmiş çalışma alanında yeni bağlam kaydedilemez.')
                _, product, _, _, _ = _product(store, session, matter_id, body.product_id, user)
                with _guard(app, product):
                    value = _preview(app, session, matter_id, analysis_id, spec, user)
                    if value['preview_sha256'] != body.expected_preview_sha256:
                        raise HTTPException(409, 'Analiz, araştırma veya bağlam beyanı değişti; önizlemeyi yenileyin.')
                    data = {'manifest': value['manifest'], 'manifest_sha256': value['preview_sha256'],
                            'request_sha256': request_sha, 'registered_at': now(), 'immutable': True}
                    data['packet_sha256'] = digest(canonical(data))
                    store.add(session, KIND, user, data, matter_id, record_id=ident)
                    store.add(session, ADMISSION, user, {'packet_id': ident, 'manifest_sha256': data['manifest_sha256'],
                        'publication_guard_completed': False}, matter_id, record_id=_admission_id(ident))
                    _audit(session, user, 'analysis_authority_context_frozen', ident, matter_id)
                    session.flush()
                    session.expire_all()
                    if _preview(app, session, matter_id, analysis_id, spec, user)['preview_sha256'] != body.expected_preview_sha256:
                        raise HTTPException(409, 'Kayıt sırasında dayanaklar değişti; önizlemeyi yenileyin.')
                    if store.decode(require_matter(session, matter_id, user)).get('status') == 'archived':
                        raise HTTPException(409, 'Çalışma alanı arşivlendi.')
                    session.commit()
                    committed = True
            _finalize(store, matter_id, analysis_id, ident, user)
            with store.session() as session:
                return _view(app, session, matter_id, analysis_id, ident, user)
        except Exception:
            if not committed:
                raise
            # A persistent pending admission survives transient recovery; no quote
            # or failed-as-unsaved claim is returned after a committed save.
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=409, content={'detail': 'Bağlam kaydedildi; son izin kontrolü tamamlanamadı. Yeni önizleme ve ayrı kayıt gerekli.',
                'outcome': 'committed_needs_revalidation', 'needs_revalidation': True, 'id': ident})

    @router.get('')
    def listing(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            prefix = 'aac-' + digest(matter_id + ':' + analysis_id)[:20] + '-'
            rows = session.scalars(select(Record).where(Record.kind == KIND, Record.matter_id == matter_id,
                Record.firm_id == user.firm_id, Record.id.startswith(prefix))
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            results = []
            for row in rows:
                _, value, _, _ = _require(store, session, matter_id, analysis_id, row.id, user)
                results.append({'id': row.id, 'title': value['manifest']['title'], 'version_id': value['manifest']['version_id']})
            return results

    @router.get('/{context_id}')
    def detail(matter_id: str, analysis_id: str, context_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            return _view(request.app, session, matter_id, analysis_id, context_id, user)

    @router.get('/{context_id}/export')
    def export(matter_id: str, analysis_id: str, context_id: str, request: Request,
               format: Literal['json', 'docx', 'pdf'] = 'json', user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            value = _view(app, session, matter_id, analysis_id, context_id, user)
            if not value['public_source_access'] or value['freshness']['status'] != 'current':
                raise HTTPException(409, 'Güncel ve izinli bağlam bulunamadı; dışa aktarım durduruldu.')
            _, data, _, _, _ = _product(store, session, matter_id, value['manifest']['product_id'], user)
            with _guard(app, data):
                response = (Response(canonical(value), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="private-authority-context-{value["id"]}.json"'})
                    if format == 'json' else render_export(_export_lines(value), value['id'], format))
                session.expire_all()
                latest = _view(app, session, matter_id, analysis_id, context_id, user)
                if not latest['public_source_access'] or latest['freshness']['status'] != 'current' or latest['manifest_sha256'] != value['manifest_sha256']:
                    raise HTTPException(409, 'Dışa aktarım sırasında bağlamın dayanakları değişti.')
                require_child(session, context_id, KIND, matter_id, user)
            require_child(session, context_id, KIND, matter_id, user)
            return response

    return router
