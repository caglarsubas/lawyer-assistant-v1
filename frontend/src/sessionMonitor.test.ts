import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { monitorSession } from './sessionMonitor';

const value = { user: { id: 'u1', name: 'Synthetic', role: 'lawyer', firm_id: 'f1', permissions: ['matter.read'] }, csrf_token: 'synthetic-csrf' };
describe('open-view session freshness', () => {
  let stop: (() => void) | undefined;
  let visibility: 'visible' | 'hidden'; let documentEvents: EventTarget; let windowEvents: EventTarget;
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    vi.useFakeTimers(); visibility = 'visible'; documentEvents = new EventTarget(); windowEvents = new EventTarget(); fetchMock.mockReset();
    vi.stubGlobal('document', { get visibilityState() { return visibility; }, addEventListener: documentEvents.addEventListener.bind(documentEvents), removeEventListener: documentEvents.removeEventListener.bind(documentEvents) });
    vi.stubGlobal('window', { setTimeout, clearTimeout, setInterval, clearInterval, addEventListener: windowEvents.addEventListener.bind(windowEvents), removeEventListener: windowEvents.removeEventListener.bind(windowEvents) });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => { stop?.(); stop = undefined; vi.useRealTimers(); vi.unstubAllGlobals(); });
  it('detects revoked sessions without another user action or private-resource request', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'revoked' }), { status: 401 }));
    const lost = vi.fn(); const fresh = vi.fn(); stop = monitorSession(fresh, lost, vi.fn());
    await vi.advanceTimersByTimeAsync(5000);
    expect(lost).toHaveBeenCalledWith(expect.objectContaining({ status: 401 })); expect(fresh).not.toHaveBeenCalled();
  });
  it('removes private views when hidden and verifies the changed identity before resuming', async () => {
    const checking = vi.fn(); const fresh = vi.fn(); stop = monitorSession(fresh, vi.fn(), checking);
    visibility = 'hidden'; documentEvents.dispatchEvent(new Event('visibilitychange'));
    expect(checking).toHaveBeenCalledOnce(); await vi.advanceTimersByTimeAsync(5000); expect(fetchMock).not.toHaveBeenCalled();
    visibility = 'visible'; fetchMock.mockResolvedValue(new Response(JSON.stringify({ ...value, user: { ...value.user, id: 'u2' } })));
    documentEvents.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(0);
    expect(fresh).toHaveBeenCalledWith(expect.objectContaining({ user: expect.objectContaining({ id: 'u2' }) }));
  });
  it('withholds views when verification hangs and cancels outstanding reads on unmount', async () => {
    fetchMock.mockImplementation((_url, options) => new Promise((_resolve, reject) => options?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))));
    const lost = vi.fn(); stop = monitorSession(vi.fn(), lost, vi.fn()); windowEvents.dispatchEvent(new Event('focus'));
    await vi.advanceTimersByTimeAsync(4000); expect(lost).toHaveBeenCalledOnce();
    windowEvents.dispatchEvent(new Event('focus')); stop(); stop = undefined; await vi.advanceTimersByTimeAsync(0);
    expect(lost).toHaveBeenCalledOnce();
  });
});
