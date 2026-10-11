import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RelationshipSummary, relationshipPath, relationshipPayload, validateRelationshipState, type RelationshipDraft, type RelationshipState } from './SourceRelationshipPanel';
import type { ComparisonEvidence } from './sourceComparison';

const a = 'a'.repeat(64), b = 'b'.repeat(64), hash = 'c'.repeat(64);
const evidence = { evidence_sha256: hash, receipt: {
  left: { source_id: a, passage_id: 'pdf_page_0001', start: 17, passage_start: 10 },
  right: { source_id: b, passage_id: 'html_block_0002', start: 80, passage_start: 60 },
} } as ComparisonEvidence;
const state: RelationshipState = { schema_version: 'source-relationship-state-v1', pair_id: 'd'.repeat(64), source_ids: [a, b], revision: 2,
  source_reviews: { [a]: { revision: 4, assigned_to: null, identity_assessment: null }, [b]: { revision: 8, assigned_to: null, identity_assessment: null } },
  latest: null, history: [], history_truncated: false, stale: false, can_record: true, identity_reviews_ready: true, resolved_for_handoff: false,
  confidentiality: 'firm_confidential', signed: false, publication_eligible: false, independent_originals_verified: false, current_law_verified: false };
const draft: RelationshipDraft = { classification: 'same_work_same_version', rationale: 'Human source evidence considered', leftWork: 'work-6101', rightWork: 'work-6101', leftVersion: 'enacted-2011', rightVersion: 'enacted-2011', reference: 'Separate evidence', sha256: 'e'.repeat(64), seconds: '', basis: 'estimate' };

describe('firm-confidential pair review', () => {
  it('pins two exact source revisions, comparison windows and separate support without actor or timestamp overrides', () => {
    const body = relationshipPayload(draft, state, evidence);
    expect(relationshipPath(evidence)).toBe(`/public-sources/${a}/relationship?other_source_id=${b}`);
    expect(body.expected_revision).toBe(2); expect(body.expected_source_revisions).toEqual({ [a]: 4, [b]: 8 });
    expect(body.comparison).toEqual({ passage_id: 'pdf_page_0001', other_passage_id: 'html_block_0002', offset: 7, other_offset: 20, evidence_sha256: hash });
    expect(body.identities).toEqual([{ source_id: a, work_ref: 'work-6101', version_ref: 'enacted-2011' }, { source_id: b, work_ref: 'work-6101', version_ref: 'enacted-2011' }]);
    expect(body.effort).toBeNull(); expect(body).not.toHaveProperty('reviewer'); expect(body).not.toHaveProperty('created_at');
    expect(draft.seconds).toBe('');
  });
  it.each(['no_owner', 'identity_pending', 'same_receipt', 'missing_reference', 'missing_work', 'inconsistent_version', 'bad_duration', 'partial_support'])('rejects unsupported or inconsistent resolved decisions: %s', kind => {
    const d = { ...draft }, s = structuredClone(state);
    if (kind === 'no_owner') s.can_record = false;
    if (kind === 'identity_pending') s.identity_reviews_ready = false;
    if (kind === 'same_receipt') d.sha256 = hash;
    if (kind === 'missing_reference') d.reference = '';
    if (kind === 'missing_work') d.leftWork = '';
    if (kind === 'inconsistent_version') d.rightVersion = 'other-version';
    if (kind === 'bad_duration') d.seconds = '1.5';
    if (kind === 'partial_support') d.sha256 = '';
    expect(() => relationshipPayload(d, s, evidence)).toThrow();
  });
  it('keeps unknown distinct from explicit zero and uses only declared relationship effort', () => {
    expect(relationshipPayload(draft, state, evidence).effort).toBeNull();
    expect(relationshipPayload({ ...draft, seconds: '0', basis: 'self_reported_timer' }, state, evidence).effort).toEqual({ active_seconds: 0, basis: 'self_reported_timer' });
  });
  it('allows unresolved opinions without fabricated work or version identity', () => {
    const body = relationshipPayload({ ...draft, classification: 'unresolved', reference: '', sha256: '' }, { ...state, identity_reviews_ready: false }, evidence);
    expect(body.identities).toEqual([]); expect(body.evidence_refs).toEqual([]);
  });
  it.each(['sources', 'pins', 'publication', 'independence', 'current_law', 'signed', 'revision', 'confidentiality'])('rejects mismatched identity and unsafe response scope: %s', kind => {
    const s = structuredClone(state);
    if (kind === 'sources') s.source_ids = [a, 'f'.repeat(64)];
    if (kind === 'pins') delete s.source_reviews[b];
    if (kind === 'revision') s.revision = 201;
    if (kind === 'confidentiality') s.confidentiality = 'public' as 'firm_confidential';
    if (kind === 'publication') s.publication_eligible = true as false;
    if (kind === 'independence') s.independent_originals_verified = true as false;
    if (kind === 'current_law') s.current_law_verified = true as false;
    if (kind === 'signed') s.signed = true as false;
    expect(() => validateRelationshipState(s, evidence)).toThrow();
  });
  it('escapes confidential opinions and references while retaining disagreement, stale state and unknown effort', () => {
    const event = { id: 'first', revision: 1, reviewer: { id: 'human', name: '<script>reviewer</script>' }, created_at: '2026-10-11T08:00:00Z',
      input: { classification: 'unresolved' as const, rationale: '<img src=x onerror=alert(1)>', identities: [], effort: null, evidence_refs: [{ reference: 'javascript:alert(1)', sha256: hash }] },
      source_reviews: state.source_reviews, comparison_evidence: { evidence_json: '{}', evidence_sha256: hash } };
    const html = renderToStaticMarkup(<RelationshipSummary state={{ ...state, latest: event, history: [event], stale: true, history_truncated: true }} />);
    expect(html).toContain('yeniden insan incelemesi'); expect(html).toContain('bilinmiyor'); expect(html).toContain('Son 50');
    expect(html).toContain('&lt;img'); expect(html).not.toContain('<script>'); expect(html).not.toContain('href="javascript:');
  });
});
