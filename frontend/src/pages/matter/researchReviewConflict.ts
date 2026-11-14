import { ApiError } from '../../api';

export type ReviewConflict =
  | { kind: 'saved'; revision: number }
  | { kind: 'rejected'; message: string }
  | { kind: 'unknown' };

export function researchReviewConflict(cause: unknown, productId: string): ReviewConflict | null {
  if (cause instanceof SyntaxError) return { kind: 'unknown' };
  if (!(cause instanceof ApiError)) return null;
  if (cause.status === 0 || cause.status >= 500) return { kind: 'unknown' };
  if (cause.status !== 409) return null;

  const data = cause.data as { outcome?: unknown; needs_revalidation?: unknown; product_id?: unknown; revision?: unknown } | null;
  if (data?.outcome !== 'committed_needs_revalidation' && !data?.needs_revalidation) {
    return { kind: 'rejected', message: cause.message };
  }
  if (data.outcome === 'committed_needs_revalidation' && data.needs_revalidation === true
    && data.product_id === productId && typeof data.revision === 'number' && Number.isSafeInteger(data.revision) && data.revision > 0) {
    return { kind: 'saved', revision: data.revision };
  }
  return { kind: 'unknown' };
}
