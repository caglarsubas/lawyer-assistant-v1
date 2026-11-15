import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api';
import { requestAssignments } from './AccessAssignments';
import { conflictRevision, isAdminRevisionConflict } from './AdminRevisionConflict';
import { employeeRolePins } from './FirmAdminPage';

afterEach(() => vi.unstubAllGlobals());

describe('administration conflicts', () => {
  it('distinguishes a rejected revision from a rejected access change', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Ekip değişti; yeniden yükleyin' }), { status: 409 }));
    vi.stubGlobal('fetch', fetchMock);
    const draft = { revision: 4, members: [{ user_id: 'draft-account', supervisor: false, responsible: true }] };
    await expect(requestAssignments('workspaces', 'synthetic-workspace', {
      method: 'PUT', body: JSON.stringify(draft),
    })).rejects.toSatisfy((cause: unknown) => isAdminRevisionConflict(cause, 'workspaces'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/firm-admin/workspaces/synthetic-workspace/team', expect.objectContaining({
      method: 'PUT', body: JSON.stringify(draft), credentials: 'same-origin', cache: 'no-store',
    }));
    expect(isAdminRevisionConflict(new ApiError('En az bir aktif dosya erişimi korunmalı', 409), 'workspaces')).toBe(false);
  });

  it('refuses to attach a snapshot from another target or assignment type', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ target_id: 'other-workspace', revision: 5, members: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ target_id: 'synthetic-workspace', revision: 5, assignments: [] })));
    vi.stubGlobal('fetch', fetchMock);
    await expect(requestAssignments('workspaces', 'synthetic-workspace', {})).rejects.toThrow('seçili hedefle eşleşmiyor');
    await expect(requestAssignments('workspaces', 'synthetic-workspace', {})).rejects.toThrow('seçili hedefle eşleşmiyor');
  });

  it('associates a typed revision conflict with its exact authorized employee', () => {
    const conflict = new ApiError('Çalışan değişti; yenileyin', 409, {
      outcome: 'revision_conflict', target: 'employee', target_id: 'employee-1', current_revision: 4,
    });
    expect(isAdminRevisionConflict(conflict, 'employee', 'employee-1')).toBe(true);
    expect(isAdminRevisionConflict(conflict, 'employee', 'employee-2')).toBe(false);
    expect(isAdminRevisionConflict(conflict, 'role', 'employee-1')).toBe(false);
    expect(conflictRevision(conflict, 3)).toBe(4);
  });

  it('pins only the selected roles from the originally opened directory', () => {
    const original = [{ id: 'selected', revision: 4 }, { id: 'other', revision: 9 }].map(role => ({ ...role, name: role.id, permissions: [], starter: false }));
    const current = original.map(role => ({ ...role, revision: role.revision + 1 }));
    expect(employeeRolePins(['selected'], original)).toEqual({ selected: 4 });
    expect(employeeRolePins(['selected'], current)).toEqual({ selected: 5 });
    expect(employeeRolePins(['missing'], original)).toBeNull();
    expect(employeeRolePins([], original)).toEqual({});
  });
});
