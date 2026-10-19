import { describe, expect, it } from 'vitest';
import { compareDestinationIdentities } from './comparisonReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';
const observation = (observed_at: string): ReviewPathDestination => ({ metadata: { observed_at, analysis: { revision: 4, current_version_id: 'v' }, historical_review: { state: 'unknown' } }, head: null } as unknown as ReviewPathDestination);
function rejects(previous: string, current: string): boolean { try { compareDestinationIdentities(observation(previous), observation(current)); return false; } catch { return true; } }
const cases: [string, string, string][] = [
  ['canonical UTC', '2026-10-15T03:04:00Z', '2026-10-15T03:06:00Z'],
  ['canonical milliseconds', '2026-10-15T03:04:00.100Z', '2026-10-15T03:04:00.099Z'],
  ['zero UTC offset', '2026-10-15T03:04:00.100+00:00', '2026-10-15T03:04:00.099+00:00'],
  ['year zero', '0000-01-01T00:00:00Z', '0001-01-01T00:00:00Z'],
  ['year upper bound', '9999-01-01T00:00:00Z', '9998-12-28T23:59:59Z'],
  ['cross month', '2024-02-28T23:59:59Z', '2024-03-01T00:00:00Z'],
  ['leap day fallback', '2024-02-29T23:59:59Z', '2024-03-01T00:00:00Z'],
  ['rollover fallback', '2024-02-30T00:00:00Z', '2024-03-01T00:00:00Z'],
  ['month end fallback', '2026-01-31T23:59:59Z', '2026-02-01T00:00:00Z'],
  ['midnight24 fallback', '2026-10-15T24:00:00Z', '2026-10-16T00:00:00Z'],
  ['offset fallback', '2026-10-15T03:00:00+03:00', '2026-10-15T00:00:00Z'],
  ['mixed precision fallback', '2026-10-15T00:00:00.1Z', '2026-10-15T00:00:00.099Z'],
  ['mixed length fallback', '2026-10-15T00:00:00Z', '2026-10-15T00:00:00.001Z'],
  ['invalid month fallback', '2026-13-15T00:00:00Z', '2026-10-15T00:00:00Z'],
  ['invalid second fallback', '2026-10-15T23:59:60Z', '2026-10-16T00:00:00Z'],
  ['same invalid strings', 'unknown', 'unknown'],
  ['date-only fallback', '2026-10-15', '2026-10-16'],
];
describe('observation timestamp comparison compatibility', () => {
  it.each(cases)('retains Date.parse ordering for %s', (_name, previous, current) => {
    expect(rejects(previous, current)).toBe(Date.parse(current) < Date.parse(previous));
    expect(rejects(current, previous)).toBe(Date.parse(previous) < Date.parse(current));
  });
  it('matches original comparison over two thousand varied valid and invalid pairs', () => {
    for (let n = 0; n < 2000; n++) {
      const day = String(1 + n % 31).padStart(2, '0'), month = String(1 + n % 12).padStart(2, '0'), year = String(n % 3 ? 2024 + n % 4 : n % 10000).padStart(4, '0');
      const previous = `${year}-${month}-${day}T03:04:00${n % 2 ? '.100' : ''}Z`, current = `${year}-${month}-${day}T03:04:00${n % 2 ? '.099' : ''}Z`;
      expect(rejects(previous, current)).toBe(Date.parse(current) < Date.parse(previous));
      expect(rejects(current, previous)).toBe(Date.parse(previous) < Date.parse(current));
    }
  });
  it('observes changed timestamps and revisions afresh without cached validation', () => {
    const before = observation('2026-10-15T03:04:00Z'), after = observation('2026-10-15T03:05:00Z');
    expect(() => compareDestinationIdentities(before, after)).not.toThrow(); after.metadata.observed_at = '2026-10-15T03:03:00Z';
    expect(() => compareDestinationIdentities(before, after)).toThrow(); after.metadata.observed_at = before.metadata.observed_at; after.metadata.analysis.revision = 3;
    expect(() => compareDestinationIdentities(before, after)).toThrow();
  });
  it('retains fallback coercion order for non-string runtime values', () => {
    const calls: string[] = []; const current = { toString() { calls.push('current'); return '2026-10-15T03:03:00Z'; } }, previous = { toString() { calls.push('previous'); return '2026-10-15T03:04:00Z'; } };
    expect(rejects(previous as unknown as string, current as unknown as string)).toBe(true); expect(calls).toEqual(['current', 'previous']);
  });
});
