import { describe, expect, it } from 'vitest';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { plainObservationDataEqual } from './plainObservationDataEqual';

const reference = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const compare = (a: unknown, b: unknown) => plainObservationDataEqual(a, b) ?? reference(a, b);
describe('fresh bounded observation equality with canonical fallback', () => {
  it.each([
    [null, null], [true, false], [0, -0], ['x', 'y'],
    [{ a: 1, b: null }, { b: null, a: 1 }],
    [{ metadata: { analysis: { revision: 3, current: 'v' } }, selected: { id: 'r' } }, { selected: { id: 'r' }, metadata: { analysis: { current: 'v', revision: 3 } } }],
    [{ filters: { customer_ids: ['A', 'B'], date: '2026-10-18' } }, { filters: { customer_ids: ['B', 'A'], date: '2026-10-18' } }],
    [{ value: undefined }, {}], [[undefined], [null]], [{ n: NaN }, { n: null }],
    [{ n: Infinity }, { n: null }], [{ f: () => 1 }, {}],
    [Object.create(null, { id: { value: 'x', enumerable: true } }), { id: 'x' }],
    [Object.fromEntries([['__proto__', 'x'], ['constructor', 'y']]), Object.fromEntries([['constructor', 'y'], ['__proto__', 'x']])],
  ])('agrees with canonical equality for case %#', (a, b) => expect(compare(a, b)).toBe(reference(a, b)));
  it('checks complete values afresh after nested mutation, including undefined extras', () => {
    const a = { selected: { id: 'r', packet: 'fixed' }, filters: { customer_ids: ['A', 'B'] } }, b = structuredClone(a);
    expect(plainObservationDataEqual(a, b)).toBe(true);
    b.selected.packet = 'changed'; expect(plainObservationDataEqual(a, b)).toBe(false);
    b.selected.packet = 'fixed'; Object.assign(b.selected, { extra: undefined });
    expect(plainObservationDataEqual(a, b)).toBeNull(); expect(compare(a, b)).toBe(reference(a, b));
  });
  it('does not execute getters before falling back', () => {
    let reads = 0; const a = Object.defineProperty({}, 'id', { enumerable: true, get: () => { reads++; return 'r'; } });
    expect(plainObservationDataEqual(a, { id: 'r' })).toBeNull(); expect(reads).toBe(0);
    expect(compare(a, { id: 'r' })).toBe(true); expect(reads).toBe(1);
  });
  it('falls back for sparse arrays, custom mapping, dates and custom prototypes', () => {
    for (const a of [Array(1), Object.assign(['x'], { map: () => ['y'] }), new Date('2026-01-01'), Object.create({ inherited: true })])
      expect(plainObservationDataEqual(a, a)).toBeNull();
  });
  it('does not retain prototype JSON-hook verdicts', () => {
    expect(plainObservationDataEqual({ id: 'r' }, { id: 'r' })).toBe(true);
    Object.defineProperty(Object.prototype, 'toJSON', { configurable: true, value: () => 'hook' });
    try { expect(plainObservationDataEqual({ id: 'r' }, { id: 'r' })).toBeNull(); } finally { delete (Object.prototype as { toJSON?: unknown }).toJSON; }
    Object.defineProperty(Array.prototype, 'toJSON', { configurable: true, value: () => 'hook' });
    try { expect(plainObservationDataEqual(['r'], ['r'])).toBeNull(); } finally { delete (Array.prototype as unknown as { toJSON?: unknown }).toJSON; }
    expect(plainObservationDataEqual({ id: 'r' }, { id: 'r' })).toBe(true);
  });
  it('falls back at the depth bound and for cycles without creating a history model', () => {
    const deep = { a: { b: { c: { d: { id: 'r' } } } } }; expect(plainObservationDataEqual(deep, deep)).toBeNull();
    const cycle: { next?: unknown } = {}; cycle.next = cycle; expect(plainObservationDataEqual(cycle, cycle)).toBeNull();
  });
  it('preserves canonical throws for unsupported big integers', () => {
    expect(plainObservationDataEqual({ value: 1n }, { value: 1n })).toBeNull();
    expect(() => compare({ value: 1n }, { value: 1n })).toThrow();
  });
});
