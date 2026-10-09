import { request } from './api';
import type { Session } from './types';

/** Clear private views on suspension; verify before remounting and on active polling. */
export function monitorSession(onFresh: (session: Session) => void, onLost: (cause: unknown) => void, onChecking: () => void) {
  let alive = true; let checking = false; let controller: AbortController | null = null;
  const visible = () => document.visibilityState !== 'hidden';
  async function verify() {
    if (checking || !visible()) return;
    checking = true; controller = new AbortController();
    const pending = controller;
    const timeout = window.setTimeout(() => pending.abort(), 4000);
    try {
      const value = await request<Session>('/auth/me', { signal: pending.signal });
      if (alive && !pending.signal.aborted && visible()) onFresh(value);
    } catch (cause) { if (alive) onLost(cause); }
    finally { window.clearTimeout(timeout); checking = false; }
  }
  const resume = () => { onChecking(); void verify(); };
  const timer = window.setInterval(() => { void verify(); }, 5000);
  document.addEventListener('visibilitychange', resume); window.addEventListener('focus', resume); window.addEventListener('pageshow', resume);
  return () => { alive = false; controller?.abort(); window.clearInterval(timer); document.removeEventListener('visibilitychange', resume); window.removeEventListener('focus', resume); window.removeEventListener('pageshow', resume); };
}
