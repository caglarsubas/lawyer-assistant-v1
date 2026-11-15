import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import AccessAssignments from './AccessAssignments';
import { AdminRevisionConflict, conflictRevision, isAdminAccessDenied, isAdminRevisionConflict } from './AdminRevisionConflict';
import { EmployeeRegister, RoleRegister } from './FirmDirectory';
import { request } from '../api';
import { Detail, Field, focusSection, Loading, Notice, PageHeader, SectionIndex } from '../components';
import { messageOf } from '../utils';

export interface FirmRole { id: string; name: string; permissions: string[]; revision: number; starter: boolean }
export interface Employee { id: string; name: string; username: string; professional_role: string; active: boolean; manager_id: string | null; revision: number; role_ids: string[]; permissions: string[] }
export interface FirmData { permissions: { id: string; label: string }[]; employees: Employee[]; roles: FirmRole[] }
interface Change { id: string; action: string; target_id: string; actor_id: string; recorded_at: string }

const emptyEmployee = { name: '', username: '', password: '', professional_role: 'lawyer', active: true, manager_id: null as string | null, role_ids: [] as string[] };

export function employeeRolePins(roleIds: string[], roles: FirmRole[]) {
  const entries: [string, number][] = [];
  for (const id of roleIds) {
    const role = roles.find(item => item.id === id);
    if (!role || !Number.isSafeInteger(role.revision) || role.revision < 1) return null;
    entries.push([id, role.revision]);
  }
  return Object.fromEntries(entries);
}

export default function FirmAdminPage() {
  const [query, setQuery] = useState('');
  const [data, setData] = useState<FirmData | null>(null);
  const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Employee | null>(null);
  const [employee, setEmployee] = useState(emptyEmployee);
  const [employeeRoles, setEmployeeRoles] = useState<FirmRole[]>([]);
  const [employeeError, setEmployeeError] = useState('');
  const [employeeConflict, setEmployeeConflict] = useState<number | null>(null);
  const [role, setRole] = useState<FirmRole | null>(null);
  const [roleName, setRoleName] = useState('');
  const [permissions, setPermissions] = useState<string[]>([]);
  const [roleError, setRoleError] = useState('');
  const [roleConflict, setRoleConflict] = useState(false);
  const [changes, setChanges] = useState<Change[]>([]);
  const read = useRef<AbortController | null>(null);
  const write = useRef<AbortController | null>(null);
  const busy = saving || loading;

  const observedEmployee = data?.employees.find(item => item.id === selected?.id && item.username === selected?.username);
  const observedRole = data?.roles.find(item => item.id === role?.id && !item.starter);
  const expectedRoleRevisions = employeeRolePins(employee.role_ids, employeeRoles);
  const observedRoleRevisions = employeeRolePins(employee.role_ids, data?.roles ?? []);
  const revisedRoles = Object.entries(expectedRoleRevisions ?? {}).filter(([id, revision]) =>
    observedRoleRevisions?.[id] !== revision);
  const currentRolesVerified = Boolean(observedRoleRevisions && expectedRoleRevisions
    && revisedRoles.every(([id, revision]) => observedRoleRevisions[id] >= revision));
  const employeeBaseChanged = Boolean(selected && observedEmployee && (
    observedEmployee.revision > selected.revision || observedEmployee.active !== selected.active || revisedRoles.length));
  const currentEmployee = !loading && !error && selected && observedEmployee && employeeBaseChanged && currentRolesVerified
    && Number.isSafeInteger(observedEmployee.revision)
    && observedEmployee.revision >= (employeeConflict ?? selected.revision) ? observedEmployee : undefined;
  const currentRole = !loading && !error && role && observedRole && observedRole.revision > role.revision ? observedRole : undefined;
  const staleEmployee = Boolean(selected && (employeeConflict !== null || employeeBaseChanged || observedEmployee?.revision !== selected.revision));
  const staleRole = Boolean(role && (roleConflict || observedRole?.revision !== role.revision));
  const availableManagers = data?.employees.filter(item => item.active && item.id !== selected?.id) ?? [];

  const clearAuthorizedData = useCallback((cause: unknown) => {
    read.current?.abort();
    write.current?.abort();
    setData(null);
    setChanges([]);
    setSelected(null);
    setEmployee(emptyEmployee);
    setEmployeeRoles([]);
    setEmployeeConflict(null);
    setEmployeeError('');
    setRole(null);
    setRoleName('');
    setPermissions([]);
    setRoleConflict(false);
    setRoleError('');
    setNotice('');
    setLoading(false);
    setSaving(false);
    setError(messageOf(cause));
  }, []);

  const load = useCallback(async () => {
    read.current?.abort();
    const controller = new AbortController();
    read.current = controller;
    setLoading(true);
    setError('');
    try {
      const options = { signal: controller.signal };
      const [next, history] = await Promise.all([
        request<FirmData>('/firm-admin', options),
        request<{ items: Change[] }>('/firm-admin/changes', options),
      ]);
      if (!controller.signal.aborted) {
        setData(next);
        setChanges(history.items);
      }
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isAdminAccessDenied(cause)) clearAuthorizedData(cause);
      else setError(messageOf(cause));
    } finally {
      if (read.current === controller) read.current = null;
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [clearAuthorizedData]);

  useEffect(() => {
    void load();
    return () => {
      read.current?.abort();
      write.current?.abort();
    };
  }, [load]);

  function selectEmployee(value: Employee | null) {
    setSelected(value);
    setEmployeeRoles(value ? data?.roles ?? [] : []);
    setEmployee(value ? {
      ...emptyEmployee, name: value.name, username: value.username, professional_role: value.professional_role,
      active: value.active, manager_id: value.manager_id, role_ids: value.role_ids,
    } : emptyEmployee);
    setEmployeeError('');
    setEmployeeConflict(null);
    setNotice('');
  }

  function selectRole(value: FirmRole | null) {
    setRole(value);
    setRoleName(value?.name || '');
    setPermissions(value?.permissions || []);
    setRoleError('');
    setRoleConflict(false);
    setNotice('');
  }

  async function saveEmployee(event: FormEvent) {
    event.preventDefault();
    if (busy || write.current || staleEmployee) return;
    const controller = new AbortController();
    write.current = controller;
    setSaving(true);
    setEmployeeError('');
    setNotice('');
    try {
      if (selected) {
        if (!expectedRoleRevisions) throw new Error('Seçilen rollerin revizyonları doğrulanamadı.');
        await request(`/firm-admin/employees/${encodeURIComponent(selected.id)}`, { method: 'PUT', signal: controller.signal, body: JSON.stringify({
          name: employee.name, role_ids: employee.role_ids, manager_id: employee.manager_id,
          active: employee.active, revision: selected.revision, expected_active: selected.active,
          expected_role_revisions: expectedRoleRevisions,
        }) });
      } else {
        await request('/firm-admin/employees', { method: 'POST', signal: controller.signal, body: JSON.stringify({
          name: employee.name, username: employee.username, password: employee.password,
          professional_role: employee.professional_role, role_ids: employee.role_ids, manager_id: employee.manager_id,
        }) });
      }
      if (controller.signal.aborted) return;
      selectEmployee(null);
      setNotice('Çalışan kaydedildi. Etkilenen hesabın yeniden giriş yapması gerekir.');
      await load();
    } catch (cause) {
      if (controller.signal.aborted) return;
      setEmployee(previous => ({ ...previous, password: '' }));
      if (isAdminAccessDenied(cause)) clearAuthorizedData(cause);
      else if (selected && isAdminRevisionConflict(cause, 'employee', selected.id)) {
        setEmployeeConflict(conflictRevision(cause, selected.revision));
        await load();
      } else setEmployeeError(messageOf(cause));
    } finally {
      if (write.current === controller) write.current = null;
      if (!controller.signal.aborted) setSaving(false);
    }
  }

  async function saveRole(event: FormEvent) {
    event.preventDefault();
    if (busy || write.current || staleRole) return;
    const controller = new AbortController();
    write.current = controller;
    setSaving(true);
    setRoleError('');
    setNotice('');
    try {
      const path = role ? `/firm-admin/roles/${encodeURIComponent(role.id)}` : '/firm-admin/roles';
      await request(path, {
        method: role ? 'PUT' : 'POST', signal: controller.signal,
        body: JSON.stringify({ name: roleName, permissions, ...(role ? { revision: role.revision } : {}) }),
      });
      if (controller.signal.aborted) return;
      selectRole(null);
      setNotice('Rol kaydedildi. Bu role bağlı hesapların yeniden giriş yapması gerekir.');
      await load();
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isAdminAccessDenied(cause)) clearAuthorizedData(cause);
      else if (role && isAdminRevisionConflict(cause, 'role')) {
        setRoleConflict(true);
        await load();
      } else setRoleError(messageOf(cause));
    } finally {
      if (write.current === controller) write.current = null;
      if (!controller.signal.aborted) setSaving(false);
    }
  }
  return <div className="page firm-administration"><PageHeader eyebrow="BÜRO YAPILANDIRMASI" title="Büro yönetimi" description="Çalışanları, işlem rollerini ve içerik atamalarını ayrı yönetin." action={<button className="button secondary" onClick={() => void load()} disabled={busy}>{loading ? 'Yükleniyor…' : 'Yenile'}</button>} />
    <Notice>İşlem rolü hangi işlemlerin yapılabileceğini, içerik ataması hangi müvekkil ve çalışma alanlarına erişilebileceğini belirler. Organizasyon yöneticiliği tek başına içerik erişimi sağlamaz.</Notice>
    {data && <SectionIndex items={[{id:'firm-employees',label:'Çalışanlar'},{id:'firm-employee-editor',label:'Çalışan formu'},{id:'firm-roles',label:'Roller ve izinler'},{id:'firm-assignments',label:'İçerik atamaları'},{id:'firm-history',label:'Değişiklik geçmişi'}]} />}
    {error && <Notice error>{error}</Notice>}{notice && <Notice>{notice}</Notice>}
    {!data ? !error && <Loading label="Büro yapılandırması yükleniyor…" /> : <>
      <section className="admin-section" id="firm-employees" tabIndex={-1} aria-labelledby="firm-employees-title"><h2 id="firm-employees-title">Çalışanlar</h2><Field label="Çalışan ara" hint="Ad veya kullanıcı adıyla yalnızca bu listedeki çalışanları filtreleyin.">{id => <input id={id} type="search" value={query} onChange={event => setQuery(event.target.value)} />}</Field><EmployeeRegister data={data} query={query} selectedId={selected?.id} busy={busy || staleEmployee} onSelect={item => { selectEmployee(item); focusSection('firm-employee-editor'); }} /></section>
      <section className="admin-section" id="firm-employee-editor" tabIndex={-1} aria-label="Çalışan formu"><form onSubmit={saveEmployee}><h2>{selected ? `${selected.name} · düzenle` : 'Çalışan ekle'}</h2>
        {selected && <p className="small muted">{selected.username}</p>}
        {employeeError && <Notice error>{employeeError}</Notice>}
        {selected && staleEmployee && <AdminRevisionConflict
          draftRevision={selected.revision} currentRevision={currentEmployee?.revision} busy={busy} checked={!loading && !error}
          onRefresh={() => void load()} onRestart={() => { if (currentEmployee) selectEmployee(currentEmployee); }}>
          {currentEmployee && <dl className="register-fields">
            <div><dt>Çalışan</dt><dd>{currentEmployee.name} · {currentEmployee.username}</dd></div>
            <div><dt>Hesap durumu</dt><dd>{currentEmployee.active ? 'Aktif' : 'Devre dışı'}</dd></div>
            <div><dt>Organizasyon yöneticisi</dt><dd>{data.employees.find(item => item.id === currentEmployee.manager_id)?.username || currentEmployee.manager_id || 'Atanmamış'}</dd></div>
            <div><dt>İşlem rolleri</dt><dd>{currentEmployee.role_ids.map(id => data.roles.find(item => item.id === id)?.name || id).join(', ') || 'İzin yok'}</dd></div>
          </dl>}
          {currentEmployee && revisedRoles.length > 0 && <ul>{revisedRoles.map(([id, revision]) => {
            const latest = data.roles.find(item => item.id === id);
            const permissions = latest?.permissions.map(permission => data.permissions.find(item => item.id === permission)?.label || permission);
            return <li key={id}>{latest?.name || id} · taslak rol sürümü {revision} · {latest ? `güncel rol sürümü ${latest.revision}` : 'güncel rol bulunamadı'}
              {permissions && <p>Güncel izinler · {permissions.join(', ') || 'İzin yok'}</p>}</li>;
          })}</ul>}
        </AdminRevisionConflict>}
        {selected && staleEmployee && <p className="small muted">Kaydedilmemiş çalışan taslağı · sürüm {selected.revision}</p>}
        <div className="form-grid"><div className="field"><label htmlFor="employee-name">Ad soyad</label><input id="employee-name" disabled={busy || staleEmployee} value={employee.name} maxLength={100} required onChange={e => setEmployee({ ...employee, name: e.target.value })} /></div>
        {!selected && <><div className="field"><label htmlFor="employee-username">Kullanıcı adı</label><input id="employee-username" disabled={busy} value={employee.username} autoComplete="off" maxLength={100} required onChange={e => setEmployee({ ...employee, username: e.target.value })} /></div><div className="field"><label htmlFor="employee-password">İlk parola (en az 16 karakter)</label><input id="employee-password" disabled={busy} type="password" autoComplete="new-password" minLength={16} maxLength={200} value={employee.password} required onChange={e => setEmployee({ ...employee, password: e.target.value })} /></div><div className="field"><label htmlFor="employee-profession">Çalışma kimliği</label><select id="employee-profession" disabled={busy} value={employee.professional_role} onChange={e => setEmployee({ ...employee, professional_role: e.target.value })}><option value="lawyer">Avukat</option><option value="curator">Küratör</option></select></div></>}
        <div className="field"><label htmlFor="employee-manager">Organizasyon yöneticisi</label><select id="employee-manager" disabled={busy || staleEmployee} value={employee.manager_id || ''} onChange={e => setEmployee({ ...employee, manager_id: e.target.value || null })}>
          <option value="">Atanmamış</option>
          {employee.manager_id && !availableManagers.some(item => item.id === employee.manager_id) && <option value={employee.manager_id} disabled>{data.employees.find(item => item.id === employee.manager_id)?.username || employee.manager_id} · seçilemiyor</option>}
          {availableManagers.map(item => <option key={item.id} value={item.id}>{item.name} · {item.username}</option>)}
        </select><small>En fazla bir yönetici; bu ilişki dosya erişimi sağlamaz.</small></div></div>
        <fieldset disabled={busy || staleEmployee}><legend>İşlem rolleri</legend>{(selected ? employeeRoles : data.roles).map(item => <label className="check-option" key={item.id}><input type="checkbox" checked={employee.role_ids.includes(item.id)} onChange={e => setEmployee({ ...employee, role_ids: e.target.checked ? [...employee.role_ids, item.id] : employee.role_ids.filter(id => id !== item.id) })} />{item.name}</label>)}
          {employee.role_ids.filter(id => !data.roles.some(item => item.id === id)).map(id => <label className="check-option" key={id}><input type="checkbox" checked onChange={() => setEmployee(previous => ({ ...previous, role_ids: previous.role_ids.filter(old => old !== id) }))} />{id} · rol bulunamadı</label>)}
        </fieldset>
        {selected && <><label className="check-option"><input type="checkbox" disabled={busy || staleEmployee} checked={employee.active} onChange={e => setEmployee({ ...employee, active: e.target.checked })} />Hesap aktif</label><Detail title={staleEmployee ? 'Taslağın dayandığı etkin işlem izinleri' : 'Mevcut etkin işlem izinleri'} variant="technical"><ul>{selected.permissions.map(id => <li key={id}>{data.permissions.find(item => item.id === id)?.label || id}</li>)}</ul><p>Kaydedilen yeni roller bir sonraki girişte uygulanır. İçerik atamaları ayrıca gereklidir.</p></Detail></>}
        <div className="form-actions"><button className="button primary" disabled={busy || staleEmployee}>{saving ? 'Kaydediliyor…' : selected ? 'Çalışanı kaydet' : 'Çalışan ekle'}</button>{selected && <button className="button" type="button" disabled={busy} onClick={() => selectEmployee(null)}>{staleEmployee ? 'Taslağı bırak' : 'Yeni çalışan'}</button>}</div></form></section>
      <section className="admin-section" id="firm-roles" tabIndex={-1} aria-label="Roller ve izinler"><h2>Roller ve izinler</h2><p className="muted">Başlangıç rolleri korunur. Farklı izinler için özel rol oluşturun. Roller dosya ataması değildir.</p><RoleRegister data={data} selectedId={role?.id} busy={busy || staleRole} onSelect={item => { selectRole(item); focusSection('firm-role-editor'); }} /><form id="firm-role-editor" tabIndex={-1} aria-label="Özel rol formu" onSubmit={saveRole}><h3>{role ? 'Özel rolü düzenle' : 'Özel rol oluştur'}</h3>
        {roleError && <Notice error>{roleError}</Notice>}
        {role && staleRole && <AdminRevisionConflict
          draftRevision={role.revision} currentRevision={currentRole?.revision} busy={busy} checked={!loading && !error}
          onRefresh={() => void load()} onRestart={() => { if (currentRole) selectRole(currentRole); }}>
          {currentRole && <dl className="register-fields">
            <div><dt>Rol</dt><dd>{currentRole.name}</dd></div>
            <div><dt>İşlem izinleri</dt><dd>{currentRole.permissions.map(id => data.permissions.find(item => item.id === id)?.label || id).join(', ') || 'İzin yok'}</dd></div>
          </dl>}
        </AdminRevisionConflict>}
        {role && staleRole && <p className="small muted">Kaydedilmemiş rol taslağı · sürüm {role.revision}</p>}
        <div className="field"><label htmlFor="role-name">Rol adı</label><input id="role-name" disabled={busy || staleRole} value={roleName} maxLength={100} required onChange={e => setRoleName(e.target.value)} /></div><fieldset disabled={busy || staleRole}><legend>Desteklenen işlem izinleri</legend>{data.permissions.map(item => <label className="check-option" key={item.id}><input type="checkbox" checked={permissions.includes(item.id)} onChange={e => setPermissions(previous => e.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))} />{item.label}</label>)}</fieldset><p className="muted">Düzenleme, inceleme ve çıktı izinleri görüntüleme izni de gerektirir.</p><div className="form-actions"><button className="button primary" disabled={busy || staleRole}>{role ? 'Rolü kaydet' : 'Rol oluştur'}</button>{role && <button type="button" className="button" disabled={busy} onClick={() => selectRole(null)}>{staleRole ? 'Taslağı bırak' : 'Yeni rol'}</button>}</div></form></section>
      <AccessAssignments employees={data.employees} onSaved={() => { void load(); }} onAccessDenied={clearAuthorizedData} /><section className="admin-section" id="firm-history" tabIndex={-1} aria-label="Değişiklik geçmişi"><h2>Son yapılandırma değişiklikleri</h2><p className="muted">Son 100 kayıt · içerik ve parola bu listede yer almaz.</p><ol>{changes.map(item => <li key={item.id}>{new Date(item.recorded_at).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul' })} · {item.action} · {data.employees.find(person => person.id === item.actor_id)?.name || item.actor_id}</li>)}</ol></section>
    </>}
  </div>;
}
