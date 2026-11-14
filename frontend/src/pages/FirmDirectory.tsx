import { Badge, Detail, Empty } from '../components';
import type { Employee, FirmData, FirmRole } from './FirmAdminPage';

export function matchingEmployees(employees: Employee[], query: string) {
  const term = query.trim().toLocaleLowerCase('tr-TR');
  return employees.filter(person => `${person.name}\n${person.username}`.toLocaleLowerCase('tr-TR').includes(term));
}

export function EmployeeRegister({ data, query, selectedId, busy, onSelect }: {
  data: FirmData; query: string; selectedId?: string; busy: boolean; onSelect: (employee: Employee) => void;
}) {
  const visible = matchingEmployees(data.employees, query);
  return <><p className="small muted" role="status">{visible.length} / {data.employees.length} çalışan</p>
    {!visible.length ? <Empty title="Eşleşen çalışan yok.">Adın veya kullanıcı adının bir bölümünü yazın; tüm liste için aramayı temizleyin.</Empty> :
      <ul className="employee-register">{visible.map(person => <li key={person.id}>
        <div className="register-heading"><div><h3>{person.name}</h3><p className="small muted">{person.username}</p></div><Badge>{person.active ? 'Aktif' : 'Devre dışı'}</Badge></div>
        <dl className="register-fields"><div><dt>Organizasyon yöneticisi</dt><dd>{data.employees.find(item => item.id === person.manager_id)?.name || 'Atanmamış'}</dd></div><div><dt>İşlem rolleri</dt><dd>{person.role_ids.map(id => data.roles.find(role => role.id === id)?.name || 'Bilinmeyen rol').join(', ') || 'İzin yok'}</dd></div></dl>
        <button type="button" className="text-button" aria-pressed={selectedId === person.id} disabled={busy} onClick={() => onSelect(person)}>Düzenle: {person.name}</button>
      </li>)}</ul>}
  </>;
}

export function RoleRegister({ data, selectedId, busy, onSelect }: {
  data: FirmData; selectedId?: string; busy: boolean; onSelect: (role: FirmRole) => void;
}) {
  return <ul className="role-register">{data.roles.map(role => <li key={role.id}>
    <div className="register-heading"><h3>{role.name}</h3><Badge>{role.starter ? 'Başlangıç rolü · salt okunur' : 'Özel rol'}</Badge></div>
    <Detail title={`${role.name} · işlem izinleri`}><ul>{role.permissions.map(id => <li key={id}>{data.permissions.find(permission => permission.id === id)?.label || id}</li>)}</ul>{!role.permissions.length && <p>Bu role işlem izni tanımlanmamış.</p>}</Detail>
    {!role.starter && <button type="button" className="text-button" aria-pressed={selectedId === role.id} disabled={busy} onClick={() => onSelect(role)}>Düzenle: {role.name}</button>}
  </li>)}</ul>;
}
