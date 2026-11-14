import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { EmployeeRegister, matchingEmployees, RoleRegister } from './FirmDirectory';
import type { FirmData } from './FirmAdminPage';

const person = { name: 'IŞIL İNCE', username: 'isil', professional_role: 'lawyer', active: true, manager_id: null, revision: 1, role_ids: ['reader'], permissions: [] };
const data: FirmData = { employees: [{ ...person, id: 'first' }, { ...person, id: 'second', active: false }], roles: [{ id: 'reader', name: 'Okuma', starter: true, permissions: ['view'], revision: 1 }], permissions: [{ id: 'view', label: 'Kayıtları görüntüle' }] };

describe('readable administration registers', () => {
  it('matches Turkish names and usernames without changing the source or excluding inactive accounts', () => {
    const before = structuredClone(data);
    expect(matchingEmployees(data.employees, ' ışıl ince ').map(item => item.id)).toEqual(['first', 'second']);
    expect(matchingEmployees(data.employees, 'isil')).toHaveLength(2);
    expect(matchingEmployees(data.employees, 'bulunmayan')).toEqual([]);
    expect(data).toEqual(before);
  });
  it('keeps identity-based selection for duplicate names and exposes inactive state', () => {
    const html = renderToStaticMarkup(<EmployeeRegister data={data} query="" selectedId="second" busy={false} onSelect={vi.fn()} />);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toContain('Devre dışı'); expect(html).toContain('2 / 2 çalışan');
    expect(html).toContain('Organizasyon yöneticisi'); expect(html).toContain('İşlem rolleri');
  });
  it('keeps starter roles inspectable without offering an editing action', () => {
    const html = renderToStaticMarkup(<RoleRegister data={data} busy={false} onSelect={vi.fn()} />);
    expect(html).toContain('Kayıtları görüntüle'); expect(html).toContain('salt okunur');
    expect(html).not.toContain('<button'); expect(html).not.toContain('<input');
  });
  it('escapes untrusted display text and disables custom-role editing during an operation', () => {
    const html = renderToStaticMarkup(<RoleRegister data={{ ...data, roles: [{ ...data.roles[0], name: '<script>test</script>', starter: false }] }} busy onSelect={vi.fn()} />);
    expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>'); expect(html).toContain('disabled=""');
  });
});
