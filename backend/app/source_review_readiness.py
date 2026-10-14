"""Bounded private observations, never a cached public-source authorization."""

from datetime import datetime, time, timedelta, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select

from . import analysis_reviews, analysis_workbench
from .auth import require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .portfolio import PORTFOLIO_TIMEZONE, parse_date

RECIPE = 'private-source-review-readiness-v1'
MAX_WINDOW = 10
MAX_DEPENDENCIES = 256
MAX_CONTRADICTIONS = 100
STATES = {'pending': 0, 'unavailable': 0, 'needs_renewal': 1, 'changes_requested': 2,
          'awaiting_review': 3, 'inspection_required': 4}
Bucket = Literal['all', 'action_required']


def _contradictions(store, session, matter_id, user):
    rows = session.scalars(select(Record).where(Record.kind == 'practice_contradiction',
        Record.firm_id == user.firm_id, Record.matter_id == matter_id).order_by(Record.id).limit(MAX_CONTRADICTIONS + 1)).all()
    if len(rows) > MAX_CONTRADICTIONS:
        return None
    return [(row, store.decode(row)) for row in rows]


def _private(store, session, matter_id, analysis_id, manifest, user, contradictions, budget):
    reasons = []
    analysis = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    if store.decode(analysis)['latest_version_id'] != manifest['version_id']:
        reasons.append('analysis_version_changed')
    _, version = analysis_reviews._version(store, session, matter_id, analysis_id, manifest['version_id'], user)
    if digest(canonical(version['content'])) != manifest['analysis_content_sha256']:
        reasons.append('analysis_content_changed')
    if analysis_reviews.review_pin(store, session, matter_id, analysis_id, manifest['version_id'], user) != manifest['analysis_review_id']:
        reasons.append('analysis_review_head_changed')
    basis = manifest['private_basis']
    if (basis['analysis_recipe'] != analysis_workbench.RECIPE or basis['review_recipe'] != analysis_reviews.RECIPE):
        reasons.append('private_recipe_changed')
    records = basis['records']
    if len(records) > budget[0]:
        return reasons, False
    budget[0] -= len(records)
    for saved in records:
        # Existence and routing are checked before any payload is decrypted.
        row = session.get(Record, saved['id'], populate_existing=True)
        if not row or row.kind != saved['kind'] or row.matter_id != matter_id or row.firm_id != user.firm_id:
            reasons.append('private_dependency_unavailable')
        elif digest(canonical(store.view(row))) != saved['sha256']:
            reasons.append('private_dependency_changed')
    if contradictions is None:
        return reasons, False
    fact_ids = {item['id'] for item in manifest['analysis_content']['fact_snapshots']}
    current = [{'id': row.id, 'revision': row.revision, 'status': data['status'], 'fact_ids': data['fact_ids']}
               for row, data in contradictions if set(data['fact_ids']) <= fact_ids] if fact_ids else []
    if current != basis['contradictions']:
        reasons.append('contradiction_basis_changed')
    return reasons, True


def _item(store, session, matter_id, analysis_id, row, user, contradictions, budget):
    from . import source_analysis_reviews as reviews
    from . import source_context_renewals as renewals

    value = {'id': row.id, 'recorded_at': row.created_at, 'state': 'unavailable',
        'historical_review': {'state': 'unknown', 'id': None, 'recorded_at': None},
        'private_observation': {'state': 'unknown', 'reasons': []},
        'source_verification': 'not_checked', 'legal_readiness': 'not_established'}
    try:
        _, packet, _, proof = reviews._require(store, session, matter_id, analysis_id, row.id, user)
        manifest = packet['manifest']
        reviews._manifest_spec(manifest)
        value.update(version_id=manifest['version_id'], product_id=manifest['product_id'],
                     manifest_sha256=packet['manifest_sha256'])
        reasons = []
        pending = not proof.get('guard_completed')
        if pending:
            reasons.append('context_admission_pending')
        head = reviews._head(store, session, matter_id, analysis_id, row.id, user)
        value['historical_review']['state'] = 'unreviewed'
        if head:
            _, event, _, review_proof = reviews._require(store, session, matter_id, analysis_id, head['latest_review_id'],
                                                        user, review=True, context_id=row.id)
            value['historical_review'] = {'state': event['input']['decision'], 'id': head['latest_review_id'],
                                          'recorded_at': event['recorded_at']}
            if not review_proof.get('guard_completed'):
                pending = True
                reasons.append('review_admission_pending')
            if (event['manifest_sha256'] != packet['manifest_sha256'] or event['recipe'] != reviews.REVIEW_RECIPE
                    or event['dimensions'] != reviews.DIMENSIONS):
                reasons.append('source_review_basis_changed')
            reviewer = session.get(User, event['recorded_by'], populate_existing=True)
            try:
                if reviewer is None:
                    raise HTTPException(403)
                reviews._reviewer(session, matter_id, reviewer, packet)
            except HTTPException:
                reasons.append('reviewer_access_changed')
        private, complete = _private(store, session, matter_id, analysis_id, manifest, user, contradictions, budget)
        reasons.extend(private)
        try:
            product, data, pin, _ = reviews._product(store, session, matter_id, manifest['product_id'], user)
            if (product.revision != manifest['product_revision'] or digest(canonical(data)) != manifest['product_sha256']
                    or pin != manifest['graph_release_pin']):
                reasons.append('research_basis_changed')
        except HTTPException as exc:
            if exc.status_code not in {403, 404, 409}:
                raise
            reasons.append('research_basis_unavailable')
        if manifest.get('renewal'):
            try:
                renewals.parent(store, session, matter_id, analysis_id, manifest['renewal'], user)
            except HTTPException as exc:
                if exc.status_code not in {403, 404, 409}:
                    raise
                reasons.append('parent_basis_changed_or_unavailable')
        if not complete:
            reasons.append('observation_budget_exhausted')
        reasons = list(dict.fromkeys(reasons))
        changed = any(reason not in {'context_admission_pending', 'review_admission_pending', 'observation_budget_exhausted'} for reason in reasons)
        value['private_observation'] = {'state': 'changed' if changed else ('unchanged' if complete else 'unknown'), 'reasons': reasons}
        state = value['historical_review']['state']
        value['state'] = ('pending' if pending else 'needs_renewal' if changed else 'unavailable' if not complete
                          else 'changes_requested' if state == 'changes_requested' else 'awaiting_review' if state == 'unreviewed'
                          else 'inspection_required')
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 409, 422}:
            raise
        value = {**value, 'state': 'unavailable', 'private_observation': {'state': 'unknown', 'reasons': ['private_basis_unavailable']}}
    except (KeyError, TypeError, ValueError):
        value = {**value, 'state': 'unavailable', 'private_observation': {'state': 'unknown', 'reasons': ['record_integrity_unavailable']}}
    return value


def queue(store, session, matter_id, analysis_id, user, *, window=10, offset=0, bucket='all', date_from=None, date_to=None):
    """One authorized analysis window, under the same lock as private edits.

    Sorting/counts describe this window only. Public guards run only on explicit
    detail/review actions, so a historical positive decision remains unchecked.
    """
    from . import source_analysis_reviews as reviews

    matter = require_matter(session, matter_id, user)
    session.refresh(matter, with_for_update=True)
    session.expire_all()
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    start, end = parse_date(date_from), parse_date(date_to)
    if start and end and start > end:
        raise HTTPException(422, 'Başlangıç tarihi bitişten sonra olamaz.')
    query = select(Record).where(Record.kind == reviews.KIND, Record.matter_id == matter_id,
        Record.firm_id == user.firm_id, Record.id.startswith(reviews._prefix(matter_id, analysis_id)))
    if start:
        try:
            boundary = datetime.combine(start, time.min, PORTFOLIO_TIMEZONE).astimezone(timezone.utc).isoformat()
        except (OverflowError, ValueError):
            raise HTTPException(422, 'Tarih aralığı desteklenen sınırı aşıyor.') from None
        query = query.where(Record.created_at >= boundary)
    if end:
        try:
            boundary = datetime.combine(end + timedelta(days=1), time.min, PORTFOLIO_TIMEZONE).astimezone(timezone.utc).isoformat()
        except (OverflowError, ValueError):
            raise HTTPException(422, 'Tarih aralığı desteklenen sınırı aşıyor.') from None
        query = query.where(Record.created_at < boundary)
    rows = session.scalars(query.order_by(Record.created_at.desc(), Record.id).limit(window + 1).offset(offset)).all()
    budget = [MAX_DEPENDENCIES]
    contradictions = _contradictions(store, session, matter_id, user) if rows else []
    items = [_item(store, session, matter_id, analysis_id, row, user, contradictions, budget) for row in rows[:window]]
    if bucket == 'action_required':
        items = [item for item in items if item['state'] != 'inspection_required']
    # Stable chronological ties, with priority only inside this bounded window.
    items.sort(key=lambda item: STATES[item['state']])
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    return {'recipe': RECIPE, 'matter_id': matter_id, 'analysis_id': analysis_id, 'observed_at': now(), 'items': items,
        'coverage': {'scope': 'authorized_analysis_window_only', 'scanned_count': min(len(rows), window),
            'returned_count': len(items), 'has_more': len(rows) > window, 'next_offset': offset + window if len(rows) > window and offset + window <= 10000 else None,
            'pagination_limit_reached': len(rows) > window and offset + window > 10000,
            'priority_scope': 'current_window_only', 'total_count': None, 'source_verification': 'not_checked'},
        'legal_readiness': 'not_established', 'qualification_granted': False}
