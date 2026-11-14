import { ApiError } from '../../api';

export type ReviewConflict =
  | { kind: 'saved'; revision: number }
  | { kind: 'rejected'; message: string }
  | { kind: 'unknown' };

const rejectedBeforeCommit = new Set([
  'Bu sürüm değiştirilemez; yeni araştırma başlatın',
  'Kritik eksikler veya incelenmemiş bulgular var',
  'Graf sürümünün güncel yayın izni doğrulanamadı; yeniden araştırma gerekli.',
  'Kayıt başka bir işlemde değişti; yenileyip tekrar deneyin.',
]);

export function researchReviewConflict(cause: unknown, productId: string, beforeRevision = 0): ReviewConflict | null {
  if (cause instanceof SyntaxError || cause instanceof TypeError) return { kind: 'unknown' };
  if (!(cause instanceof ApiError)) return null;
  if (cause.status === 0 || cause.status >= 500) return { kind: 'unknown' };
  if (cause.status !== 409) return null;

  const data = cause.data as { outcome?: unknown; needs_revalidation?: unknown; product_id?: unknown; revision?: unknown } | null;
  if (data?.outcome === 'committed_needs_revalidation' && data.needs_revalidation === true
    && data.product_id === productId && typeof data.revision === 'number' && Number.isSafeInteger(data.revision) && data.revision > beforeRevision) {
    return { kind: 'saved', revision: data.revision };
  }
  if (data && !('outcome' in Object(data)) && !('needs_revalidation' in Object(data)) && rejectedBeforeCommit.has(cause.message)) {
    return { kind: 'rejected', message: cause.message };
  }
  return { kind: 'unknown' };
}
