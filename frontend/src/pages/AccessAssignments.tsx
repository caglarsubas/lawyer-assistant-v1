import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, request } from '../api';
import { Notice } from '../components';
import { messageOf } from '../utils';
import { AdminRevisionConflict, isAdminAccessDenied, isAdminRevisionConflict } from './AdminRevisionConflict';
import type { Employee } from './FirmAdminPage';

type AssignmentKind = 'customers' | 'workspaces';
export interface Assignment { user_id: string; scope?: 'details' | 'all_cases'; supervisor?: boolean; responsible?: boolean }
interface Snapshot { target_id: string; revision: number; assignments?: Assignment[]; members?: Assignment[] }

export async function requestAssignments(kind: AssignmentKind, target: string, options: RequestInit) {
  const field = kind === 'customers' ? 'assignments' : 'members';
  const suffix = kind === 'customers' ? 'assignments' : 'team';
  const value = await request<Snapshot>(`/firm-admin/${kind}/${encodeURIComponent(target)}/${suffix}`, options);
  if (value?.target_id !== target || !Number.isSafeInteger(value.revision) || value.revision < 1 || !Array.isArray(value[field])) {
    throw new Error('Atama kaydı seçili hedefle eşleşmiyor.');
  }
  return { ...value, items: value[field] };
}
type AssignmentSnapshot = Awaited<ReturnType<typeof requestAssignments>>;

export default function AccessAssignments({ employees, onSaved, onAccessDenied }: {
  employees: Employee[];
  onSaved: () => void;
  onAccessDenied: (cause: unknown) => void;
}) {
  const [kind, setKind] = useState<AssignmentKind>('customers');
  const [reference, setReference] = useState('');
  const [snapshot, setSnapshot] = useState<AssignmentSnapshot | null>(null);
  const [items, setItems] = useState<Assignment[]>([]);
  const [selected, setSelected] = useState('');
  const [scope, setScope] = useState<'details' | 'all_cases'>('details');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [checked, setChecked] = useState(false);
  const [current, setCurrent] = useState<AssignmentSnapshot | null>(null);
  const operation = useRef<AbortController | null>(null);
  const dirty = Boolean(snapshot && JSON.stringify(snapshot.items) !== JSON.stringify(items));
  const lockTarget = dirty || conflict;

  useEffect(() => () => operation.current?.abort(), []);

  function restart(value: AssignmentSnapshot | null) {
    setSnapshot(value);
    setItems(value?.items ?? []);
    setSelected('');
    setConflict(false);
    setChecked(false);
    setCurrent(null);
    setError('');
    setNotice('');
  }

  function failed(cause: unknown, reading: boolean) {
    if (isAdminAccessDenied(cause)) {
      onAccessDenied(cause);
      return;
    }
    if (cause instanceof ApiError && cause.status === 404 && (reading || cause.message === 'Atama hedefi bulunamadı')) {
      restart(null);
    }
    setError(messageOf(cause));
  }

  async function load() {
    if (operation.current || !reference.trim()) return;
    const target = snapshot?.target_id ?? reference.trim();
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setError('');
    setNotice('');
    setCurrent(null);
    setChecked(false);
    try {
      const value = await requestAssignments(kind, target, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (snapshot && (conflict || dirty)) {
        if (value.revision > snapshot.revision) {
          setConflict(true);
          setCurrent(value);
        } else if (value.revision !== snapshot.revision) {
          setConflict(true);
        }
        setChecked(true);
      } else restart(value);
    } catch (cause) {
      if (!controller.signal.aborted) failed(cause, true);
    } finally {
      operation.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (operation.current || !snapshot || conflict) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const field = kind === 'customers' ? 'assignments' : 'members';
      const value = await requestAssignments(kind, snapshot.target_id, {
        method: 'PUT', signal: controller.signal,
        body: JSON.stringify({ revision: snapshot.revision, [field]: items }),
      });
      if (controller.signal.aborted) return;
      restart(value);
      setNotice('Atamalar kaydedildi. Etkilenen hesapların yeniden giriş yapması gerekir.');
      onSaved();
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (isAdminRevisionConflict(cause, kind)) {
        setConflict(true);
        setCurrent(null);
        setChecked(false);
      } else failed(cause, false);
    } finally {
      operation.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  const draftDisabled = busy || conflict;
  const available = employees.filter(person => person.active && !items.some(item => item.user_id === person.id));
  return <section className="admin-section" id="firm-assignments" tabIndex={-1} aria-label="İçerik atamaları">
    <h2>Müvekkil ve dosya atamaları</h2>
    <p className="muted">Yetkili avukatın paylaştığı kayıt referansını kullanın. Yapılandırma yetkisi müvekkil adını veya dosya içeriğini açmaz.</p>
    <form onSubmit={event => { event.preventDefault(); void load(); }}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="assignment-kind">Kayıt türü</label>
          <select id="assignment-kind" value={kind} disabled={busy || lockTarget} onChange={event => {
            restart(null);
            setKind(event.target.value as AssignmentKind);
            setReference('');
          }}>
            <option value="customers">Müvekkil</option>
            <option value="workspaces">Dosya / çalışma alanı</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="assignment-reference">Kayıt referansı</label>
          <input id="assignment-reference" value={reference} maxLength={64} required disabled={busy || lockTarget} onChange={event => {
            restart(null);
            setReference(event.target.value);
          }} />
        </div>
      </div>
      <div className="form-actions">
        {!conflict && <button className="button" disabled={busy || !reference.trim()}>{snapshot ? 'Kaydedilen atamaları kontrol et' : 'Atamaları yükle'}</button>}
        {lockTarget && <button className="button secondary" type="button" disabled={busy} onClick={() => {
          restart(null);
          setReference('');
        }}>Taslağı bırak ve başka kayıt aç</button>}
      </div>
    </form>
    {error && <Notice error>{error}</Notice>}
    {notice && <Notice>{notice}</Notice>}
    {snapshot && <form onSubmit={save}>
      {conflict && <AdminRevisionConflict draftRevision={snapshot.revision} currentRevision={current?.revision} checked={checked}
        busy={busy} onRefresh={() => void load()} onRestart={() => { if (current) restart(current); }}>
        {current && (current.items.length ? <SavedAssignments items={current.items} employees={employees} kind={kind} />
          : <p className="small muted">Bu sürümde kayıtlı atama yok.</p>)}
      </AdminRevisionConflict>}
      <p className="assignment-draft-note">{conflict ? 'Kaydedilmemiş atama taslağı' : 'Bu listedeki değişiklikler, “Kapsamları ve atamaları kaydet” düğmesine basılana kadar taslaktır.'}</p>
      <p className="small muted">Referans: {snapshot.target_id} · atama sürümü {snapshot.revision}</p>
      <Notice>{kind === 'customers'
        ? 'Yalnızca ayrıntılar: müvekkil bilgileri açılır, dosya erişimi verilmez. Tüm bağlı dosyalar: mevcut ve gelecekte bağlanan dosyalar ile o dosyalardaki diğer müvekkil ayrıntıları da açılır. Dosya sayıları yalnızca erişilebilir dosyaları gösterir.'
        : 'Doğrudan dosya atamaları aşağıdadır. Müvekkil üzerinden verilen erişim ayrıca korunur. Birden fazla avukat gözetmen veya sorumlu olabilir. Organizasyon yöneticiliği bu görevi vermez.'}</Notice>
      <AssignedAccounts items={items} employees={employees} kind={kind} busy={draftDisabled} onChange={setItems} />
      <div className="field">
        <label htmlFor="assignment-employee">Atanacak çalışan</label>
        <select id="assignment-employee" disabled={draftDisabled} value={selected} onChange={event => setSelected(event.target.value)}>
          <option value="">Çalışan seçin</option>
          {available.map(person => <option key={person.id} value={person.id}>{person.name} · {person.username}</option>)}
        </select>
      </div>
      {kind === 'customers' && <div className="field">
        <label htmlFor="assignment-scope">Yeni atamanın kapsamı</label>
        <select id="assignment-scope" disabled={draftDisabled} value={scope} onChange={event => setScope(event.target.value as 'details' | 'all_cases')}>
          <option value="details">Yalnızca ayrıntılar</option>
          <option value="all_cases">Tüm mevcut ve gelecekteki bağlı dosyalar</option>
        </select>
      </div>}
      <div className="form-actions">
        <button type="button" className="button" disabled={draftDisabled || !available.some(person => person.id === selected)} onClick={() => {
          const assignment = kind === 'customers' ? { user_id: selected, scope } : { user_id: selected, supervisor: false, responsible: false };
          setItems(previous => [...previous, assignment]);
          setSelected('');
        }}>Atama listesine ekle</button>
        <button className="button primary" disabled={draftDisabled}>{busy ? 'İşlem sürüyor…' : 'Kapsamları ve atamaları kaydet'}</button>
      </div>
      <p className="small muted">Kaydetmeden önce kapsamları kontrol edin. Müvekkil atamasının kaldırılması ayrı doğrudan dosya atamasını kaldırmaz. Dosya ekibinden kaldırılan kişi ayrı müvekkil izniyle erişmeye devam edebilir.</p>
    </form>}
  </section>;
}

function SavedAssignments({ items, employees, kind }: { items: Assignment[]; employees: Employee[]; kind: AssignmentKind }) {
  return <ul className="assignment-register">{items.map(item => {
    const person = employees.find(employee => employee.id === item.user_id);
    const duties = [item.supervisor && 'Dosya gözetmeni', item.responsible && 'Sorumlu avukat'].filter(Boolean);
    return <li key={item.user_id}>
      <strong>{person ? `${person.name} · ${person.username}` : item.user_id}</strong>
      <span>{kind === 'customers'
        ? item.scope === 'all_cases' ? 'Tüm mevcut ve gelecekteki bağlı dosyalar' : 'Yalnızca ayrıntılar'
        : duties.join(' · ') || 'Dosya üyesi'}</span>
    </li>;
  })}</ul>;
}

export function AssignedAccounts({ items, employees, kind, busy, onChange }: { items: Assignment[]; employees: Employee[]; kind: string; busy: boolean; onChange: (items: Assignment[]) => void }) {
  return <ul className="assignment-register">{items.map(item => { const person = employees.find(p => p.id === item.user_id); return <li key={item.user_id}><div><strong>{person?.name || 'Hesap adı alınamadı'}</strong><p className="small muted">{person?.username || item.user_id}{person && !person.active ? ' · devre dışı' : ''}</p></div> {kind === 'customers' ? <label> Erişim kapsamı <select aria-label={`${person ? `${person.name} (${person.username})` : item.user_id} erişim kapsamı`} disabled={busy} value={item.scope} onChange={e => onChange(items.map(value => value.user_id === item.user_id ? { ...value, scope: e.target.value as 'details' | 'all_cases' } : value))}><option value="details">Yalnızca ayrıntılar</option><option value="all_cases">Tüm mevcut ve gelecekteki bağlı dosyalar</option></select></label> : <>{(['supervisor', 'responsible'] as const).map(key => <label className="check-option" key={key}><input type="checkbox" disabled={busy || !person?.active || !['lawyer', 'admin'].includes(person.professional_role)} checked={Boolean(item[key])} onChange={e => onChange(items.map(value => value.user_id === item.user_id ? { ...value, [key]: e.target.checked } : value))} />{key === 'supervisor' ? 'Dosya gözetmeni' : 'Sorumlu avukat'}</label>)}</>} <button type="button" className="text-button" disabled={busy} onClick={() => onChange(items.filter(value => value.user_id !== item.user_id))}>Listeden kaldır: {person ? `${person.name} (${person.username})` : item.user_id}</button></li>; })}</ul>;
}
