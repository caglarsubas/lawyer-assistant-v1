import { ApiError, request } from '../api';
import type { PublicSourceDetail } from '../types';
import { messageOf } from '../utils';

export function sameCuratorSource(previous: PublicSourceDetail, current: PublicSourceDetail) {
  return previous.id === current?.id
    && previous.source_version_id === current.source_version_id
    && Boolean(current.artifacts)
    && Object.keys(previous.artifacts).length === Object.keys(current.artifacts).length
    && Object.entries(previous.artifacts).every(([name, artifact]) =>
      artifact.sha256 === current.artifacts[name]?.sha256 && artifact.bytes === current.artifacts[name]?.bytes);
}

export async function writeCuratorReview<T>(path: string, readPath: string, payload: unknown, signal?: AbortSignal): Promise<
  | { state: T; conflict: false }
  | { state: T | null; conflict: true; reason: string; refreshError?: string }
> {
  try {
    return { state: await request<T>(path, { method: 'POST', body: JSON.stringify(payload), signal }), conflict: false };
  } catch (cause) {
    if (!(cause instanceof ApiError) || cause.status !== 409 || signal?.aborted) throw cause;
    try {
      return { state: await request<T>(readPath, { signal }), conflict: true, reason: cause.message };
    } catch (refreshCause) {
      if (signal?.aborted || (refreshCause instanceof ApiError && [401, 403].includes(refreshCause.status))) throw refreshCause;
      return { state: null, conflict: true, reason: cause.message, refreshError: messageOf(refreshCause) };
    }
  }
}
