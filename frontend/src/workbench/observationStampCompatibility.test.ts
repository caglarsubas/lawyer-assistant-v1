import { describe, expect, it, vi } from 'vitest';
import { finiteObservationTime } from './privateObservationValidation';

const original = (value: string) => Number.isFinite(Date.parse(value));
describe('stateless finite observation timestamp compatibility', () => {
  it.each(['0000-01-01T00:00:00Z', '0099-02-28T23:59:59.999Z', '2024-02-29T00:00:00Z',
    '2026-02-31T00:00:00Z', '2026-10-15T03:06:00+00:00', '2026-10-15T03:06:00.123456Z',
    '2026-10-15T03:06:00+03:00', '2026-10-15T24:00:00Z', '2026-13-01T00:00:00Z',
    '2026-10-15T03:06:60Z', 'October 15, 2026', 'not-a-date'])('matches Date.parse for %s', value => {
    expect(finiteObservationTime(value)).toBe(original(value));
  });
  it('matches the independent parser across Gregorian years, months and every boundary day', () => {
    for (const year of [0, 1, 99, 100, 400, 1900, 2000, 2024, 2026, 9999]) {
      for (let month = 1; month <= 13; month++) for (const day of [0, 1, 28, 29, 30, 31, 32]) {
        const prefix = `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        for (const tail of ['T00:00:00Z', 'T23:59:59.999+00:00', 'T03:06:00+03:00']) {
          const value = prefix + tail; expect(finiteObservationTime(value), value).toBe(original(value));
        }
      }
    }
  });
  it('matches the parser after deterministic single-character mutations and Unicode suffixes', () => {
    const base = '2026-10-15T03:06:00.123Z';
    for (let i = 0; i < base.length; i++) for (const c of ['0', '9', 'a', ' ', '\n', 'İ', '\u0000']) {
      const value = base.slice(0, i) + c + base.slice(i + 1); expect(finiteObservationTime(value), value).toBe(original(value));
    }
  });
  it('uses the unchanged parser for noncanonical rollovers and precision', () => {
    const parse = vi.spyOn(Date, 'parse');
    try { for (const value of ['2026-02-31T00:00:00Z', '2026-10-15T03:06:00.123456Z']) {
      parse.mockClear(); finiteObservationTime(value); expect(parse).toHaveBeenCalledExactlyOnceWith(value);
    } } finally { parse.mockRestore(); }
  });
  it('avoids parsing only the calendar-valid canonical positive subset', () => {
    const parse = vi.spyOn(Date, 'parse');
    try { for (const value of ['2026-10-15T03:06:00Z', '0000-01-01T00:00:00.123+00:00']) {
      parse.mockClear(); expect(finiteObservationTime(value)).toBe(true); expect(parse).not.toHaveBeenCalled();
    } } finally { parse.mockRestore(); }
  });
  it('rechecks a changed value on every invocation without a retained verdict', () => {
    let value = '2026-10-15T03:06:00Z'; expect(finiteObservationTime(value)).toBe(true);
    value = '2026-13-15T03:06:00Z'; expect(finiteObservationTime(value)).toBe(false);
    value = '2026-10-15T03:06:00Z'; expect(finiteObservationTime(value)).toBe(true);
  });
  it('retains the original callers string and forty-character bounds', () => {
    const before = (value: unknown) => typeof value === 'string' && value.length <= 40 && original(value);
    const after = (value: unknown) => typeof value === 'string' && value.length <= 40 && finiteObservationTime(value);
    for (const value of [null, undefined, 0, {}, [], Symbol('invalid'), '2026-10-15T03:06:00Z', ' '.repeat(41), '2026-10-15T03:06:00Z' + ' '.repeat(25)]) expect(after(value)).toBe(before(value));
  });
  it('preserves parser behavior for final line breaks and whitespace', () => {
    for (const suffix of ['\n', '\r', '\r\n', '\u2028', '\u2029', ' ', '\t']) {
      for (const base of ['2026-10-15T03:06:00Z', '2026-10-15', 'October 15, 2026']) {
        const value = base + suffix; expect(finiteObservationTime(value), value).toBe(original(value));
      }
    }
  });
  it('preserves the parser for offsets and unusual fractional precision', () => {
    for (const tail of ['+01:00', '-03:30', '+00:01', 'z', '.1Z', '.12Z', '.1234Z', '.123456789Z']) {
      const value = '2026-10-15T03:06:00' + tail; expect(finiteObservationTime(value), value).toBe(original(value));
    }
  });
});
