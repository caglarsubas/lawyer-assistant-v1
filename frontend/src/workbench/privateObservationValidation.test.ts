import { describe, expect, it } from 'vitest';
import { hasExactKeys, validCalendarDay } from './privateObservationValidation';

const oldKeys = (value: object, expected: string[]) => JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
const oldDay = (value: string) => value === '' || /^\d{4}-\d{2}-\d{2}$/.test(value) && value.slice(0, 4) !== '0000'
  && Number.isFinite(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;

describe('fresh private observation primitives', () => {
  it.each([
    [{}, [], true], [{ a: undefined }, ['a'], true], [{ a: 1, b: 2 }, ['b', 'a'], true],
    [{ a: 1, b: undefined }, ['a'], false], [{ a: 1 }, ['a', 'b'], false],
    [{ a: 1, c: 2 }, ['a', 'b'], false], [{ a: 1, b: 2 }, ['a', 'a'], false],
  ] as [object, string[], boolean][])('checks exact own enumerable keys for %j', (value, expected, accepted) => {
    expect(hasExactKeys(value, expected)).toBe(accepted);
    expect(hasExactKeys(value, expected)).toBe(oldKeys(value, expected));
  });
  it('checks each invocation afresh after key mutation, including undefined extras', () => {
    const value: Record<string, unknown> = { selected: 'event', packet: 'hash' };
    const expected = Object.freeze(['selected', 'packet']);
    expect(hasExactKeys(value, expected)).toBe(true);
    value.extra = undefined; expect(hasExactKeys(value, expected)).toBe(false);
    delete value.extra; expect(hasExactKeys(value, expected)).toBe(true);
    delete value.packet; value.redirect = 'hash'; expect(hasExactKeys(value, expected)).toBe(false);
    expect(expected).toEqual(['selected', 'packet']);
  });
  it('preserves inherited, non-enumerable, symbol and prototype-named key behavior', () => {
    const value = Object.create({ inherited: 1 });
    Object.defineProperty(value, 'hidden', { value: 2 }); value[Symbol('symbol')] = 3;
    expect(hasExactKeys(value, [])).toBe(true);
    expect(hasExactKeys(value, ['inherited'])).toBe(false);
    const own = Object.fromEntries([['__proto__', undefined], ['constructor', 1], ['toJSON', null]]);
    expect(hasExactKeys(own, ['toJSON', '__proto__', 'constructor'])).toBe(true);
    expect(hasExactKeys(own, ['toJSON', 'constructor'])).toBe(false);
  });
  it('agrees with the previous shape predicate across every subset of eight special keys', () => {
    const names = ['a', 'selected', 'packet', 'context', '0', '10', '__proto__', 'constructor'];
    for (let mask = 0; mask < 256; mask++) {
      const keys = names.filter((_, i) => mask & (1 << i)), value = Object.fromEntries(keys.map(key => [key, undefined]));
      for (const expected of [keys, [...keys].reverse(), [...keys, 'extra'], names, keys.length ? [...keys.slice(1), keys[0], keys[0]] : ['a']]) {
        if (hasExactKeys(value, expected) !== oldKeys(value, expected)) throw new Error(`Shape acceptance changed for mask ${mask}`);
      }
    }
  });
  it.each([
    ['', true], ['0001-01-01', true], ['9999-12-31', true], ['0000-01-01', false],
    ['1900-02-29', false], ['2000-02-29', true], ['2100-02-29', false], ['2400-02-29', true],
    ['2024-02-29', true], ['2025-02-29', false], ['2026-04-31', false], ['2026-04-30', true],
    ['2026-12-31', true], ['2026-01-00', false], ['2026-00-01', false], ['2026-13-01', false],
    ['2026-1-01', false], ['2026-01-1', false], [' 2026-01-01', false], ['2026-01-01 ', false],
    ['２０２６-01-01', false], ['2026-01-01T00:00:00Z', false], ['10000-01-01', false],
  ] as [string, boolean][])('preserves portfolio date acceptance for %j', (value, accepted) => {
    expect(validCalendarDay(value)).toBe(accepted);
    expect(validCalendarDay(value)).toBe(oldDay(value));
  });
  it('rejects trailing line terminators that regular-expression dollar anchors alone allow', () => {
    for (const suffix of ['\n', '\r', '\r\n', '\u2028', '\u2029']) {
      const value = '2026-01-01' + suffix;
      expect(validCalendarDay(value)).toBe(false);
      expect(validCalendarDay(value)).toBe(oldDay(value));
    }
  });
  it('agrees with Date parsing across the complete 400-year Gregorian cycle and invalid month/day boundaries', () => {
    let checked = 0;
    for (let year = 2000; year < 2400; year++) for (let month = 0; month <= 13; month++) for (let day = 0; day <= 32; day++) {
      const value = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      if (validCalendarDay(value) !== oldDay(value)) throw new Error(`Calendar acceptance changed for ${value}`);
      checked++;
    }
    expect(checked).toBe(184800);
  });
});
