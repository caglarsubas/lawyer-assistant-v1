import type { AuthorityComparisonView } from './authorityComparisonTypes';
import type { AdjudicationView } from './authorityAdjudicationTypes';

export interface TrialRegistrationContext {
  context_sha256: string; can_register: boolean; synthetic_only: boolean;
  eligible_reviewers: { id: string; name: string }[]; reasons: string[];
  basis: { baseline_version_id: string; input_sha256: string; rubric: Record<string, string> };
}
export type TrialArm = 'original' | 'revised';
export const TRIAL_ARMS: TrialArm[] = ['original', 'revised'];
export const EFFORT_PHASES = ['preparation_seconds', 'verification_seconds', 'correction_seconds'] as const;
export type EffortPhase = typeof EFFORT_PHASES[number];
export type EditableTrialEffort = { arm: TrialArm } & Record<EffortPhase, string>;
export type TrialEffort = { arm: TrialArm } & Record<EffortPhase, number | null>;
export interface TrialCaptureContext {
  basis_sha256: string; expected_capture_id: string | null; can_record: boolean;
  basis: { comparison_id: string; comparison: NonNullable<AuthorityComparisonView['snapshot']>;
    observations: (Omit<NonNullable<AdjudicationView['snapshot']>, 'basis'> & { id: string; reviewer_name: string; reviewer_id: string })[] };
}
export interface TrialView {
  id: string; capture_id: string | null; registered_at: string; owner_id: string;
  public_source_access: boolean; freshness: { status: 'current' | 'stale' | 'withheld'; reasons: string[] };
  capture_complete: boolean; can_record: boolean; protocol_sha256: string; capture_sha256: string | null;
  protocol: null | { title: string; question: string; reviewer_ids: string[]; sample_kind: 'real' | 'synthetic';
    split_family_sha256: string; basis: TrialRegistrationContext['basis']; registration_before_baseline: false };
  snapshot: null | { sequence: number; recorded_at: string; basis: TrialCaptureContext['basis'];
    effort_accounted: boolean; disagreement: { semantic_dimensions: number | null; finding_dimensions: number | null };
    assessment: { note: string; arms: TrialEffort[]; shared_setup_included: boolean;
      verification_and_correction_included: boolean; non_overlapping_active_time: boolean } };
}
export function trialEffort(rows: EditableTrialEffort[]) {
  if (rows.length !== 2 || new Set(rows.map(row => row.arm)).size !== 2 || rows.some(row => !TRIAL_ARMS.includes(row.arm))) return null;
  const converted: TrialEffort[] = [];
  for (const row of rows) {
    const value = { arm: row.arm } as TrialEffort;
    for (const key of EFFORT_PHASES) {
      const text = row[key].trim(); const seconds = text === '' ? null : Number(text);
      if (seconds !== null && (!/^\d+$/.test(text) || !Number.isSafeInteger(seconds) || seconds > 28800)) return null;
      value[key] = seconds;
    }
    converted.push(value);
  }
  return converted;
}
export function trialReviewers(context: TrialRegistrationContext, selected: string[]) {
  return context.can_register && selected.length === 2 && new Set(selected).size === 2
    && selected.every(id => context.eligible_reviewers.some(item => item.id === id));
}
export function pendingTrial(data: unknown) {
  if (!data || typeof data !== 'object') return false;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true
    && typeof value.id === 'string' && /^atr-[a-f0-9]{24}-[a-f0-9]{32}$/.test(value.id);
}
