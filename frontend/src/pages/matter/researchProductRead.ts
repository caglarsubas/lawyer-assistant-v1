import { request } from '../../api';
import type { Product } from '../../types';
import { messageOf } from '../../utils';

export interface ProductSelection { matterId: string; productId: string; version?: number }
export type ProductRead = { key: string } & (
  { status: 'loading' } | { status: 'ready'; value: Product } | { status: 'failed'; message: string }
);
export function productSelectionKey(selection: ProductSelection) {
  return JSON.stringify([selection.matterId, selection.productId, selection.version ?? null]);
}

/** One selected output owns its reads. Aborting alone cannot reject a late response. */
export function createProductReader(selection: ProductSelection, publish: (state: ProductRead) => void,
  fetchProduct = (path: string, signal: AbortSignal) => request<Product>(path, { signal })) {
  const key = productSelectionKey(selection);
  let closed = false; let generation = 0; let controller: AbortController | undefined;
  return {
    key,
    get active() { return !closed; },
    close() { closed = true; generation++; controller?.abort(); },
    async load() {
      if (closed) return false;
      const current = ++generation; controller?.abort(); controller = new AbortController();
      publish({ key, status: 'loading' });
      try {
        const value = await fetchProduct(`/matters/${encodeURIComponent(selection.matterId)}/products/${encodeURIComponent(selection.productId)}`, controller.signal);
        if (closed || current !== generation) return false;
        if (value.id !== selection.productId || (selection.version !== undefined && value.version !== selection.version)) {
          throw new Error('Çıktının kimliği veya sürümü seçiminizle eşleşmiyor. Çalışma alanını yenileyip yeniden seçin.');
        }
        publish({ key, status: 'ready', value }); return true;
      } catch (cause) {
        if (!closed && current === generation) publish({ key, status: 'failed', message: messageOf(cause) });
        return false;
      }
    },
  };
}
