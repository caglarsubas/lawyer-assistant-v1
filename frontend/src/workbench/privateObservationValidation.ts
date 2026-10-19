/** Exact enumerable own keys, checked afresh without sorting or serialization. */
export function hasExactKeys(value: object, expected: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === expected.length && actual.every(key => expected.includes(key));
}

/** Manual portfolio date filters use Gregorian dates from year 0001 through 9999. */
export function validCalendarDay(value: string): boolean {
  if (value === '') return true;
  if (typeof value !== 'string' || value.length !== 10 || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const year = Number(value.slice(0, 4)), month = Number(value.slice(5, 7)), day = Number(value.slice(8, 10));
  if (year === 0 || month < 1 || month > 12 || day < 1) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const limit = month === 2 ? leap ? 29 : 28 : [4, 6, 9, 11].includes(month) ? 30 : 31;
  return day <= limit;
}

/** Compare only scalar data records, without sorting, serialization or retained verdicts.
 * null requires the caller's original canonical-JSON comparison. This is not
 * observation validation; callers must still validate their complete history.
 */
export function scalarDataRecordsEqual(left: unknown, right: unknown): boolean | null {
  if (!left || !right || typeof left !== 'object' || typeof right !== 'object' || Array.isArray(left) || Array.isArray(right)
    || Object.hasOwn(Object.prototype, 'toJSON')) return null;
  for (const value of [left, right]) {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return null;
  }
  const a = left as Record<string, unknown>, b = right as Record<string, unknown>;
  const aKeys = Object.keys(a), bKeys = Object.keys(b);
  for (const [record, fields] of [[a, aKeys], [b, bKeys]] as const) {
    for (const field of fields) {
      const descriptor = Object.getOwnPropertyDescriptor(record, field)!;
      if (!('value' in descriptor)) return null;
      const value: unknown = descriptor.value;
      if (value !== null && typeof value !== 'string' && typeof value !== 'boolean'
        && !(typeof value === 'number' && Number.isFinite(value))) return null;
    }
  }
  return aKeys.length === bKeys.length && aKeys.every(field => Object.hasOwn(b, field) && a[field] === b[field]);
}

// Calendar-valid in every month; other Date.parse inputs retain the original path.
const canonicalUtcStamp = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|1\d|2[0-8])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{3})?(?:Z|\+00:00)$/;
/** Stateless finite-time check only; no parsed value or validation verdict is retained. */
export function finiteObservationTime(value: string): boolean {
  return canonicalUtcStamp.test(value) || Number.isFinite(Date.parse(value));
}
