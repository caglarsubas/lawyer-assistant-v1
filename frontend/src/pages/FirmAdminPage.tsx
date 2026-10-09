import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { post, request } from '../api';
import { Loading, Notice } from '../components';
import { messageOf } from '../utils';

export interface FirmRole { id: string; name: string; permissions: string[]; revision: number; starter: boolean }
export interface Employee { id: string; name: string; username: string; professional_role: string; active: boolean; manager_id: string | null; revision: number; role_ids: string[]; permissions: string[] }
export interface FirmData { permissions: { id: string; label: string }[]; employees: Employee[]; roles: FirmRole[] }
interface Change { id: string; action: string; target_id: string; actor_id: string; recorded_at: string }

const emptyEmployee = { name: '', username: '', password: '', professional_role: 'lawyer', active: true, manager_id: null as string | null, role_ids: [] as string[] };

export default function FirmAdminPage() {
  const [data, setData] = useState<FirmData | null>(null);
  const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Employee | null>(null);
  const [employee, setEmployee] = useState(emptyEmployee);
  const [role, setRole] = useState<FirmRole | null>(null);
  const [roleName, setRoleName] = useState(''); const [permissions, setPermissions] = useState<string[]>([]);
  const [changes, setChanges] = useState<Change[]>([]);
  const load = useCallback(async () => {
    try {
      const [next, history] = await Promise.all([request<FirmData>('/firm-admin'), request<{ items: Change[] }>('/firm-admin/changes')]);
      setData(next); setChanges(history.items);
    } catch (cause) { setData(null); setChanges([]); setSelected(null); setRole(null); setEmployee(emptyEmployee); setPermissions([]); setError(messageOf(cause)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  function selectEmployee(value: Employee | null) {
    setSelected(value); setEmployee(value ? { ...emptyEmployee, name: value.name, username: value.username, professional_role: value.professional_role, active: value.active, manager_id: value.manager_id, role_ids: value.role_ids } : emptyEmployee);
    setError(''); setNotice('');
  }
  function selectRole(value: FirmRole | null) { setRole(value); setRoleName(value?.name || ''); setPermissions(value?.permissions || []); setError(''); }
  async function saveEmployee(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      if (selected) await request(`/firm-admin/employees/${encodeURIComponent(selected.id)}`, { method: 'PUT', body: JSON.stringify({ name: employee.name, role_ids: employee.role_ids, manager_id: employee.manager_id, active: employee.active, revision: selected.revision }) });
      else await post('/firm-admin/employees', { name: employee.name, username: employee.username, password: employee.password, professional_role: employee.professional_role, role_ids: employee.role_ids, manager_id: employee.manager_id });
      setEmployee(emptyEmployee); setSelected(null); setNotice('Çalışan kaydedildi. Etkilenen hesabın yeniden giriş yapması gerekir.'); await load();
    } catch (cause) { setEmployee(previous => ({ ...previous, password: '' })); setError(messageOf(cause)); }
    finally { setBusy(false); }
  }
  async function saveRole(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const body = { name: roleName, permissions, ...(role ? { revision: role.revision } : {}) };
      if (role) await request(`/firm-admin/roles/${encodeURIComponent(role.id)}`, { method: 'PUT', body: JSON.stringify(body) });
      else await post('/firm-admin/roles', body);
      selectRole(null); setNotice('Rol kaydedildi. Bu role bağlı hesapların yeniden giriş yapması gerekir.'); await load();
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  }
  return <div className="page firm-administration"><header className="page-header"><div><p className="eyebrow">BÜRO YAPILANDIRMASI</p><h1>Çalışanlar ve roller</h1><p className="muted">Organizasyonu ve işlem izinlerini düzenleyin.</p></div><button className="button" onClick={() => { selectEmployee(null); selectRole(null); void load(); }} disabled={busy}>Yenile</button></header>
    <Notice>Organizasyon yöneticisi olmak müvekkil veya dosya erişimi vermez. İşlem izinleri için rol, içerik için açık atama gerekir. Müvekkil/dosya ekipleri ve insan görüşü iş akışı sonraki aşamalarda açılacak.</Notice>
    {error && <Notice error>{error}</Notice>}{notice && <Notice>{notice}</Notice>}
    {!data ? !error && <Loading label="Büro yapılandırması yükleniyor…" /> : <>
      <section className="panel"><h2>Çalışanlar</h2><div className="table-scroll"><table><thead><tr><th>Çalışan</th><th>Organizasyon yöneticisi</th><th>Durum</th><th>Roller</th><th>İşlem</th></tr></thead><tbody>{data.employees.map(item => <tr key={item.id}><td>{item.name}<br /><small>{item.username}</small></td><td>{data.employees.find(person => person.id === item.manager_id)?.name || 'Atanmamış'}</td><td>{item.active ? 'Aktif' : 'Devre dışı'}</td><td>{item.role_ids.map(id => data.roles.find(value => value.id === id)?.name || 'Bilinmeyen rol').join(', ') || 'İzin yok'}</td><td><button className="text-button" disabled={busy} onClick={() => selectEmployee(item)}>Düzenle: {item.name}</button></td></tr>)}</tbody></table></div></section>
      <section className="panel"><form onSubmit={saveEmployee}><h2>{selected ? `${selected.name} · düzenle` : 'Çalışan ekle'}</h2><div className="form-grid"><div className="field"><label htmlFor="employee-name">Ad soyad</label><input id="employee-name" value={employee.name} maxLength={100} required onChange={e => setEmployee({ ...employee, name: e.target.value })} /></div>
        {!selected && <><div className="field"><label htmlFor="employee-username">Kullanıcı adı</label><input id="employee-username" value={employee.username} autoComplete="off" maxLength={100} required onChange={e => setEmployee({ ...employee, username: e.target.value })} /></div><div className="field"><label htmlFor="employee-password">İlk parola (en az 16 karakter)</label><input id="employee-password" type="password" autoComplete="new-password" minLength={16} maxLength={200} value={employee.password} required onChange={e => setEmployee({ ...employee, password: e.target.value })} /></div><div className="field"><label htmlFor="employee-profession">Çalışma kimliği</label><select id="employee-profession" value={employee.professional_role} onChange={e => setEmployee({ ...employee, professional_role: e.target.value })}><option value="lawyer">Avukat</option><option value="curator">Küratör</option></select></div></>}
        <div className="field"><label htmlFor="employee-manager">Organizasyon yöneticisi</label><select id="employee-manager" value={employee.manager_id || ''} onChange={e => setEmployee({ ...employee, manager_id: e.target.value || null })}><option value="">Atanmamış</option>{data.employees.filter(item => item.active && item.id !== selected?.id).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><small>En fazla bir yönetici; bu ilişki dosya erişimi sağlamaz.</small></div></div>
        <fieldset><legend>İşlem rolleri</legend>{data.roles.map(item => <label className="check-option" key={item.id}><input type="checkbox" checked={employee.role_ids.includes(item.id)} onChange={e => setEmployee({ ...employee, role_ids: e.target.checked ? [...employee.role_ids, item.id] : employee.role_ids.filter(id => id !== item.id) })} />{item.name}</label>)}</fieldset>
        {selected && <><label className="check-option"><input type="checkbox" checked={employee.active} onChange={e => setEmployee({ ...employee, active: e.target.checked })} />Hesap aktif</label><details><summary>Mevcut etkin işlem izinleri</summary><ul>{selected.permissions.map(id => <li key={id}>{data.permissions.find(item => item.id === id)?.label || id}</li>)}</ul><p>Kaydedilen yeni roller bir sonraki girişte uygulanır. İçerik atamaları ayrıca gereklidir.</p></details></>}
        <div className="form-actions"><button className="button primary" disabled={busy}>{busy ? 'Kaydediliyor…' : selected ? 'Çalışanı kaydet' : 'Çalışan ekle'}</button>{selected && <button className="button" type="button" disabled={busy} onClick={() => selectEmployee(null)}>Yeni çalışan</button>}</div></form></section>
      <section className="panel"><h2>Rol kataloğu</h2><p className="muted">Başlangıç rolleri korunur. Farklı izinler için özel rol oluşturun. Roller dosya ataması değildir.</p><div className="form-actions">{data.roles.map(item => <button className="button" key={item.id} disabled={item.starter || busy} onClick={() => selectRole(item)}>{item.name}{item.starter ? ' · başlangıç' : ''}</button>)}</div><form onSubmit={saveRole}><h3>{role ? 'Özel rolü düzenle' : 'Özel rol oluştur'}</h3><div className="field"><label htmlFor="role-name">Rol adı</label><input id="role-name" value={roleName} maxLength={100} required onChange={e => setRoleName(e.target.value)} /></div><fieldset><legend>Desteklenen işlem izinleri</legend>{data.permissions.map(item => <label className="check-option" key={item.id}><input type="checkbox" checked={permissions.includes(item.id)} onChange={e => setPermissions(previous => e.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))} />{item.label}</label>)}</fieldset><p className="muted">Düzenleme, inceleme ve çıktı izinleri görüntüleme izni de gerektirir.</p><div className="form-actions"><button className="button primary" disabled={busy}>{role ? 'Rolü kaydet' : 'Rol oluştur'}</button>{role && <button type="button" className="button" disabled={busy} onClick={() => selectRole(null)}>Yeni rol</button>}</div></form></section>
      <section className="panel"><h2>Son yapılandırma değişiklikleri</h2><p className="muted">Son 100 kayıt · içerik ve parola bu listede yer almaz.</p><ol>{changes.map(item => <li key={item.id}>{new Date(item.recorded_at).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul' })} · {item.action} · {data.employees.find(person => person.id === item.actor_id)?.name || item.actor_id}</li>)}</ol></section>
    </>}
  </div>;
}
