import type { AuthorityAssessment, EditableAssessment, FindingDimension } from './authorityFindingTypes';
import type { AuthorityManifest } from './authorityTypes';
export interface LineageRef { id: string; sha256: string }
export interface LineagePreview {
  preview_sha256: string; preview: { version_id: string; expected_revision: number; draft_sha256: string;
    dimensions: Record<FindingDimension, string>; targets: Record<string, unknown>;
    entries: { dependency_sha256: string; manifest: AuthorityManifest; stale_reasons: string[] }[] };
}
export interface EditableRenewal { dependency_sha256: string; note: string; seconds: string; sources: EditableAssessment[] }
export interface LineageRecord extends LineageRef {
  version_id: string; snapshot: { sequence: number; version_id: string; reviewer_name: string; recorded_at: string; dimensions: Record<FindingDimension, string>;
    entries?: { dependency_sha256: string; dependency: { context_id: string; review_id: string; review_sha256: string } }[];
    renewals?: (AuthorityAssessment & { dependency_sha256: string })[] };
}
export function pendingLineageReceipt(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true
    && typeof value.id === 'string' && /^arl-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value.id) ? value.id : null;
}

export function sourceBindingReason(reason: string): string {
  const labels: Record<string, string> = {
    authority_review_changed: 'Özgün kaynak incelemesinden sonra yeni bir inceleme kaydedildi.',
    authority_reviewer_access_changed: 'Özgün inceleyenin çalışma alanı veya inceleme erişimi değişti.',
    authority_recipe_changed: 'Kaynak inceleme kuralları değişti; bu akışla yenilenemez.',
    authority_revalidated_analysis_changed: 'Kaynak bağı yenilendikten sonra taslak veya model katkısı değişti.',
    authority_revalidation_review_changed: 'Yenilemeden sonra kaynak bağları veya inceleme başı değişti.',
    authority_revalidation_reviewer_access_changed: 'Bağı yenileyen avukatın çalışma alanı veya inceleme erişimi değişti.',
    authority_revalidation_recipe_changed: 'Bağ yenileme inceleme kuralları değişti.',
  };
  return labels[reason] || reason;
}
