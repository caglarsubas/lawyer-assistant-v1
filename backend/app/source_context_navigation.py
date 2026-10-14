"""Exact private identity handoff; no public verdict, quote or admission replay."""

import re

from fastapi import HTTPException

from . import analysis_reviews
from .auth import require_child, require_matter
from .db import now

RECIPE = 'private-source-context-navigation-v1'
IDENTIFIER = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
CONTEXT_ID = re.compile(r'^sac-[a-f0-9]{20}-[a-f0-9]{32}$')


def metadata(store, session, matter_id, analysis_id, context_id, user):
    from . import source_analysis_reviews as reviews

    if (not IDENTIFIER.fullmatch(matter_id) or not IDENTIFIER.fullmatch(analysis_id)
            or not CONTEXT_ID.fullmatch(context_id) or not context_id.startswith(reviews._prefix(matter_id, analysis_id))):
        raise HTTPException(404, 'Kaynak bağlamı bulunamadı.')
    matter = require_matter(session, matter_id, user)
    session.refresh(matter, with_for_update=True)
    session.expire_all()
    analysis = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    context = require_child(session, context_id, reviews.KIND, matter_id, user)
    result = {'recipe': RECIPE, 'matter_id': matter_id, 'analysis_id': analysis_id, 'context_id': context_id,
        'observed_at': now(), 'analysis': {'id': analysis_id, 'current_version_id': None, 'revision': analysis.revision},
        'context': {'id': context_id, 'version_id': None, 'manifest_sha256': None, 'recorded_at': context.created_at},
        'admission': {'context_state': 'unavailable', 'review_state': 'unknown'},
        'historical_review': {'state': 'unknown', 'id': None, 'recorded_at': None},
        'version_relation': 'unknown', 'integrity': 'unavailable', 'tools_available': False,
        'source_verification': 'not_checked', 'legal_readiness': 'not_established', 'qualification_granted': False}
    # Complete context/admission routing before decrypting the selected packet.
    try:
        require_child(session, reviews._id('saa-', context_id), reviews.ADMISSION, matter_id, user)
        _, packet, _, proof = reviews._require(store, session, matter_id, analysis_id, context_id, user)
        manifest = packet['manifest']
        reviews._manifest_spec(manifest)
        if manifest['recipe'] != reviews.RECIPE:
            raise HTTPException(409)
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 409, 422}:
            raise
        require_child(session, context_id, reviews.KIND, matter_id, user)
        return result
    except (KeyError, TypeError, ValueError):
        return result
    result.update(integrity='verified')
    result['context'].update(version_id=manifest['version_id'], manifest_sha256=packet['manifest_sha256'])
    result['admission']['context_state'] = 'complete' if proof.get('guard_completed') else 'pending'
    try:
        current_id = store.decode(analysis)['latest_version_id']
        if not isinstance(current_id, str) or not IDENTIFIER.fullmatch(current_id):
            raise HTTPException(409)
        analysis_reviews._version(store, session, matter_id, analysis_id, current_id, user)
        result['analysis']['current_version_id'] = current_id
        result.update(version_relation='same' if current_id == manifest['version_id'] else 'different', tools_available=True)
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 409}:
            raise
    except (KeyError, TypeError, ValueError):
        pass
    try:
        head = reviews._head(store, session, matter_id, analysis_id, context_id, user)
        result['historical_review']['state'] = 'unreviewed'
        result['admission']['review_state'] = 'not_recorded'
        if head:
            _, event, _, review_proof = reviews._require(store, session, matter_id, analysis_id, head['latest_review_id'],
                user, review=True, context_id=context_id)
            result['historical_review'] = {'state': event['input']['decision'], 'id': head['latest_review_id'],
                                          'recorded_at': event['recorded_at']}
            result['admission']['review_state'] = 'complete' if review_proof.get('guard_completed') else 'pending'
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 409, 422}:
            raise
        result['historical_review'] = {'state': 'unknown', 'id': None, 'recorded_at': None}
        result['admission']['review_state'] = 'unavailable'
    except (KeyError, TypeError, ValueError):
        result['historical_review'] = {'state': 'unknown', 'id': None, 'recorded_at': None}
        result['admission']['review_state'] = 'unavailable'
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    require_child(session, context_id, reviews.KIND, matter_id, user)
    return reviews._bounded(result)
