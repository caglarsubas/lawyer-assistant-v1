import { useState, type FormEvent } from 'react';
import { request } from '../api';
import { Notice } from '../components';
import { messageOf } from '../utils';
import type { Employee } from './FirmAdminPage';

interface Assignment { user_id: string; scope?: 'details' | 'all_cases'; supervisor?: boolean; responsible?: boolean }
interface Snapshot { target_id: string; revision: number; assignments?: Assignment[]; members?: Assignment[] }
export default function AccessAssignments({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const [kind, setKind] = useState('customers'); const [reference, setReference] = useState('');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null); const [items, setItems] = useState<Assignment[]>([]);
  const [selected, setSelected] = useState(''); const [scope, setScope] = useState<'details' | 'all_cases'>('details');
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const path = `/firm-admin/${kind}/${encodeURIComponent(reference.trim())}/${kind === 'customers' ? 'assignments' : 'team'}`;
  function reset() { setSnapshot(null); setItems([]); setSelected(''); setError(''); setNotice(''); }
  async function load(event: FormEvent) {
    event.preventDefault(); reset(); setBusy(true);
    try { const value = await request<Snapshot>(path); setSnapshot(value); setItems(value.assignments || value.members || []); }
    catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!snapshot) return; setBusy(true); setError(''); setNotice('');
    try {
      const value = await request<Snapshot>(path, { method: 'PUT', body: JSON.stringify({ revision: snapshot.revision, [kind === 'customers' ? 'assignments' : 'members']: items }) });
      setSnapshot(value); setItems(value.assignments || value.members || []); setNotice('Atamalar kaydedildi. Etkilenen hesapların yeniden giriş yapması gerekir.'); onSaved();
    } catch (cause) { reset(); setError(messageOf(cause)); } finally { setBusy(false); }
  }
  return <section className="panel"><h2>Müvekkil ve dosya atamaları</h2><p className="muted">Yetkili avukatın paylaştığı kayıt referansını kullanın. Yapılandırma yetkisi müvekkil adını veya dosya içeriğini açmaz.</p>
    <form onSubmit={load}><div className="form-grid"><div className="field"><label htmlFor="assignment-kind">Kayıt türü</label><select id="assignment-kind" value={kind} disabled={busy} onChange={e => { reset(); setKind(e.target.value); setReference(''); }}><option value="customers">Müvekkil</option><option value="workspaces">Dosya / çalışma alanı</option></select></div><div className="field"><label htmlFor="assignment-reference">Kayıt referansı</label><input id="assignment-reference" value={reference} maxLength={64} required disabled={busy} onChange={e => { reset(); setReference(e.target.value); }} /></div></div><button className="button" disabled={busy || !reference.trim()}>Atamaları yükle</button></form>
    {error && <Notice error>{error}</Notice>}{notice && <Notice>{notice}</Notice>}
    {snapshot && <form onSubmit={save}><p className="small muted">Referans: {snapshot.target_id} · atama sürümü {snapshot.revision}</p>
      <Notice>{kind === 'customers' ? 'Yalnızca ayrıntılar: müvekkil bilgileri açılır, dosya erişimi verilmez. Tüm bağlı dosyalar: mevcut ve gelecekte bağlanan dosyalar ile o dosyalardaki diğer müvekkil ayrıntıları da açılır. Dosya sayıları yalnızca erişilebilir dosyaları gösterir.' : 'Doğrudan dosya atamaları aşağıdadır. Müvekkil üzerinden verilen erişim ayrıca korunur. Birden fazla avukat gözetmen veya sorumlu olabilir. Organizasyon yöneticiliği bu görevi vermez.'}</Notice>
      <ul>{items.map(item => { const person = employees.find(p => p.id === item.user_id); return <li key={item.user_id}><strong>{person?.name || item.user_id}{person && !person.active ? ' · devre dışı' : ''}</strong> {kind === 'customers' ? <label> Erişim kapsamı <select aria-label={`${person?.name || item.user_id} erişim kapsamı`} disabled={busy} value={item.scope} onChange={e => setItems(old => old.map(value => value.user_id === item.user_id ? { ...value, scope: e.target.value as 'details' | 'all_cases' } : value))}><option value="details">Yalnızca ayrıntılar</option><option value="all_cases">Tüm mevcut ve gelecekteki bağlı dosyalar</option></select></label> : <>{(['supervisor', 'responsible'] as const).map(key => <label className="check-option" key={key}><input type="checkbox" disabled={busy || !person?.active || !['lawyer', 'admin'].includes(person.professional_role)} checked={Boolean(item[key])} onChange={e => setItems(old => old.map(value => value.user_id === item.user_id ? { ...value, [key]: e.target.checked } : value))} />{key === 'supervisor' ? 'Dosya gözetmeni' : 'Sorumlu avukat'}</label>)}</>} <button type="button" className="text-button" disabled={busy} onClick={() => setItems(old => old.filter(value => value.user_id !== item.user_id))}>Kaldır: {person?.name || item.user_id}</button></li>; })}</ul>
      <div className="field"><label htmlFor="assignment-employee">Atanacak çalışan</label><select id="assignment-employee" disabled={busy} value={selected} onChange={e => setSelected(e.target.value)}><option value="">Çalışan seçin</option>{employees.filter(person => person.active && !items.some(item => item.user_id === person.id)).map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></div>
      {kind === 'customers' && <div className="field"><label htmlFor="assignment-scope">Yeni atamanın kapsamı</label><select id="assignment-scope" disabled={busy} value={scope} onChange={e => setScope(e.target.value as 'details' | 'all_cases')}><option value="details">Yalnızca ayrıntılar</option><option value="all_cases">Tüm mevcut ve gelecekteki bağlı dosyalar</option></select></div>}
      <div className="form-actions"><button type="button" className="button" disabled={busy || !selected} onClick={() => { setItems(old => [...old, kind === 'customers' ? { user_id: selected, scope } : { user_id: selected, supervisor: false, responsible: false }]); setSelected(''); }}>Atama listesine ekle</button><button className="button primary" disabled={busy}>{busy ? 'Kaydediliyor…' : 'Kapsamları ve atamaları kaydet'}</button></div><p className="small muted">Kaydetmeden önce kapsamları kontrol edin. Müvekkil atamasının kaldırılması ayrı doğrudan dosya atamasını kaldırmaz. Dosya ekibinden kaldırılan kişi ayrı müvekkil izniyle erişmeye devam edebilir.</p>
    </form>}
  </section>;
}
