import { describe, expect, it } from 'vitest';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { hasExactKeys, scalarDataRecordsEqual } from './privateObservationValidation';

const reference = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const compare = (a: unknown, b: unknown) => scalarDataRecordsEqual(a, b) ?? reference(a, b);
const scalars = [null, true, false, 0, -0, 1, -1, Number.MAX_SAFE_INTEGER, Number.MIN_VALUE, '', 'İstanbul', '\ud800', '\n"\\', '😀'];

describe('stateless scalar data comparison with the original canonical fallback', () => {
  it.each(scalars)('matches canonical JSON for scalar %# and reordered keys', value => {
    const a = { value, id: 'fixed', sequence: 43, packet_sha256: 'a'.repeat(64) };
    const b = Object.fromEntries(Object.entries(a).reverse());
    expect(scalarDataRecordsEqual(a, b)).toBe(true);
    expect(compare(a, b)).toBe(reference(a, b));
    b.id = 'different'; expect(compare(a, b)).toBe(reference(a, b)); expect(compare(a, b)).toBe(false);
  });
  it.each([undefined, NaN, Infinity, -Infinity, 1n, Symbol('unknown'), () => 'x', [], {}, new Date(0)])('requires the original fallback for non-scalar value %#', value => {
    expect(scalarDataRecordsEqual({ value }, { value })).toBeNull();
  });
  it.each([null, undefined, [], 1, 'record', true, new Date(0)])('withholds the fast path for non-record %#', value => {
    expect(scalarDataRecordsEqual(value, {})).toBeNull(); expect(scalarDataRecordsEqual({}, value)).toBeNull();
  });
  it('retains own pollution-shaped keys, integer keys and null prototypes', () => {
    const entries: [string, unknown][] = [['10', 'ten'], ['2', 'two'], ['__proto__', 'data'], ['constructor', null], ['toString', false], ['toJSON', 'data']];
    const a = Object.fromEntries(entries), b = Object.create(null) as Record<string, unknown>;
    for (const [key, value] of [...entries].reverse()) b[key] = value;
    expect(scalarDataRecordsEqual(a, b)).toBe(true); expect(compare(a, b)).toBe(reference(a, b));
    b.__proto__ = 'changed'; expect(compare(a, b)).toBe(false); expect(compare(a, b)).toBe(reference(a, b));
    expect(Object.getPrototypeOf(a)).toBe(Object.prototype); expect(Object.getPrototypeOf(b)).toBeNull();
  });
  it('does not invoke accessors while deciding to use the canonical fallback', () => {
    let reads = 0; const a = Object.defineProperty({}, 'value', { enumerable: true, get: () => { reads++; return 'fixed'; } });
    expect(scalarDataRecordsEqual(a, { value: 'fixed' })).toBeNull(); expect(reads).toBe(0);
    expect(compare(a, { value: 'fixed' })).toBe(true); expect(reads).toBe(1);
  });
  it('uses the canonical fallback for custom prototypes and inherited toJSON hooks', () => {
    expect(scalarDataRecordsEqual(Object.assign(Object.create({ inherited: true }), { id: 'x' }), { id: 'x' })).toBeNull();
    const saved = Object.getOwnPropertyDescriptor(Object.prototype, 'toJSON');
    try {
      Object.defineProperty(Object.prototype, 'toJSON', { configurable: true, value: () => 'hook' });
      expect(scalarDataRecordsEqual({ id: 'x' }, { id: 'x' })).toBeNull();
    } finally {
      if (saved) Object.defineProperty(Object.prototype, 'toJSON', saved); else Reflect.deleteProperty(Object.prototype, 'toJSON');
    }
  });
  it('retains undefined omission, nested values and non-finite semantics in the fallback', () => {
    for (const [a, b] of [[{ x: undefined }, {}], [{ x: NaN }, { x: null }], [{ x: [1, undefined] }, { x: [1, null] }], [{ x: { b: 1, a: 2 } }, { x: { a: 2, b: 1 } }]]) {
      expect(scalarDataRecordsEqual(a, b)).toBeNull(); expect(compare(a, b)).toBe(reference(a, b));
    }
    expect(() => compare({ x: 1n }, {})).toThrow(TypeError);
  });
  it('does not weaken exact-key validation, including unexpected undefined keys', () => {
    const a = { id: 'fixed', unexpected: undefined };
    expect(hasExactKeys(a, ['id'])).toBe(false); expect(scalarDataRecordsEqual(a, { id: 'fixed' })).toBeNull();
  });
  it('observes mutations and additional scalar keys afresh on every call', () => {
    const a: Record<string, unknown> = { id: 'fixed', revision: 42 }, b = { id: 'fixed', revision: 42 };
    expect(scalarDataRecordsEqual(a, b)).toBe(true); a.revision = 43; expect(scalarDataRecordsEqual(a, b)).toBe(false);
    a.revision = 42; a.extra = true; expect(scalarDataRecordsEqual(a, b)).toBe(false); delete a.extra; expect(scalarDataRecordsEqual(a, b)).toBe(true);
  });
  it('agrees with the unchanged canonical serializer on 10,000 deterministic record pairs', () => {
    let seed = 918273; const next = () => (seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0);
    const names = ['id', 'state', 'sequence', 'recorded_at', 'packet_sha256', 'manifest_sha256', 'previous_review_id', '__proto__', '2', '10'];
    for (let n = 0; n < 10000; n++) {
      const entries = names.slice(0, 1 + next() % names.length).map(key => [key, scalars[next() % scalars.length]] as const);
      const a = Object.fromEntries(entries), b = Object.fromEntries([...entries].reverse());
      if (n % 3 === 0) b[entries[0][0]] = 'changed-' + n;
      if (n % 5 === 0) delete b[entries.at(-1)![0]];
      expect(compare(a, b)).toBe(reference(a, b));
    }
  });
});
