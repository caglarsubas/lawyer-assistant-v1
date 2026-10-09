"""Selected source-bound feedback and continuing permissions for derived text.

The immutable source review is evidence, never a model's authority to resolve it.
Admission receipts distinguish committed bytes from a clean publication exit.
"""

from contextlib import ExitStack, contextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import HTTPException
from pydantic import Field, model_validator

from . import analysis_authorities as authorities
from . import authority_findings as findings
from .analysis_feedback import editable_targets
from .auth import require_child, require_matter
from .db import User, digest
from .evidence_prompt import canonical
from .firm_rbac import require_permission
from .practice import StrictInput

RECIPE = 'source-bound-authority-proposals-v1'
ADMISSION = 'authority_proposal_admission'
MAX_DEPENDENCIES = 8


def _public_basis(public):
    # A private draft adoption stales its research wrapper. It must not change
    # the retained public nomination or release; pin those independently.
    return digest(canonical({'authority_candidates': public.get('authority_candidates'),
        'graph_paths': public.get('graph_paths'),
        'graph_release_pin': public.get('snapshots', {}).get('graph_release_pin')}))


class SelectedFinding(StrictInput):
    source_index: Annotated[int, Field(strict=True, ge=0, le=7)]
    dimension: findings.Dimension


class AuthorityFeedbackSelection(StrictInput):
    context_id: str = Field(min_length=1, max_length=64)
    review_id: str = Field(min_length=1, max_length=64)
    review_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    findings: list[SelectedFinding] = Field(min_length=1, max_length=5)

    @model_validator(mode='after')
    def distinct(self):
        if len({(item.source_index, item.dimension) for item in self.findings}) != len(self.findings):
            raise ValueError('Select distinct authority findings')
        return self


def resolve(app, session, matter_id, analysis_id, version_id, user, selection):
    findings._lawyer(session, matter_id, user)
    value = findings._view(app, session, matter_id, analysis_id, selection.context_id, selection.review_id, user)
    if (not value['public_source_access'] or value['freshness']['status'] != 'current'
            or value['review_sha256'] != selection.review_sha256 or not value['is_latest_review']):
        raise HTTPException(409, 'Güncel ve izinli son dayanak incelemesini yeniden seçin.')
    review = value['snapshot']
    context = review['context_snapshot']
    if context['manifest']['version_id'] != version_id:
        raise HTTPException(409, 'Dayanak incelemesi seçilen analiz sürümüne bağlı değil.')
    selected = []
    sources = {}
    for item in sorted(selection.findings, key=lambda item: (item.source_index, item.dimension)):
        if item.source_index >= len(review['assessment']['sources']):
            raise HTTPException(422, 'Seçilen dayanak bulgusu bu incelemede bulunamadı.')
        assessed = review['assessment']['sources'][item.source_index]
        source = next(source for source in context['manifest']['sources']
                      if findings._identity(source['selection']) == findings._identity(assessed))
        observation = next(value for value in assessed['observations'] if value['dimension'] == item.dimension)
        if observation['outcome'] not in {'needs_change', 'unresolved', 'not_assessed'}:
            raise HTTPException(422, 'Düzenleme için açık veya değişiklik gereken bir bulgu seçin.')
        ident = 'authority:' + str(item.source_index)
        sources[ident] = {'id': ident, 'selection': source['selection'], 'evidence': source['evidence'],
                         'temporal_alignment': source['temporal_alignment']}
        targets = list(dict.fromkeys(target for original in assessed['target_ids']
                                     for target in editable_targets(context['manifest']['analysis_content'], original)))
        selected.append({'finding_id': ident + ':' + item.dimension, 'authority_id': ident,
                         'dimension': item.dimension, **observation, 'target_ids': assessed['target_ids'],
                         'editable_targets': targets})
    public = findings._public_data(app, session, matter_id, analysis_id, selection.context_id, user)
    dependency = {'analysis_id': analysis_id, 'context_id': selection.context_id,
                  'review_id': selection.review_id, 'review_sha256': selection.review_sha256,
                  'context_manifest_sha256': context['manifest_sha256'],
                  'public_basis_sha256': _public_basis(public), 'recipe': RECIPE}
    snapshot = {'recipe': RECIPE, 'scope': 'selected_authority_findings_not_resolution',
                'dependency': dependency, 'findings': selected, 'sources': list(sources.values())}
    if len(canonical(snapshot).encode()) > 128 * 1024:
        raise HTTPException(409, "Seçilen dayanak girdisi 128 KiB sınırını aşıyor; metin kesilemez.")
    return snapshot, digest(canonical(snapshot))


@contextmanager
def dependency_guard(app, session, matter_id, user, dependency):
    """Validate original evidence without requiring its draft to remain latest."""
    store = app.state.store
    try:
        analysis_id, context_id = dependency['analysis_id'], dependency['context_id']
        _, review, _, admission = findings._require(
            store, session, matter_id, analysis_id, context_id, dependency['review_id'], user)
        _, context, _, context_admission = authorities._require(
            store, session, matter_id, analysis_id, context_id, user)
        if (dependency['recipe'] != RECIPE or not admission.get('publication_guard_completed')
                or not context_admission.get('publication_guard_completed')
                or review['review_sha256'] != dependency['review_sha256']
                or context['manifest_sha256'] != dependency['context_manifest_sha256']
                or review['context_manifest_sha256'] != context['manifest_sha256']):
            raise HTTPException(409)
        manifest = context['manifest']
        _, public, pin, _, _ = authorities._product(
            store, session, matter_id, manifest['product_id'], user, allow_stale=True)
        with authorities._guard(app, public):
            if pin != manifest['graph_release_pin'] or _public_basis(public) != dependency['public_basis_sha256']:
                raise HTTPException(409)
            for source in manifest['sources']:
                if authorities._evidence(app, source['evidence'], source['temporal_alignment']['research_as_of']) != source['evidence']:
                    raise HTTPException(409)
            reasons = []
            head = findings._head(store, session, matter_id, analysis_id, context_id, user)
            if not head or head['latest_review_id'] != dependency['review_id']:
                reasons.append('authority_review_changed')
            if (review['recipe'] != findings.RECIPE or review['dimensions'] != findings.DIMENSIONS
                    or manifest['recipe'] != authorities.RECIPE):
                reasons.append('authority_recipe_changed')
            reviewer = session.get(User, review['reviewer_id'], populate_existing=True)
            try:
                if not reviewer or reviewer.role not in {'lawyer', 'admin'}:
                    raise HTTPException(403)
                require_matter(session, matter_id, reviewer)
                require_permission(session, reviewer, "matter.review")
            except HTTPException:
                reasons.append('authority_reviewer_access_changed')
            yield reasons
            require_child(session, dependency['review_id'], findings.KIND, matter_id, user)
    except (KeyError, TypeError, StopIteration):
        raise HTTPException(409, 'Kamu dayanağının saklanan bağı doğrulanamadı; içerik bekletiliyor.') from None


def dependencies(state):
    content = state.get('source_content', state)
    retained = content.get('authority_dependencies', [])
    if not isinstance(retained, list) or any(not isinstance(item, dict) for item in retained):
        raise HTTPException(409, 'Saklanan kamu katkısı bağları doğrulanamadı.')
    if content.get('ai_assistance', {}).get('authority_feedback') and not retained:
        raise HTTPException(409, 'Kamu katkısının zorunlu kaynak bağları eksik.')
    contributions = content.get('authority_contributions', [])
    if (not isinstance(contributions, list) or len(contributions) > MAX_DEPENDENCIES
            or any(not isinstance(item, dict) or not isinstance(item.get('feedback'), dict)
                   or item['feedback'].get('dependency') not in retained
                   for item in contributions)
            or any(dependency not in [item['feedback']['dependency'] for item in contributions]
                   for dependency in retained)):
        raise HTTPException(409, 'Önceki kamu katkılarının kaynak bağları doğrulanamadı.')
    result = list(retained)
    feedback = state.get('authority_feedback')
    if feedback and feedback['dependency'] not in result:
        result.append(feedback['dependency'])
    if len(result) > MAX_DEPENDENCIES:
        raise HTTPException(409, 'Sekiz kamu dayanağı katkısı sınırı aşıldı; önceki bağlar atılamaz.')
    return result


def contributions(state, job_id):
    """Keep original source/model provenance visible through later revisions."""
    values = list(state['source_content'].get('authority_contributions', []))
    if state.get('authority_feedback'):
        values.append({'job_id': job_id, 'source_version_id': state['source_version_id'],
                       'provider_pin': state['provider_pin'], 'feedback': state['authority_feedback'],
                       'responses': state['authority_responses'], 'response_pass': state['authority_response_pass']})
    if len(values) > MAX_DEPENDENCIES:
        raise HTTPException(409, 'Sekiz kamu katkısı sınırı aşıldı; önceki katkılar atılamaz.')
    return values


@contextmanager
def scope(app, session, matter_id, user, state):
    with ExitStack() as stack:
        reasons = []
        for dependency in dependencies(state):
            reasons.extend(stack.enter_context(dependency_guard(app, session, matter_id, user, dependency)))
        yield list(dict.fromkeys(reasons))


def check_admission(store, session, matter_id, user, content):
    if not dependencies(content):
        return
    ident = content.get('authority_admission_id')
    if not ident:
        raise HTTPException(409, 'Kamu dayanağı içeren taslak son izin kontrolünü bekliyor.')
    proof = store.decode(require_child(session, ident, ADMISSION, matter_id, user))
    if (not proof.get('completed')
            or proof.get('dependencies_sha256') != digest(canonical(content['authority_dependencies']))):
        raise HTTPException(409, 'Kamu dayanağı içeren taslak son izin kontrolünü bekliyor.')


def prepare_admission(store, session, matter_id, user, content):
    if not dependencies(content):
        return None
    ident = 'aap-' + uuid4().hex
    content['authority_admission_id'] = ident
    store.add(session, ADMISSION, user, {'completed': False,
        'dependencies_sha256': digest(canonical(content['authority_dependencies']))}, matter_id, record_id=ident)
    return ident


def complete_admission(store, matter_id, user, ident):
    if not ident:
        return
    with store.session() as session:
        matter = require_matter(session, matter_id, user)
        session.refresh(matter, with_for_update=True)
        row = require_child(session, ident, ADMISSION, matter_id, user)
        value = store.decode(row)
        value['completed'] = True
        store.update(row, value)
        session.commit()


def freshness(store, session, matter_id, user, content):
    if not dependencies(content):
        return []
    check_admission(store, session, matter_id, user, content)
    app = getattr(store, 'authority_proposal_app', None)
    if app is None:
        raise HTTPException(409, 'Kamu dayanağı izin hizmeti erişilebilir değil.')
    with scope(app, session, matter_id, user, content) as reasons:
        return reasons
