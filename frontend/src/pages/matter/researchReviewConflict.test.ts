import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api';
import type { Product } from '../../types';
import { createProductReader } from './researchProductRead';
import { researchReviewConflict } from './researchReviewConflict';

const saved = { outcome: 'committed_needs_revalidation', needs_revalidation: true, product_id: 'p1', revision: 5 };

describe('research review recovery', () => {
  it('distinguishes a matching committed receipt from a rejected and an ambiguous write', () => {
    expect(researchReviewConflict(new ApiError('test', 409, saved), 'p1')).toEqual({ kind: 'saved', revision: 5 });
    const rejection = 'Bu sürüm değiştirilemez; yeni araştırma başlatın';
    expect(researchReviewConflict(new ApiError(rejection, 409, { detail: rejection }), 'p1')).toEqual({ kind: 'rejected', message: rejection });
    expect(researchReviewConflict(new ApiError('Unreadable 409', 409, null), 'p1')).toEqual({ kind: 'unknown' });
    expect(researchReviewConflict(new TypeError('Body stream closed'), 'p1')).toEqual({ kind: 'unknown' });
    expect(researchReviewConflict(new ApiError('test', 409, saved), 'p1', 5)).toEqual({ kind: 'unknown' });
    expect(researchReviewConflict(new ApiError('test', 0), 'p1')).toEqual({ kind: 'unknown' });
    expect(researchReviewConflict(new ApiError('test', 500), 'p1')).toEqual({ kind: 'unknown' });
    expect(researchReviewConflict(new ApiError('test', 422), 'p1')).toBeNull();
  });

  it.each([{ ...saved, product_id: 'p2' }, { ...saved, revision: '5' }, { ...saved, needs_revalidation: false }])('never attributes a malformed or cross-output receipt to this review', receipt => {
    expect(researchReviewConflict(new ApiError('test', 409, receipt), 'p1')).toEqual({ kind: 'unknown' });
  });

  it('withholds reads older than the recorded revision and accepts the exact output when it catches up', async () => {
    const publish = vi.fn();
    const savedProduct = { id: 'p1', version: 2, revision: 5, status: 'stale' } as Product;
    const fetchProduct = vi.fn().mockResolvedValueOnce({ ...savedProduct, revision: 4 }).mockResolvedValueOnce(savedProduct);
    const reader = createProductReader({ matterId: 'm1', productId: 'p1', version: 2 }, publish, fetchProduct);
    expect(await reader.load(5)).toBe(false);
    expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'failed' }));
    expect(await reader.load(5)).toBe(true);
    expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'ready', value: savedProduct }));
  });
});
