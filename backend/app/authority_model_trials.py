"""Registered same-input authority model trials; completion is never qualification."""
from contextlib import ExitStack
from datetime import datetime
from math import isfinite

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, StrictInt, model_validator
from sqlalchemy import select

from . import analysis_comparisons as private_trials
from . import analysis_reviews, analysis_suggestions
from . import authority_adjudications as semantic
from . import authority_model_inputs as inputs
from . import authority_proposals as proposals
from . import authority_revalidations as renewals
from .analysis_adjudication import target_values
from .auth import authenticate, require_child, require_matter
from .content_scope import scoped_users
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .practice import StrictInput, _audit

RECIPE = 'registered-authority-model-trial-v1'
KIND = 'authority_model_trial'
JUDGMENT = 'authority_model_observation'
EFFORT = 'authority_model_effort'
ADMISSION = 'authority_model_admission'
MAX_EVENTS = 60
MAX_PROTOCOLS = 60
MAX_BYTES = 12 * 1024 * 1024
ARMS = private_trials.ARMS


class Preview(StrictInput):
    selection: inputs.Selection


class Registration(private_trials.Registration):
    selection: inputs.Selection

    @model_validator(mode='after')
    def separate(self):
        if (self.review_feedback or any(len(value.strip()) < 3 for value in (self.title, self.question, self.rubric_text))
                or len(canonical(self.model_dump()).encode()) > 16 * 1024):
            raise ValueError('Authority trials use their own fixed source inputs within 16 KiB')
        return self


class Assessment(StrictInput):
    comparison_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    observations: list[semantic.Observation] = Field(min_length=6, max_length=6)
    judgments: list[semantic.Judgment] = Field(min_length=6, max_length=48)
    adverse_scope: semantic.AdverseScope
    note: str = Field(min_length=3, max_length=2000)
    review_seconds: StrictInt | None = Field(default=None, ge=1, le=28800)

    @model_validator(mode='after')
    def complete(self):
        if (len(self.note.strip()) < 3 or {item.dimension for item in self.observations} != set(semantic.DIMENSIONS)
                or len({(item.source_index, item.dimension) for item in self.judgments}) != len(self.judgments)
                or len(canonical(self.model_dump()).encode()) > 128 * 1024):
            raise ValueError('Complete distinct observations within 128 KiB')
        return self


class ArmObservation(StrictInput):
    arm: private_trials.Arm
    assessment: Assessment


class Observation(private_trials.Observation):
    arms: list[ArmObservation] = Field(min_length=2, max_length=2)

    @model_validator(mode='after')
    def explained(self):
        if len(self.note.strip()) < 3:
            raise ValueError('Explain the observation')
        return self


class Effort(private_trials.Effort):
    active_phases_nonoverlapping: bool = Field(strict=True)


def _prefix(kind, parent):
    return {KIND: 'amt-', JUDGMENT: 'amo-', EFFORT: 'ame-'}[kind] + digest(parent)[:20] + '-'


def _proof_id(ident):
    return 'ama-' + digest(ident)[:32]


def _bounded(value):
    if len(canonical(value).encode()) + 4096 > MAX_BYTES:
        raise HTTPException(409, 'Deneme paketi 12 MiB sınırını aşıyor; geçmiş kesilemez.')
    return value


def _require(store, session, matter_id, analysis_id, ident, user):
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    row = require_child(session, ident, KIND, matter_id, user)
    data = store.decode(row)
    admission = require_child(session, _proof_id(ident), ADMISSION, matter_id, user)
    proof = store.decode(admission)
    if (data.get('analysis_id') != analysis_id or data.get('registered_by') != row.owner_id
            or data.get('protocol_sha256') != digest(canonical({key: val for key, val in data.items() if key != 'protocol_sha256'}))
            or admission.owner_id != row.owner_id
            or proof.get('id') != ident or proof.get('sha256') != data['protocol_sha256']):
        raise HTTPException(409, 'Deneme protokol mührü doğrulanamadı.')
    return row, data, proof


def registration_context(app, session, matter_id, analysis_id, user, selection):
    store = app.state.store
    renewals._lawyer(session, matter_id, user)
    row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    content = store.view(row)
    _, version = analysis_reviews._version(store, session, matter_id, analysis_id, content['latest_version_id'], user)
    feedback, basis = inputs.resolve(app, session, matter_id, analysis_id, content['latest_version_id'], user, selection)
    excluded = {user.id, version['authored_by'], basis['reviewer_id']}
    members = []
    for member in scoped_users(session, matter_id, user.firm_id):
        if member.id in excluded:
            continue
        try:
            renewals._lawyer(session, matter_id, member)
            members.append({'id': member.id, 'name': member.name})
        except HTTPException:
            continue
    matter = require_matter(session, matter_id, user)
    value = {'selection': selection.model_dump(), 'version_id': content['latest_version_id'],
        'expected_revision': row.revision, 'source_content_sha256': digest(canonical(content)),
        'feedback': feedback, 'basis': basis, 'eligible_reviewers': sorted(members, key=lambda item: item['id']),
        'excluded_account_ids': sorted(excluded), 'provider_pin': analysis_suggestions.provider_pin(app),
        'provider_model': app.state.settings.provider_model,
        'source_review_id': analysis_reviews.review_pin(store, session, matter_id, analysis_id, content['latest_version_id'], user),
        'research_budget_seconds': app.state.settings.research_budget_seconds, 'recipe': RECIPE,
        'recipes': [inputs.RECIPE, proposals.RECIPE, renewals.RECIPE, semantic.RECIPE, analysis_reviews.RECIPE],
        'dimensions': semantic.DIMENSIONS,
        'synthetic_only': app.state.settings.demo_mode or bool(store.decode(matter).get('synthetic')),
        'can_register': len(members) >= 2 and bool(content['evidence'] and content['applications'])
            and store.decode(matter).get('status') != 'archived' and not app.state.provider.configuration_issues()}
    return {**value, 'context_sha256': digest(canonical(value))}


def _current(app, session, matter_id, user, plan):
    store = app.state.store
    operator = session.get(User, plan['registered_by'], populate_existing=True)
    if not operator or not operator.active or operator.firm_id != user.firm_id:
        raise HTTPException(409, 'Deneme sahibinin erişimi değişti.')
    renewals._lawyer(session, matter_id, operator)
    if (plan['recipe'] != RECIPE or plan['recipes'] != [inputs.RECIPE, proposals.RECIPE, renewals.RECIPE,
            semantic.RECIPE, analysis_reviews.RECIPE] or plan['dimensions'] != semantic.DIMENSIONS
            or plan['research_budget_seconds'] != app.state.settings.research_budget_seconds):
        raise HTTPException(409, 'Denemenin ölçütleri veya bütçesi değişti.')
    base = {key: val for key, val in plan.items() if key not in {'authority_feedback', 'authority_feedback_sha256'}}
    analysis_suggestions._source(app, session, matter_id, operator, base)
    row = require_child(session, plan['analysis_id'], 'practice_analysis', matter_id, user)
    if digest(canonical(store.view(row))) != plan['task_input_sha256']:
        raise HTTPException(409, 'Denemenin sabit özel taslağı değişti.')
    feedback, basis = inputs.resolve(app, session, matter_id, row.id, plan['source_version_id'], operator,
                                    inputs.Selection.model_validate(plan['selection']))
    if feedback != plan['authority_feedback'] or basis != plan['authority_basis']:
        raise HTTPException(409, 'Denemenin özgün kaynak veya insan değerlendirmesi değişti.')
    for ident in [plan['registered_by'], *plan['reviewer_ids']]:
        member = session.get(User, ident, populate_existing=True)
        try:
            if not member or not member.active or member.firm_id != user.firm_id:
                raise HTTPException(403)
            renewals._lawyer(session, matter_id, member)
        except HTTPException:
            raise HTTPException(409, 'Atanmış hesapların dosya veya inceleme izni değişti.') from None


def job_feedback(app, session, matter_id, analysis_id, user, ref):
    row, plan, proof = _require(app.state.store, session, matter_id, analysis_id, ref.id, user)
    if not proof.get('completed') or row.owner_id != user.id or ref.protocol_sha256 != plan['protocol_sha256']:
        raise HTTPException(409, 'Deneme kayıt kabulü veya sahibi doğrulanamadı.')
    _current(app, session, matter_id, user, plan)
    return plan['authority_feedback'], plan['authority_feedback_sha256']


def validate_job(app, session, matter_id, user, state):
    ref = analysis_suggestions.ComparisonReference.model_validate(state['authority_trial_ref'])
    feedback, checksum = job_feedback(app, session, matter_id, state['analysis_id'], user, ref)
    _, plan, _ = _require(app.state.store, session, matter_id, state['analysis_id'], ref.id, user)
    spec = plan['arms'][ref.arm]
    if (state.get('comparison_request_id') != spec['request_id'] or state['mode'] != spec['mode']
            or state['max_passes'] != spec['max_passes'] or state['authority_feedback'] != feedback
            or state['authority_feedback_sha256'] != checksum
            or digest(canonical(state['source_content'])) != plan['task_input_sha256']
            or ('budget_seconds' in state and state['budget_seconds'] != spec['budget_seconds'])):
        raise HTTPException(409, 'Deneme kolunun sabit girdileri veya bütçesi eşleşmiyor.')


def _events(store, session, matter_id, ident, kind, user, pending_ids=()):
    rows = session.scalars(select(Record).where(Record.kind == kind, Record.matter_id == matter_id,
        Record.id.startswith(_prefix(kind, ident), autoescape=True)).order_by(Record.created_at, Record.id).limit(MAX_EVENTS + 1))
    result = []
    for row in rows:
        row = require_child(session, row.id, kind, matter_id, user)
        data = store.decode(row)
        admission = require_child(session, _proof_id(row.id), ADMISSION, matter_id, user)
        proof = store.decode(admission)
        if (data.get('trial_id') != ident or row.owner_id != data.get('reviewer_id')
                or data.get('sha256') != digest(canonical({key: val for key, val in data.items() if key != 'sha256'}))
                or admission.owner_id != row.owner_id or proof.get('sha256') != data['sha256'] or proof.get('id') != row.id
                or (not proof.get('completed') and row.id not in pending_ids)):
            raise HTTPException(409, 'Deneme gözlem kabulü veya mührü doğrulanamadı.')
        result.append(store.view(row))
    if len(result) > MAX_EVENTS:
        raise HTTPException(409, 'Deneme geçmişi sınırı aşıldı; kayıtlar kesilemez.')
    return sorted(result, key=lambda item: item['sequence'])


def _comparison(plan, job, arm):
    before, after = plan['source_content'], job['candidate']
    left, right = target_values(before), target_values(after)
    value = {'recipe': RECIPE, 'arm': arm, 'candidate_kind': 'unadopted_model_proposal',
        'candidate_version_id': 'proposal:' + job['id'], 'candidate_content_sha256': job['candidate_sha256'],
        'base_version_id': plan['source_version_id'], 'before_targets': left, 'after_targets': right,
        'changes': [{'target_id': key, 'before': left.get(key), 'after': right.get(key)}
                    for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)],
        'private_sources': [{'source_ref': side + ':' + source['evidence_id'], **source}
                           for side, draft in (('before', before), ('after', after)) for source in draft['evidence']],
        'authority_input_sha256': digest(canonical(plan['authority_basis'])),
        'dimensions': semantic.DIMENSIONS, 'qualification_granted': False}
    return {**value, 'comparison_sha256': digest(canonical(value))}


def _capture(app, session, matter_id, analysis_id, ident, user, pending_ids=()):
    store = app.state.store
    row, plan, proof = _require(store, session, matter_id, analysis_id, ident, user)
    if not proof.get('completed') and ident not in pending_ids:
        raise HTTPException(409, 'Deneme kayıt kabulü son izin kontrolünü bekliyor.')
    reasons = []
    try:
        _current(app, session, matter_id, user, plan)
    except HTTPException as exc:
        if exc.status_code in {401, 404}:
            raise
        reasons.append(exc.detail)
    arms = {}
    for arm, spec in plan['arms'].items():
        receipt_id = analysis_id + '-' + digest(row.owner_id + ':' + spec['request_id'])[:30]
        receipt = session.get(Record, receipt_id)
        if not receipt:
            arms[arm] = {'status': 'not_started', 'job': None, 'comparison': None, 'elapsed_seconds': None,
                         'provider_round_trip_seconds': None, 'gpu_compute_seconds': None}
            continue
        receipt = require_child(session, receipt_id, analysis_suggestions.RECEIPT, matter_id, user)
        job_row = analysis_suggestions._require_job(store, session, matter_id, analysis_id, store.decode(receipt)['job_id'], user)
        job = store.view(job_row)
        if job.get('authority_publication_pending'):
            raise HTTPException(409, 'Deneme adayının kaynak izin kontrolü tamamlanmadı.')
        if job.get('authority_trial_ref') != {'id': ident, 'protocol_sha256': plan['protocol_sha256'], 'arm': arm}:
            raise HTTPException(409, 'Deneme işinin protokol bağı doğrulanamadı.')
        operator = session.get(User, row.owner_id, populate_existing=True)
        try:
            analysis_suggestions._source(app, session, matter_id, operator, job)
        except HTTPException as exc:
            reasons.append(str(exc.detail))
        if job.get('candidate') and digest(canonical(job['candidate'])) != job.get('candidate_sha256'):
            raise HTTPException(409, 'Deneme adayının mührü doğrulanamadı.')
        iterations = job.get('iterations', [])
        if len(iterations) > spec['max_passes']:
            raise HTTPException(409, 'Deneme geçiş sınırı aşıldı.')
        elapsed = None
        try:
            created, registered = datetime.fromisoformat(job['created_at']), datetime.fromisoformat(plan['registered_at'])
            if created.tzinfo is None or registered.tzinfo is None or created < registered:
                raise ValueError
            if job.get('finished_at'):
                finished = datetime.fromisoformat(job['finished_at'])
                if finished.tzinfo is None or finished < created:
                    raise ValueError
                elapsed = (finished - created).total_seconds()
        except (TypeError, ValueError, KeyError):
            reasons.append('Deneme kayıt ve iş sırası doğrulanamadı.')
        measured = bool(iterations) and all(type(item.get('provider_seconds')) in {int, float}
            and isfinite(item['provider_seconds']) and item['provider_seconds'] >= 0 for item in iterations)
        complete = job['status'] == 'completed' and bool(job.get('candidate')) and measured and elapsed is not None
        arms[arm] = {'status': job['status'], 'job': job, 'comparison': _comparison(plan, job, arm) if complete else None,
                     'elapsed_seconds': elapsed, 'provider_round_trip_seconds': sum(item['provider_seconds'] for item in iterations)
                     if complete else None, 'gpu_compute_seconds': None}
    checksum = digest(canonical({'protocol_sha256': plan['protocol_sha256'], 'jobs': {arm: item['job'] for arm, item in arms.items()}}))
    events = _events(store, session, matter_id, ident, JUDGMENT, user, pending_ids)
    effort_history = _events(store, session, matter_id, ident, EFFORT, user, pending_ids)
    latest = {item['reviewer_id']: item for item in events}
    effort = effort_history[-1] if effort_history else None
    finished = all(item['comparison'] is not None for item in arms.values())
    current = [item for reviewer, item in latest.items() if reviewer in plan['reviewer_ids']
        and item['execution_sha256'] == checksum and finished
        and item['comparison_hashes'] == {arm: result['comparison']['comparison_sha256'] for arm, result in arms.items()}]
    accounted = bool(effort and effort['execution_sha256'] == checksum and effort['shared_setup_included']
        and effort['verification_and_correction_included'] and effort['active_phases_nonoverlapping']
        and all(all(item[key] is not None for key in ('preparation_seconds', 'verification_seconds', 'correction_seconds'))
            and sum(item[key] for key in ('preparation_seconds', 'verification_seconds', 'correction_seconds')) > 0
            for item in effort['arms']))
    disagreement = []
    if len(current) == 2:
        for arm in ARMS:
            sides = [next(entry['assessment'] for entry in item['arms'] if entry['arm'] == arm) for item in current]
            for key, identity in (('observations', lambda item: item['dimension']),
                                  ('judgments', lambda item: (item['source_index'], item['dimension']))):
                left, right = [{str(identity(item)): item['outcome'] for item in side[key]} for side in sides]
                disagreement.extend({'arm': arm, 'kind': key, 'item': ident, 'outcomes': [left[ident], right[ident]]}
                                    for ident in left if left[ident] != right[ident])
    return _bounded({'id': ident, 'protocol': plan, 'execution_sha256': checksum, 'arms': arms,
        'public_source_access': True, 'freshness': {'status': 'stale' if reasons else 'current', 'reasons': list(dict.fromkeys(reasons))},
        'observations': events, 'effort_history': effort_history, 'current_reviewer_count': len(current),
        'effort_accounted': accounted, 'capture_complete': not reasons and finished and len(current) == 2 and accounted,
        'disagreement': disagreement if len(current) == 2 else None,
        'can_run': row.owner_id == user.id and not reasons and any(item['status'] == 'not_started' for item in arms.values()),
        'can_observe': user.id in plan['reviewer_ids'] and not reasons and finished,
        'can_record_effort': row.owner_id == user.id and not reasons and finished,
        'previous_observation_id': latest.get(user.id, {}).get('id'), 'previous_effort_id': effort['id'] if effort else None,
        'sample_kind': plan['sample_kind'], 'qualification_granted': False, 'benefit_established': False, 'exported_at': now()})


def _read(app, session, matter_id, analysis_id, ident, user):
    row, plan, _ = _require(app.state.store, session, matter_id, analysis_id, ident, user)
    try:
        with proposals.scope(app, session, matter_id, user, plan):
            return _capture(app, session, matter_id, analysis_id, ident, user)
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        return {'id': row.id, 'registered_at': plan['registered_at'], 'protocol_sha256': plan['protocol_sha256'],
                'protocol': None, 'arms': {}, 'observations': [], 'effort_history': [], 'public_source_access': False,
                'freshness': {'status': 'withheld', 'reasons': ['source_or_admission_unavailable']},
                'can_run': False, 'can_observe': False, 'can_record_effort': False,
                'capture_complete': False, 'qualification_granted': False, 'benefit_established': False}


def _add(store, session, kind, user, data, matter_id, ident, sha):
    store.add(session, kind, user, data, matter_id, record_id=ident)
    store.add(session, ADMISSION, user, {'id': ident, 'sha256': sha, 'completed': False}, matter_id, record_id=_proof_id(ident))


def _complete(app, matter_id, analysis_id, trial_id, ident, user):
    with app.state.store.session() as session:
        matter = require_matter(session, matter_id, user)
        session.refresh(matter, with_for_update=True)
        renewals._lawyer(session, matter_id, user)
        _, plan, _ = _require(app.state.store, session, matter_id, analysis_id, trial_id, user)
        _current(app, session, matter_id, user, plan)
        proof = require_child(session, _proof_id(ident), ADMISSION, matter_id, user)
        app.state.store.update(proof, {**app.state.store.decode(proof), 'completed': True})
        session.commit()


def authority_model_trials_router():
    router = APIRouter(prefix='/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-model-trials', tags=['authority-model-trials'])

    @router.post('/registration-context')
    def preview(matter_id: str, analysis_id: str, body: Preview, request: Request, user=Depends(authenticate)):
        app = request.app
        with app.state.store.session() as session:
            value = registration_context(app, session, matter_id, analysis_id, user, body.selection)
            with proposals.scope(app, session, matter_id, user, {'source_content': app.state.store.view(
                    require_child(session, analysis_id, 'practice_analysis', matter_id, user)), 'authority_feedback': value['feedback']}):
                return value

    @router.post('', status_code=201)
    def register(matter_id: str, analysis_id: str, body: Registration, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        ident = _prefix(KIND, analysis_id) + digest(user.id + ':' + body.request_id)[:32]
        checksum = digest(canonical(body.model_dump(exclude={'request_id'})))
        with store.session() as session, ExitStack() as guards:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            renewals._lawyer(session, matter_id, user)
            if session.get(Record, ident):
                old, plan, _ = _require(store, session, matter_id, analysis_id, ident, user)
                if old.owner_id != user.id or plan['request_sha256'] != checksum:
                    raise HTTPException(409, 'İstek kimliği başka protokole bağlı.')
                return _read(app, session, matter_id, analysis_id, ident, user)
            context = registration_context(app, session, matter_id, analysis_id, user, body.selection)
            if (not context['can_register'] or body.context_sha256 != context['context_sha256']
                    or body.version_id != context['version_id'] or body.expected_revision != context['expected_revision']
                    or not set(body.reviewer_ids) <= {item['id'] for item in context['eligible_reviewers']}):
                raise HTTPException(409, 'Deneme girdileri veya atanmış hesaplar değişti; yeniden açın.')
            if context['synthetic_only'] and body.sample_kind != 'synthetic':
                raise HTTPException(422, 'Örnek ortam gerçek örnek olarak kaydedilemez.')
            if len(list(session.scalars(select(Record.id).where(Record.kind == KIND, Record.matter_id == matter_id,
                    Record.id.startswith(_prefix(KIND, analysis_id), autoescape=True)).limit(MAX_PROTOCOLS)))) >= MAX_PROTOCOLS:
                raise HTTPException(409, 'Bu analizde 60 protokol sınırına ulaşıldı.')
            row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            content = store.view(row)
            data = {**body.model_dump(exclude={'request_id', 'expected_revision', 'version_id', 'review_feedback'}),
                'recipe': RECIPE, 'recipes': context['recipes'], 'dimensions': context['dimensions'],
                'request_sha256': checksum, 'registered_at': now(), 'registered_by': user.id,
                'analysis_id': analysis_id, 'source_revision': row.revision, 'source_version_id': body.version_id,
                'source_content': content, 'task_input_sha256': digest(canonical(content)),
                'source_review_id': analysis_reviews.review_pin(store, session, matter_id, analysis_id, body.version_id, user),
                'source_review_recipe': analysis_reviews.RECIPE, 'provider_pin': context['provider_pin'],
                'authority_feedback': context['feedback'], 'authority_feedback_sha256': digest(canonical(context['feedback'])),
                'authority_basis': context['basis'], 'research_budget_seconds': context['research_budget_seconds'],
                'rubric_sha256': digest(body.rubric_text), 'account_separation_only': True, 'immutable': True,
                'qualification_granted': False, 'benefit_established': False,
                'arms': {arm: {'request_id': digest(ident + ':' + arm)[:32], 'mode': mode,
                    'max_passes': 1 if mode == 'single' else 2,
                    'budget_seconds': min(app.state.settings.research_budget_seconds, 120 if mode == 'single' else 240)}
                    for arm, mode in ARMS.items()}}
            guards.enter_context(proposals.scope(app, session, matter_id, user, data))
            # Authority feedback is resolved explicitly above; no ordinary proposal
            # may treat this protocol's renewal as an original review.
            _current(app, session, matter_id, user, data)
            data['protocol_sha256'] = digest(canonical(data))
            _add(store, session, KIND, user, data, matter_id, ident, data['protocol_sha256'])
            _audit(session, user, 'authority_model_trial_registered', ident, matter_id)
            final = _capture(app, session, matter_id, analysis_id, ident, user, [ident])
            if final['freshness']['status'] != 'current':
                raise HTTPException(409, 'Kayıt sırasında denemenin sabit girdileri değişti.')
            session.commit()
            try:
                guards.close()
                _complete(app, matter_id, analysis_id, ident, ident, user)
            except HTTPException:
                return JSONResponse(status_code=409, content={'id': ident, 'status': 'committed_needs_revalidation'})
        with store.session() as session:
            return _read(app, session, matter_id, analysis_id, ident, user)

    @router.get('')
    def listing(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_child(session, analysis_id, 'practice_analysis', matter_id, user)
            rows = session.scalars(select(Record).where(Record.kind == KIND, Record.firm_id == user.firm_id,
                Record.matter_id == matter_id, Record.id.startswith(_prefix(KIND, analysis_id), autoescape=True))
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            return [{'id': row.id, 'registered_at': store.decode(row)['registered_at'],
                     'protocol_sha256': store.decode(row)['protocol_sha256']} for row in rows]

    @router.get('/{trial_id}')
    def detail(matter_id: str, analysis_id: str, trial_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            return _read(request.app, session, matter_id, analysis_id, trial_id, user)

    @router.get('/{trial_id}/export')
    def export(matter_id: str, analysis_id: str, trial_id: str, request: Request, user=Depends(authenticate)):
        app = request.app
        with app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            _, plan, _ = _require(app.state.store, session, matter_id, analysis_id, trial_id, user)
            with proposals.scope(app, session, matter_id, user, plan):
                value = _capture(app, session, matter_id, analysis_id, trial_id, user)
                if value['freshness']['status'] != 'current':
                    raise HTTPException(409, 'Güncel olmayan deneme dışa aktarılamaz.')
                data = canonical(value)
                _current(app, session, matter_id, user, plan)
                return Response(data, media_type='application/json', headers={'Cache-Control': 'no-store',
                    'X-Content-Type-Options': 'nosniff', 'Content-Disposition': f'attachment; filename="authority-model-trial-{trial_id}.json"'})

    @router.post('/{trial_id}/run', status_code=202)
    def run(matter_id: str, analysis_id: str, trial_id: str, request: Request,
            body: private_trials.Run = Body(default=private_trials.Run()), user=Depends(authenticate)):
        app = request.app
        with app.state.store.session() as session:
            row, plan, _ = _require(app.state.store, session, matter_id, analysis_id, trial_id, user)
            if row.owner_id != user.id:
                raise HTTPException(403, 'Denemeyi yalnız protokol sahibi başlatabilir.')
            value = _read(app, session, matter_id, analysis_id, trial_id, user)
            if not value['public_source_access'] or value['freshness']['status'] != 'current':
                raise HTTPException(409, 'Güncel izinli deneme gerekli.')
        for arm, spec in plan['arms'].items():
            analysis_suggestions.start_suggestion(matter_id, analysis_id, analysis_suggestions.SuggestionInput(
                expected_revision=plan['source_revision'], version_id=plan['source_version_id'],
                request_id=spec['request_id'], mode=spec['mode'], authority_trial_ref={
                    'id': trial_id, 'protocol_sha256': plan['protocol_sha256'], 'arm': arm}), request, user)
        with app.state.store.session() as session:
            return _read(app, session, matter_id, analysis_id, trial_id, user)

    def append(kind, matter_id, analysis_id, trial_id, body, app, user):
        store = app.state.store
        ident = _prefix(kind, trial_id) + digest(user.id + ':' + body.request_id)[:32]
        checksum = digest(canonical(body.model_dump(exclude={'request_id'})))
        with store.session() as session, ExitStack() as guards:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            renewals._lawyer(session, matter_id, user)
            _, plan, proof = _require(store, session, matter_id, analysis_id, trial_id, user)
            guards.enter_context(proposals.scope(app, session, matter_id, user, plan))
            value = _capture(app, session, matter_id, analysis_id, trial_id, user)
            if session.get(Record, ident):
                prior = require_child(session, ident, kind, matter_id, user)
                if prior.owner_id != user.id or store.decode(prior)['request_sha256'] != checksum:
                    raise HTTPException(409, 'İstek kimliği farklı gözleme bağlı.')
                return store.view(prior)
            key = 'can_observe' if kind == JUDGMENT else 'can_record_effort'
            previous = value['previous_observation_id' if kind == JUDGMENT else 'previous_effort_id']
            if not proof.get('completed') or not value[key] or body.execution_sha256 != value['execution_sha256'] or body.expected_previous_id != previous:
                raise HTTPException(409, 'Güncel iki kol, yetkili hesap ve tam önceki kayıt bağı gerekli.')
            if kind == JUDGMENT:
                for item in body.arms:
                    comparison = value['arms'][item.arm]['comparison']
                    if item.assessment.comparison_sha256 != comparison['comparison_sha256']:
                        raise HTTPException(409, 'Aday karşılaştırma mührü değişti.')
                    basis = {'basis': {'comparison': {'comparison_snapshot': {**comparison,
                        'authority_review_snapshot': {'assessment': plan['authority_basis']['assessment']}},
                        'assessment': {'dispositions': [{'source_index': index, 'dimension': dimension}
                            for index, source in enumerate(plan['authority_basis']['assessment']['sources'])
                            for dimension in plan['authority_basis']['authority_dimensions']]}}}}
                    semantic._validate(item.assessment, basis)
            history = value['observations' if kind == JUDGMENT else 'effort_history']
            if len(history) >= MAX_EVENTS:
                raise HTTPException(409, 'Deneme geçmişi doldu; eski kayıtlar korunur.')
            data = {**body.model_dump(exclude={'request_id'}), 'trial_id': trial_id, 'request_sha256': checksum,
                'reviewer_id': user.id, 'reviewer_name': user.name, 'recorded_at': now(), 'immutable': True,
                'sequence': len(history) + 1, 'qualification_granted': False}
            if kind == JUDGMENT:
                data['comparison_hashes'] = {arm: item['comparison']['comparison_sha256'] for arm, item in value['arms'].items()}
                data['coverage'] = {item.arm: semantic._coverage(item.assessment.model_dump()) for item in body.arms}
            data['sha256'] = digest(canonical(data))
            _add(store, session, kind, user, data, matter_id, ident, data['sha256'])
            _audit(session, user, 'authority_model_observation' if kind == JUDGMENT else 'authority_model_effort', ident, matter_id)
            final = _capture(app, session, matter_id, analysis_id, trial_id, user, [ident])
            if not final[key] or final['execution_sha256'] != body.execution_sha256:
                raise HTTPException(409, 'Gözlem kaydı sırasında deneme girdileri değişti.')
            session.commit()
            try:
                guards.close()
                _complete(app, matter_id, analysis_id, trial_id, ident, user)
            except HTTPException:
                return JSONResponse(status_code=409, content={'id': ident, 'status': 'committed_needs_revalidation'})
            return store.view(require_child(session, ident, kind, matter_id, user))

    @router.post('/{trial_id}/observations', status_code=201)
    def observe(matter_id: str, analysis_id: str, trial_id: str, body: Observation, request: Request, user=Depends(authenticate)):
        return append(JUDGMENT, matter_id, analysis_id, trial_id, body, request.app, user)

    @router.post('/{trial_id}/effort', status_code=201)
    def effort(matter_id: str, analysis_id: str, trial_id: str, body: Effort, request: Request, user=Depends(authenticate)):
        return append(EFFORT, matter_id, analysis_id, trial_id, body, request.app, user)

    return router
