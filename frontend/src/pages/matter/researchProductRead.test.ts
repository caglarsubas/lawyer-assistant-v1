import { describe, expect, it, vi } from 'vitest';
import type { Product } from '../../types';
import { createProductReader, productSelectionKey, type ProductRead } from './researchProductRead';

const selection = { matterId: 'private/a', productId: 'saved/b', version: 3 };
const product = { id: selection.productId, version: 3, summary: 'Exact saved text' } as Product;
function deferred() { let resolve!: (value: Product) => void; let reject!: (error: Error) => void; const promise = new Promise<Product>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
describe('selection-bound research reads', () => {
  it('clears the previous result before a refresh, exposes failure and retries the same exact selection', async () => {
    const states: ProductRead[] = []; const fetcher = vi.fn().mockResolvedValueOnce(product).mockRejectedValueOnce(new Error('Read unavailable')).mockResolvedValueOnce(product);
    const reader = createProductReader(selection, state => states.push(state), fetcher);
    expect(await reader.load()).toBe(true); expect(await reader.load()).toBe(false);
    expect(states.map(s => s.status)).toEqual(['loading', 'ready', 'loading', 'failed']);
    expect(states.at(-1)).not.toHaveProperty('value'); expect(await reader.load()).toBe(true);
    expect(fetcher.mock.calls.every(([path]) => path === '/matters/private%2Fa/products/saved%2Fb')).toBe(true);
    expect(states.every(s => s.key === productSelectionKey(selection))).toBe(true);
    expect(states.at(-1)).toMatchObject({ status: 'ready', value: product });
  });
  it.each(['id', 'version'] as const)('withholds a response with the wrong %s', async field => {
    const publish = vi.fn(); const reader = createProductReader(selection, publish, async () => ({ ...product, [field]: field === 'id' ? 'other' : 4 }));
    expect(await reader.load()).toBe(false); expect(publish.mock.calls.map(([s]) => s.status)).toEqual(['loading', 'failed']);
    expect(publish.mock.lastCall?.[0].message).toContain('eşleşmiyor');
  });
  it.each(['resolve', 'reject'] as const)('ignores a late %s after the selection closes even if transport ignores abort', async outcome => {
    const pending = deferred(); const publish = vi.fn(); let signal!: AbortSignal;
    const reader = createProductReader(selection, publish, async (_path, value) => { signal = value; return pending.promise; });
    const read = reader.load(); reader.close(); expect(signal.aborted).toBe(true); expect(reader.active).toBe(false);
    if (outcome === 'resolve') pending.resolve(product); else pending.reject(new Error('late'));
    expect(await read).toBe(false); expect(await reader.load()).toBe(false); expect(publish).toHaveBeenCalledTimes(1);
  });
  it('keeps the newest refresh when responses finish out of order', async () => {
    const first = deferred(); const second = deferred(); const publish = vi.fn();
    const reader = createProductReader(selection, publish, vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise));
    const a = reader.load(); const b = reader.load(); second.resolve(product); expect(await b).toBe(true);
    first.resolve({ ...product, summary: 'obsolete response' }); expect(await a).toBe(false);
    expect(publish.mock.calls.filter(([s]) => s.status === 'ready')).toEqual([[{ key: reader.key, status: 'ready', value: product }]]);
  });
  it('separates otherwise identical selections across matters and versions', () => {
    expect(productSelectionKey(selection)).not.toBe(productSelectionKey({ ...selection, matterId: 'another' }));
    expect(productSelectionKey(selection)).not.toBe(productSelectionKey({ ...selection, version: 4 }));
  });
});
