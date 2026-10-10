"""Human renewal of retained source bindings; never legal/source approval.

Original dependency guards always run. Immutable renewals cover an exact draft,
all inherited contexts, observed review heads and a currently authorized reviewer.
"""
from contextlib import ExitStack
from copy import deepcopy
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator

from . import analysis_authorities as authorities
from . import authority_findings as findings
from . import authority_proposals as proposals
from .analysis_adjudication import target_values
from .analysis_workbench import AnalysisInput, _freshness, _view
from .auth import authenticate, require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .firm_rbac import require_permission
from .practice import VersionInput, _audit, _invalidate, _write_version

RECIPE = 'retained-authority-binding-renewal-v1'
KIND = 'authority_lineage_revalidation'
ADMISSION = 'authority_lineage_admission'
MAX_RECORDS = 20
MAX_BYTES = 2 * 1024 * 1024
RECOVERABLE = {'authority_review_changed', 'authority_reviewer_access_changed'}


def _bounded(value):
    if len(canonical(value).encode()) > MAX_BYTES:
        raise HTTPException(409, 'Yeniden inceleme kaydı 2 MiB sınırını aşıyor; içerik kesilemez.')
    return value


def draft_sha(content):
    keys = (set(AnalysisInput.model_fields) - {'expected_revision', 'change_note'}) | {
        'evidence', 'fact_snapshots', 'source_snapshots', 'contradiction_snapshots', 'checks',
        'ai_assistance', 'authority_contributions'}
    return digest(canonical({key: content.get(key) for key in sorted(keys)}))


def _lawyer(session, matter_id, user):
    findings._lawyer(session, matter_id, user)
    require_permission(session, user, 'matter.review')


class Renewal(findings.Assessment):
    dependency_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class Save(VersionInput):
    version_id: str = Field(min_length=1, max_length=128)
    expected_preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    decision: str = Field(pattern=r'^retain_for_review$')
    renewals: list[Renewal] = Field(min_length=1, max_length=proposals.MAX_DEPENDENCIES)

    @model_validator(mode='after')
    def complete(self):
        if len({item.dependency_sha256 for item in self.renewals}) != len(self.renewals):
            raise ValueError('Duplicate dependency')
        if len(canonical(self.model_dump()).encode()) > 256 * 1024:
            raise ValueError('Review input exceeds 256 KiB')
        return self


def _require(store, session, matter_id, analysis_id, ref, user):
    row = require_child(session, ref['id'], KIND, matter_id, user)
    value = store.decode(row)
    snapshot = value.get('snapshot', {})
    proof = store.decode(require_child(session, value.get('admission_id', ''), ADMISSION, matter_id, user))
    if (value.get('sha256') != digest(canonical(snapshot)) or value.get('sha256') != ref.get('sha256')
            or snapshot.get('analysis_id') != analysis_id or snapshot.get('reviewer_id') != row.owner_id
            or not proof.get('completed') or proof.get('sha256') != value['sha256']
            or proof.get('record_id') != row.id or proof.get('version_id') != value.get('version_id')
            or snapshot.get('recipe') != RECIPE):
        raise HTTPException(409, 'Yeniden inceleme mührü veya son izin kontrolü doğrulanamadı.')
    version = require_child(session, value['version_id'], 'practice_version', matter_id, user)
    version_data = store.decode(version)
    if (version_data.get('entity_id') != analysis_id or version_data.get('entity_kind') != 'practice_analysis'
            or ref not in version_data.get('content', {}).get('authority_revalidations', [])):
        raise HTTPException(409, 'Yeniden inceleme sürüm bağı doğrulanamadı.')
    proposals.check_admission(store, session, matter_id, user, version_data['content'])
    return value


def records(store, session, matter_id, user, content):
    refs = content.get('authority_revalidations', [])
    if not isinstance(refs, list) or len(refs) > MAX_RECORDS:
        raise HTTPException(409, 'Yeniden inceleme geçmişi doğrulanamadı.')
    deps = proposals.dependencies(content)
    if refs and not deps:
        raise HTTPException(409, 'Yeniden inceleme kaynak bağı yok.')
    values = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict) or set(ref) != {'id', 'sha256'}:
            raise HTTPException(409, 'Yeniden inceleme bağı doğrulanamadı.')
        value = _require(store, session, matter_id, deps[0]['analysis_id'], ref, user)
        snap = value['snapshot']
        if snap.get('sequence') != index + 1 or snap.get('previous') != (refs[index - 1] if index else None):
            raise HTTPException(409, 'Yeniden inceleme sırası doğrulanamadı.')
        values.append(value)
    return values


def observed_heads(store, session, matter_id, user, deps):
    return [{ 'dependency_sha256': digest(canonical(dep)), 'head': findings._head(
        store, session, matter_id, dep['analysis_id'], dep['context_id'], user)} for dep in deps]


def projected_reasons(app, session, matter_id, user, content, reasons):
    values = records(app.state.store, session, matter_id, user, content)
    if not values:
        return reasons
    snap = values[-1]['snapshot']
    current = []
    if snap['draft_sha256'] != draft_sha(content):
        current.append('authority_revalidated_analysis_changed')
    deps = proposals.dependencies(content)
    if snap['dependencies'] != deps or snap['heads'] != observed_heads(app.state.store, session, matter_id, user, deps):
        current.append('authority_revalidation_review_changed')
    reviewer = session.get(User, snap['reviewer_id'], populate_existing=True)
    try:
        if not reviewer:
            raise HTTPException(403)
        _lawyer(session, matter_id, reviewer)
    except HTTPException:
        current.append('authority_revalidation_reviewer_access_changed')
    if (snap['recipes'] != [proposals.RECIPE, authorities.RECIPE, findings.RECIPE]
            or snap['dimensions'] != findings.DIMENSIONS):
        current.append('authority_revalidation_recipe_changed')
    return list(dict.fromkeys([*reasons, *current])) if current else [item for item in reasons if item not in RECOVERABLE]


def _preview(app, session, matter_id, analysis_id, user):
    store = app.state.store
    _lawyer(session, matter_id, user)
    if store.decode(require_matter(session, matter_id, user)).get('status') == 'archived':
        raise HTTPException(409, 'Arşivlenen çalışma alanında yeniden inceleme kaydedilemez.')
    row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    session.refresh(row)
    content = store.decode(row)
    proposals.check_admission(store, session, matter_id, user, content)
    deps = proposals.dependencies(content)
    if not deps or any(dep['analysis_id'] != analysis_id for dep in deps):
        raise HTTPException(409, 'Bu taslakta yeniden incelenecek saklanmış kamu katkısı yok.')
    private = _freshness(store, session, matter_id, user, content, include_authorities=False)
    if private['status'] != 'current':
        raise HTTPException(409, 'Özel olgu veya belgeler değişti; önce yeni taslak sürümü yazın.')
    previous = records(store, session, matter_id, user, content)
    if len(previous) >= MAX_RECORDS:
        raise HTTPException(409, 'Bu analizde 20 yeniden inceleme kaydı sınırına ulaşıldı.')
    entries, reasons = [], []
    with ExitStack() as guards:
        for dep in deps:
            stale = guards.enter_context(proposals.dependency_guard(app, session, matter_id, user, dep))
            if set(stale) - RECOVERABLE:
                raise HTTPException(409, 'Kaynak inceleme sözleşmesi değişti; bu akışla yenilenemez.')
            reasons.extend(stale)
            _, context, _, _ = authorities._require(store, session, matter_id, analysis_id, dep['context_id'], user)
            entries.append({'dependency': dep, 'dependency_sha256': digest(canonical(dep)),
                            'manifest': context['manifest'], 'stale_reasons': stale})
        value = _bounded({'recipe': RECIPE, 'analysis_id': analysis_id, 'version_id': content['latest_version_id'],
            'expected_revision': row.revision, 'draft_sha256': draft_sha(content),
            'analysis_content': {key: val for key, val in content.items() if key not in {
                'authority_revalidations', 'authority_admission_id', 'latest_version_id', 'updated_at', 'version'}},
            'dependencies': deps, 'heads': observed_heads(store, session, matter_id, user, deps),
            'recipes': [proposals.RECIPE, authorities.RECIPE, findings.RECIPE], 'dimensions': findings.DIMENSIONS,
            'targets': target_values(content), 'entries': entries, 'original_stale_reasons': list(dict.fromkeys(reasons)),
            'previous': content.get('authority_revalidations', [])[-1] if previous else None,
            'sequence': len(previous) + 1, 'model_use': 'none', 'legal_approval': 'not_granted',
            'source_approval': 'not_granted', 'qualification_granted': False,
            'scope': 'retained_source_bindings_for_exact_draft_only'})
        return row, value, digest(canonical(value))


def _validate(body, preview):
    if {item.dependency_sha256 for item in body.renewals} != {item['dependency_sha256'] for item in preview['entries']}:
        raise HTTPException(422, 'Her saklanan kamu katkısını ayrı ayrı inceleyin.')
    for renewal in body.renewals:
        entry = next(item for item in preview['entries'] if item['dependency_sha256'] == renewal.dependency_sha256)
        sources = {findings._identity(item['selection']) for item in entry['manifest']['sources']}
        if {findings._identity(item.model_dump()) for item in renewal.sources} != sources:
            raise HTTPException(422, 'Seçilen bağlamın bütün kaynakları incelenmelidir.')
        if any(not set(item.target_ids) <= set(preview['targets']) for item in renewal.sources):
            raise HTTPException(422, 'Kaynağı güncel taslağın mevcut hedeflerine bağlayın.')


def export_lines(store, session, matter_id, user, content):
    values = records(store, session, matter_id, user, content)
    lines = []
    for value in values:
        snap = value['snapshot']
        lines.extend([f"Saklanan kaynak bağı yeniden incelemesi: {value['id']} / {value['sha256']}",
            f"İnceleyen: {snap['reviewer_name']} / {snap['reviewer_id']} / {snap['recorded_at']}",
            f"Özgün taslak sürümü: {snap['version_id']} / yeni sürüm: {value['version_id']}",
            'Hukuki veya kaynak onayı verilmez; özgün katkılar ve belirsizlikler korunur.'])
    if values:
        for renewal in values[-1]['snapshot']['renewals']:
            lines.append('Son bağ yenileme gözlemleri: ' + renewal['dependency_sha256'] + ' / ' + renewal['note'])
            for source in renewal['sources']:
                lines.append(f"Kaynak: {source['assertion_id']} / {source['passage_id']} / {source['authority_id']} / hedefler: {', '.join(source['target_ids'])}")
                lines.extend(f"{item['dimension']}: {item['outcome']} / {item['note']}" for item in source['observations'])
    return lines


def authority_revalidation_router():
    router = APIRouter(prefix='/api/v1/matters/{matter_id}/analyses/{analysis_id}/lineage-reviews', tags=['retained-source-lineage'])

    @router.get('/preview')
    def preview(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            _, value, sha = _preview(request.app, session, matter_id, analysis_id, user)
            return {'preview': value, 'preview_sha256': sha}

    @router.get('')
    def history(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            content = store.decode(row)
            proposals.check_admission(store, session, matter_id, user, content)
            with proposals.scope(app, session, matter_id, user, content):
                # Bounded history summaries; only the latest assessment is expanded.
                values = records(store, session, matter_id, user, content)
                return _bounded([{'id': item['id'], 'sha256': item['sha256'], 'version_id': item['version_id'],
                    'snapshot': {**{key: val for key, val in item['snapshot'].items() if key in {
                        'recipe', 'sequence', 'previous', 'version_id', 'reviewer_id', 'reviewer_name', 'recorded_at',
                        'draft_sha256', 'scope', 'dimensions', 'legal_approval', 'source_approval', 'qualification_granted',
                        *(['renewals'] if index == len(values) - 1 else [])}},
                        **({'entries': [{key: entry[key] for key in ('dependency', 'dependency_sha256')}
                            for entry in item['snapshot']['entries']]} if index == len(values) - 1 else {})}}
                    for index, item in enumerate(values)])

    @router.post('', status_code=201)
    def save(matter_id: str, analysis_id: str, body: Save, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        ident = 'arl-' + digest(analysis_id + user.id)[:20] + '-' + body.request_id
        request_sha = digest(canonical(body.model_dump()))
        committed = False
        try:
            with store.session() as session, ExitStack() as guards:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                _lawyer(session, matter_id, user)
                receipt = session.get(Record, ident, populate_existing=True)
                if receipt:
                    receipt = require_child(session, ident, KIND, matter_id, user)
                    val = store.decode(receipt)
                    if val['snapshot']['request_sha256'] != request_sha or receipt.owner_id != user.id:
                        raise HTTPException(409, 'İstek kimliği farklı içerikle kullanılmış.')
                    current = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
                    with proposals.scope(app, session, matter_id, user, store.decode(current)):
                        _require(store, session, matter_id, analysis_id, {'id': ident, 'sha256': val['sha256']}, user)
                        return {'id': ident, 'version_id': val['version_id'], 'replayed': True}
                row, value, sha = _preview(app, session, matter_id, analysis_id, user)
                if (body.version_id != value['version_id'] or body.expected_revision != row.revision
                        or body.expected_preview_sha256 != sha):
                    raise HTTPException(409, 'Taslak veya kaynak inceleme başı değişti; önizlemeyi yeniden açın.')
                _validate(body, value)
                for dep in value['dependencies']:
                    guards.enter_context(proposals.dependency_guard(app, session, matter_id, user, dep))
                content = deepcopy(store.decode(row))
                snapshot = _bounded({**value, 'renewals': [item.model_dump() for item in body.renewals],
                    'reviewer_id': user.id, 'reviewer_name': user.name, 'recorded_at': now(),
                    'request_sha256': request_sha, 'decision': body.decision})
                seal = digest(canonical(snapshot))
                proof_id = 'arla-' + uuid4().hex
                content['authority_revalidations'] = [*content.get('authority_revalidations', []), {'id': ident, 'sha256': seal}]
                # Re-check the exact preview before creating the new immutable version.
                session.expire_all()
                _, _, current_sha = _preview(app, session, matter_id, analysis_id, user)
                if current_sha != sha:
                    raise HTTPException(409, 'İnceleme girdileri kayıt sırasında değişti.')
                for key in ('latest_version_id', 'updated_at', 'version'):
                    content.pop(key, None)
                content.update(status='needs_review', authored_by=user.id,
                    revision_comparison={'previous_version_id': body.version_id, 'changed_sections': [],
                        'changed_dependency_groups': ['authority_revalidations'], 'checks_no_longer_triggered': [],
                        'new_check_ids': [], 'scope': 'source_binding_renewal_only'})
                admission = proposals.prepare_admission(store, session, matter_id, user, content)
                row = _write_version(store, session, user, 'practice_analysis', body, content, matter_id, row)
                version_id = store.decode(row)['latest_version_id']
                store.add(session, KIND, user, {'id': ident, 'snapshot': snapshot, 'sha256': seal,
                    'version_id': version_id, 'admission_id': proof_id}, matter_id, ident)
                store.add(session, ADMISSION, user, {'completed': False, 'record_id': ident,
                    'sha256': seal, 'version_id': version_id}, matter_id, proof_id)
                _invalidate(store, session, matter, 'Kamu bağı avukat tarafından yeniden incelendi; taslak hukuki inceleme gerektirir.')
                _audit(session, user, 'authority_lineage_revalidated', ident, matter_id)
                _lawyer(session, matter_id, user)
                session.commit()
                committed = True
                guards.close()
            # Admission stays pending if any publication guard exit failed.
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                _lawyer(session, matter_id, user)
                row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
                if store.decode(row)['latest_version_id'] != version_id:
                    raise HTTPException(409, 'Son izin kontrolünden önce taslak değişti.')
                for proof_ident, kind in ((admission, proposals.ADMISSION), (proof_id, ADMISSION)):
                    proof = require_child(session, proof_ident, kind, matter_id, user)
                    data = store.decode(proof)
                    store.update(proof, {**data, 'completed': True})
                session.commit()
                result = _view(store, session, matter_id, user, row)
                if result['freshness']['status'] != 'current':
                    raise HTTPException(409, 'Son kontrol sırasında kaynak veya taslak değişti.')
                return {'id': ident, 'version_id': version_id, 'analysis': result}
        except HTTPException as exc:
            if committed:
                return JSONResponse(status_code=409, content={'id': ident, 'needs_revalidation': True,
                    'outcome': 'committed_needs_revalidation', 'detail': str(exc.detail)})
            raise

    return router
