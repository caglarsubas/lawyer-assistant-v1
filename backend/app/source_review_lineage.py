"""Bounded private review ancestry; identity observations never authorize source reads."""

import re
from datetime import datetime

from fastapi import HTTPException

from . import source_context_navigation as navigation
from .auth import require_child
from .db import digest

RECIPE = 'private-source-review-lineage-v1'
MAX_WINDOW = 10
REVIEW_ID = re.compile(r'^sar-[a-f0-9]{20}-[a-f0-9]{32}$')


def _route(context_id, review_id):
    if not isinstance(review_id, str) or not REVIEW_ID.fullmatch(review_id) or not review_id.startswith('sar-' + digest(context_id)[:20] + '-'):
        raise HTTPException(404, 'İnceleme kaydı bulunamadı.')


def _event(store, session, matter_id, analysis_id, context_id, review_id, user, manifest_sha):
    from . import source_analysis_reviews as reviews

    _route(context_id, review_id)
    row = require_child(session, review_id, reviews.REVIEW, matter_id, user)
    result = {'id': review_id, 'state': 'unknown', 'sequence': None, 'recorded_at': None,
        'packet_sha256': None, 'manifest_sha256': None, 'previous_review_id': None,
        'admission': 'unavailable', 'integrity': 'unavailable'}
    if not manifest_sha:
        return result
    try:
        require_child(session, reviews._id('saa-', review_id), reviews.ADMISSION, matter_id, user)
        _, event, _, proof = reviews._require(store, session, matter_id, analysis_id, review_id, user, review=True, context_id=context_id)
        sequence, previous = event['sequence'], event['previous_review_id']
        if (event['recipe'] != reviews.REVIEW_RECIPE or event['dimensions'] != reviews.DIMENSIONS
                or event['legal_approval'] != 'not_granted' or event['manifest_sha256'] != manifest_sha
                or type(sequence) is not int or not 1 <= sequence <= reviews.MAX_REVIEWS
                or previous != event['input']['expected_review_id'] or (sequence == 1) != (previous is None)):
            raise ValueError('Invalid event semantics')
        if previous is not None:
            _route(context_id, previous)
        stamp = event['recorded_at']
        if not isinstance(stamp, str) or len(stamp) > 40 or datetime.fromisoformat(stamp).tzinfo is None:
            raise ValueError('Unknown event recording time')
        result.update(state=event['input']['decision'], sequence=sequence, recorded_at=stamp,
            packet_sha256=event['packet_sha256'], manifest_sha256=event['manifest_sha256'], previous_review_id=previous,
            admission='complete' if proof.get('guard_completed') else 'pending', integrity='verified')
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 409, 422}:
            raise
    except (KeyError, TypeError, ValueError):
        pass
    require_child(session, row.id, reviews.REVIEW, matter_id, user)
    return result


def metadata(store, session, matter_id, analysis_id, context_id, review_id, user, *, window=MAX_WINDOW):
    from . import source_analysis_reviews as reviews

    if not navigation.CONTEXT_ID.fullmatch(context_id) or not context_id.startswith(reviews._prefix(matter_id, analysis_id)):
        raise HTTPException(404, 'İnceleme kaydı bulunamadı.')
    _route(context_id, review_id)
    # Authenticate every selected routing identity before decrypting any context.
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    require_child(session, context_id, reviews.KIND, matter_id, user)
    require_child(session, review_id, reviews.REVIEW, matter_id, user)
    context = navigation.metadata(store, session, matter_id, analysis_id, context_id, user)
    manifest_sha = context['context']['manifest_sha256']
    selected = _event(store, session, matter_id, analysis_id, context_id, review_id, user, manifest_sha)
    head_id = context['historical_review']['id']
    head = _event(store, session, matter_id, analysis_id, context_id, head_id, user, manifest_sha) if head_id else None
    # Identity equality/different sequence is not proof of a reachable history.
    relationship = 'unestablished'
    if selected['integrity'] == 'verified' and head and head['integrity'] == 'verified':
        relationship = 'current_head' if head_id == review_id else 'different_from_head'
    items, seen, cursor, expected = [], set(), selected, selected['sequence']
    status, next_id = 'unavailable', None
    for _ in range(window):
        if cursor['integrity'] != 'verified' or cursor['id'] in seen or cursor['sequence'] != expected:
            break
        seen.add(cursor['id'])
        items.append(cursor)
        previous = cursor['previous_review_id']
        if previous is None:
            status = 'complete_to_first_event'
            break
        if previous in seen:
            break
        if len(items) == window:
            status, next_id = 'truncated', previous
            break
        try:
            cursor = _event(store, session, matter_id, analysis_id, context_id, previous, user, manifest_sha)
        except HTTPException as exc:
            if exc.status_code not in {403, 404, 409}:
                raise
            break
        expected -= 1
    result = {'recipe': RECIPE, 'matter_id': matter_id, 'analysis_id': analysis_id, 'context_id': context_id,
        'review_id': review_id, 'observed_at': context['observed_at'], 'context_navigation': context,
        'selected_review': selected, 'current_head': head, 'head_relationship': relationship,
        'lineage': {'scope': 'selected_predecessors_only', 'status': status, 'window': window,
            'items': items, 'next_review_id': next_id, 'total_count': None, 'head_reachability': 'not_checked'},
        'tools_available': context['tools_available'] and selected['integrity'] == 'verified' and selected['admission'] == 'complete' and status != 'unavailable',
        'source_verification': 'not_checked', 'legal_readiness': 'not_established', 'qualification_granted': False}
    require_child(session, review_id, reviews.REVIEW, matter_id, user)
    return reviews._bounded(result)
