"""Actor-bound, metadata-only observation; never replay or finalize a write."""

from fastapi import HTTPException
from pydantic import Field

from . import source_context_renewals as renewals
from .auth import require_child, require_matter
from .db import Record, digest, now
from .evidence_prompt import canonical
from .practice import StrictInput

RECIPE = 'private-renewal-reconciliation-v1'


class Receipt(StrictInput):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    parent_context_id: str = Field(pattern=r'^sac-[a-f0-9]{20}-[a-f0-9]{32}$')
    expected_parent_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_parent_review_id: str | None = Field(default=None, pattern=r'^sar-[a-f0-9]{20}-[a-f0-9]{32}$')
    parent_version_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    version_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')


def observe(store, session, matter_id, analysis_id, receipt, user):
    from . import source_analysis_reviews as reviews

    matter = require_matter(session, matter_id, user)
    session.refresh(matter, with_for_update=True)
    session.expire_all()
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    result = {'recipe': RECIPE, 'matter_id': matter_id, 'analysis_id': analysis_id, 'observed_at': now(),
        'receipt': receipt.model_dump(), 'outcome': 'not_observed', 'successor': None, 'lineage': None,
        'admission': None, 'source_verification': 'not_checked', 'legal_readiness': 'not_established',
        'review_inheritance': 'none', 'qualification_granted': False, 'effects_replayed': False}
    ident = reviews._prefix(matter_id, analysis_id) + digest(user.id + ':' + receipt.request_id)[:32]
    row = session.get(Record, ident)
    if not row:
        return result
    result['outcome'] = 'unavailable'
    # Verify scope and submitting actor before decrypting the packet.
    if (row.kind != reviews.KIND or row.matter_id != matter_id or row.firm_id != user.firm_id
            or row.owner_id != user.id or not receipt.parent_context_id.startswith(reviews._prefix(matter_id, analysis_id))):
        return result
    try:
        _, packet, _, proof = reviews._require(store, session, matter_id, analysis_id, ident, user)
        manifest = packet['manifest']
        spec = reviews._manifest_spec(manifest)
        if (manifest['recipe'] != reviews.RECIPE or type(proof.get('guard_completed')) is not bool
                or packet['recorded_by'] != user.id or packet['request_sha256'] != receipt.expected_request_sha256
                or packet['request_sha256'] != digest(canonical({**reviews._spec_value(spec),
                    'expected_preview_sha256': packet['manifest_sha256']}))
                or packet['manifest_sha256'] != receipt.expected_preview_sha256 or spec.version_id != receipt.version_id
                or not spec.renewal or spec.renewal.parent_context_id != receipt.parent_context_id
                or spec.renewal.expected_parent_manifest_sha256 != receipt.expected_parent_manifest_sha256
                or spec.renewal.expected_parent_review_id != receipt.expected_parent_review_id):
            return result
        _, parent, _, parent_proof = reviews._require(store, session, matter_id, analysis_id, receipt.parent_context_id, user)
        reviews._manifest_spec(parent['manifest'])
        if (parent['manifest']['recipe'] != reviews.RECIPE or type(parent_proof.get('guard_completed')) is not bool
                or parent['manifest_sha256'] != receipt.expected_parent_manifest_sha256
                or parent['manifest']['version_id'] != receipt.parent_version_id):
            return result
        review_state, review_sha = 'not_recorded', None
        if receipt.expected_parent_review_id:
            _, event, _, event_proof = reviews._require(store, session, matter_id, analysis_id,
                receipt.expected_parent_review_id, user, review=True, context_id=receipt.parent_context_id)
            if event['manifest_sha256'] != parent['manifest_sha256'] or type(event_proof.get('guard_completed')) is not bool:
                return result
            review_state = 'complete' if event_proof.get('guard_completed') else 'pending'
            review_sha = event['packet_sha256']
        prior = parent['manifest'].get('renewal_comparison')
        if prior and (type(prior.get('depth')) is not int or not 1 <= prior['depth'] <= renewals.MAX_DEPTH
                or digest(canonical(prior)) != parent['manifest'].get('renewal_comparison_sha256')):
            return result
        depth = (prior['depth'] if prior else 0) + 1
        if not 1 <= depth <= renewals.MAX_DEPTH:
            return result
        expected = renewals.comparison_from_parent(spec.renewal, manifest, parent, receipt.expected_parent_review_id, depth)
        if (manifest.get('renewal_comparison') != expected
                or manifest.get('renewal_comparison_sha256') != digest(canonical(expected))):
            return result
        result.update(outcome='verified', successor={'id': ident, 'version_id': spec.version_id,
            'manifest_sha256': packet['manifest_sha256'], 'packet_sha256': packet['packet_sha256']},
            lineage={'scope': 'one_historical_link', 'parent_context_id': receipt.parent_context_id,
                'parent_version_id': receipt.parent_version_id, 'parent_manifest_sha256': parent['manifest_sha256'],
                'parent_packet_sha256': parent['packet_sha256'], 'parent_review_id': receipt.expected_parent_review_id,
                'parent_review_packet_sha256': review_sha, 'comparison_sha256': manifest['renewal_comparison_sha256'],
                'depth': depth, 'current_parent_head': 'not_checked', 'legal_equivalence': 'not_assessed'},
            admission={'successor': 'complete' if proof.get('guard_completed') else 'pending',
                'parent': 'complete' if parent_proof.get('guard_completed') else 'pending', 'parent_review': review_state})
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 409, 422}:
            raise
    except (KeyError, ValueError, TypeError):
        pass
    require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    require_child(session, ident, reviews.KIND, matter_id, user)
    return reviews._bounded(result)
