import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AuthorityTrials, { TrialContent } from './AuthorityTrials';
import { pendingTrial, trialEffort, trialReviewers } from './authorityTrialTypes';
import type { TrialRegistrationContext, TrialView } from './authorityTrialTypes';

const context: TrialRegistrationContext = { can_register: true, context_sha256: 'a'.repeat(64), synthetic_only: true, reasons: [], eligible_reviewers: [{ id: 'one', name: 'One' }, { id: 'two', name: 'Two' }], basis: { baseline_version_id: 'v1', input_sha256: 'b'.repeat(64), rubric: { meaning: 'Anlam' } } };
const blank = () => ['original', 'revised'].map(arm => ({ arm, preparation_seconds: '', verification_seconds: '', correction_seconds: '' })) as Parameters<typeof trialEffort>[0];
const value = (): TrialView => ({ id: 'atr-' + 'a'.repeat(24) + '-' + 'b'.repeat(32), capture_id: null, registered_at: '2026-01-01T00:00:00Z', owner_id: 'operator', public_source_access: true, can_record: true, freshness: { status: 'current', reasons: [] }, capture_complete: false, protocol_sha256: 'c'.repeat(64), capture_sha256: null, protocol: { title: 'SYNTHETIC <script>private</script>', question: 'SYNTHETIC question', sample_kind: 'synthetic', reviewer_ids: ['one', 'two'], split_family_sha256: 'e'.repeat(64), basis: context.basis, registration_before_baseline: false }, snapshot: null });

describe('registered fixed-evidence human authority trials', () => {
  it('loads only on explicit requests with no selected attestations', () => {
    const html = renderToStaticMarkup(<AuthorityTrials base="/private/trials" onUnavailable={() => undefined} />);
    expect(html).toContain('Revizyon öncesi kayıt girdilerini getir');
    expect(html).not.toContain('<details open'); expect(html).not.toContain('checked'); expect(html).not.toContain('SYNTHETIC');
  });
  it('keeps registration scope and qualification limits clear with escaped notes', () => {
    const html = renderToStaticMarkup(<TrialContent value={value()} />);
    for (const text of ['Kayıtlar / ölçümler eksik', 'özgün taslak kayıt öncesi', 'Model karşılaştırması', '&lt;script&gt;']) expect(html).toContain(text);
    expect(html).not.toContain('<script>');
  });
  it('permission denial overrides even an accidentally cached protocol', () => {
    const cached = value(); cached.public_source_access = false;
    const html = renderToStaticMarkup(<TrialContent value={cached} />);
    expect(html).toContain('bekletiliyor'); expect(html).not.toContain('SYNTHETIC'); expect(html).not.toContain('private');
  });
  it('shows retained stale inputs with export-closed status', () => {
    const stale = value(); stale.freshness = { status: 'stale', reasons: ['registered_basis_changed'] };
    const html = renderToStaticMarkup(<TrialContent value={stale} />);
    expect(html).toContain('Aktarım kapalı'); expect(html).toContain('registered_basis_changed');
  });
  it('preserves explicit zero and unknown effort without inferred totals', () => {
    expect(trialEffort(blank())?.[0].preparation_seconds).toBeNull();
    const rows = blank(); rows[0].correction_seconds = '0';
    expect(trialEffort(rows)?.[0].correction_seconds).toBe(0);
    for (const invalid of ['1.5', '-1', 'true', '1e3', '28801']) {
      rows[0].correction_seconds = invalid; expect(trialEffort(rows)).toBeNull();
    }
    expect(trialEffort(blank().slice(1))).toBeNull();
    expect(trialEffort([blank()[0], blank()[0]])).toBeNull();
  });
  it('requires two distinct eligible accounts and a current registration', () => {
    expect(trialReviewers(context, ['one', 'two'])).toBe(true);
    expect(trialReviewers(context, ['one', 'one'])).toBe(false);
    expect(trialReviewers(context, ['one', 'foreign'])).toBe(false);
    expect(trialReviewers({ ...context, can_register: false }, ['one', 'two'])).toBe(false);
  });
  it('only accepts exact pending record identifiers', () => {
    expect(pendingTrial({ id: value().id, needs_revalidation: true, outcome: 'committed_needs_revalidation' })).toBe(true);
    expect(pendingTrial({ id: '../private', needs_revalidation: true, outcome: 'committed_needs_revalidation' })).toBe(false);
  });
});
