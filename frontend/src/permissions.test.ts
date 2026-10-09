import { describe, expect, it } from 'vitest';
import { hasFirmAdministration } from './permissions';

describe('administration navigation', () => {
  it('requires the server-granted configuration action', () => {
    expect(hasFirmAdministration(undefined)).toBe(false);
    expect(hasFirmAdministration(['matter.read', 'matter.write'])).toBe(false);
    expect(hasFirmAdministration(['firm.manage'])).toBe(true);
  });
});
