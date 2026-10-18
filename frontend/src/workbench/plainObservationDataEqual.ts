/** Stateless equality for bounded plain observation data. Unsupported values require
 * the caller's unchanged canonical-JSON fallback. Never validates or caches history. */
export function plainObservationDataEqual(left: unknown, right: unknown): boolean | null {
  if (Object.hasOwn(Object.prototype, 'toJSON') || Object.hasOwn(Array.prototype, 'toJSON')) return null;
  const scalar = (value: unknown) => value === null || typeof value === 'string' || typeof value === 'boolean'
    || typeof value === 'number' && Number.isFinite(value);
  function visit(a: unknown, b: unknown, depth: number): boolean | null {
    if (scalar(a) && scalar(b)) return a === b;
    if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || depth === 4) return null;
    const arrays = Array.isArray(a);
    if (arrays !== Array.isArray(b)) return null;
    for (const value of [a, b]) {
      const prototype = Object.getPrototypeOf(value);
      if (arrays ? prototype !== Array.prototype || Object.hasOwn(value, 'map') : prototype !== Object.prototype && prototype !== null) return null;
    }
    const x = a as Record<string, unknown>, y = b as Record<string, unknown>, ak = Object.keys(x), bk = Object.keys(y);
    if (arrays && (ak.length !== (a as unknown[]).length || bk.length !== (b as unknown[]).length
      || ak.some((key, i) => key !== String(i)) || bk.some((key, i) => key !== String(i)))) return null;
    let same = ak.length === bk.length;
    for (const key of ak) {
      const av = Object.getOwnPropertyDescriptor(x, key)!;
      if (!('value' in av)) return null;
      const bv = Object.getOwnPropertyDescriptor(y, key);
      if (bv && !('value' in bv)) return null;
      const child = visit(av.value, bv ? bv.value : av.value, depth + 1);
      if (child === null) return null;
      if (!bv || !child) same = false;
    }
    for (const key of bk) if (!Object.hasOwn(x, key)) {
      const bv = Object.getOwnPropertyDescriptor(y, key)!;
      if (!('value' in bv) || visit(bv.value, bv.value, depth + 1) === null) return null;
      same = false;
    }
    return same;
  }
  return visit(left, right, 0);
}
