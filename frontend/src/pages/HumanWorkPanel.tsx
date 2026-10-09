import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { request } from '../api';
import { Badge, Detail, Empty, Field, Loading, Notice } from '../components';
import { messageOf } from '../utils';
import { KIND_LABELS, WORK_STATUS, latestSubmission, workTime, type WorkDraft, type WorkItem, type WorkList, type WorkPerson, type WorkResponse } from './workflowTypes';

const blank: WorkDraft = { kind: 'task', title: '', description: '', due_local: '', assignee_ids: [] };
export default function HumanWorkPanel({ matterId, initialWorkId }: { matterId: string; initialWorkId?: string | null }) {
  const base = `/workspaces/${encodeURIComponent(matterId)}/work`;
  const [list, setList] = useState<WorkList | null>(null);
  const [selected, setSelected] = useState<WorkItem | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<WorkDraft>(blank);
  const load = useCallback(async (signal?: AbortSignal) => {
    const value = await request<WorkList>(base, { signal });
    if (!signal?.aborted) setList(value);
  }, [base]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).catch(cause => { if (!controller.signal.aborted) { setList(null); setSelected(null); setError(messageOf(cause)); } });
    if (initialWorkId) request<WorkItem>(`${base}/${encodeURIComponent(initialWorkId)}`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setSelected(value); }).catch(cause => { if (!controller.signal.aborted) { setSelected(null); setError(messageOf(cause)); } });
    return () => controller.abort();
  }, [base, initialWorkId, load]);
  async function open(id: string) {
    setBusy(true); setError(''); setSelected(null);
    try { setSelected(await request<WorkItem>(`${base}/${encodeURIComponent(id)}`)); } catch (cause) { setList(null); setError(messageOf(cause)); } finally { setBusy(false); }
  }
  async function mutate(path: string, body: unknown, method = 'POST') {
    setBusy(true); setError('');
    try { const value = await request<WorkItem>(path, { method, body: JSON.stringify(body) }); setSelected(value); await load(); return true; }
    catch (cause) { setSelected(null); setList(null); setError(messageOf(cause)); return false; }
    finally { setBusy(false); }
  }
  async function create(event: FormEvent) {
    event.preventDefault(); if (await mutate(base, draft)) setDraft(blank);
  }
  return <section className="human-work"><div className="section-heading"><h2>İş ve görüş takibi</h2><button className="text-button" disabled={busy} onClick={() => { setSelected(null); setError(''); void load().catch(cause => { setList(null); setError(messageOf(cause)); }); }}>Yenile</button></div>
    <p className="muted">Tarihler elle, İstanbul saatine göre kaydedilir. Bu kayıtlar hukuki süre hesabı veya hukuki doğruluk onayı değildir.</p>
    {error && <Notice error>{error}</Notice>}
    {list?.can_manage && <Detail title="Yeni görev, tarih veya görüş isteği"><form onSubmit={create}><WorkFields draft={draft} onChange={setDraft} people={list.people} busy={busy} /><button className="button primary" disabled={busy || !draft.assignee_ids.length}>{busy ? 'Kaydediliyor…' : 'İş kaydını aç'}</button><p className="small muted">Yalnızca dosyaya zaten erişimi ve işlem izni olan çalışanlar atanabilir. Bu form erişim yetkisi vermez.</p></form></Detail>}
    {!list && !error ? <Loading /> : list && !list.items.length ? <Empty title="Henüz iş kaydı yok.">Dosya gözetmeni görev ve görüş isteklerini buradan açar.</Empty> : list && <div className="work-register">{list.items.map(item => <article key={item.id}><div><span className="small-label">{KIND_LABELS[item.kind]}</span><h3>{item.title}</h3><p className="small">{workTime(item.due_at)} · İstanbul{item.overdue ? ' · tarihi geçti' : ''}</p><Badge>{WORK_STATUS[item.status]}</Badge></div><button className="button secondary" disabled={busy} onClick={() => void open(item.id)}>Çalışmayı aç</button></article>)}</div>}
    {selected && <WorkDetail key={`${selected.id}:${selected.revision}`} item={selected} people={list?.people || []} busy={busy} mutate={(suffix, body, method) => mutate(`${base}/${encodeURIComponent(selected.id)}${suffix}`, body, method)} />}
  </section>;
}

function WorkFields({ draft, onChange, people, busy, fixedKind = false }: { draft: WorkDraft; onChange: (d: WorkDraft) => void; people: WorkPerson[]; busy: boolean; fixedKind?: boolean }) {
  return <><div className="form-grid"><Field label="Kayıt türü">{id => <select id={id} value={draft.kind} disabled={busy || fixedKind} onChange={e => onChange({ ...draft, kind: e.target.value as WorkDraft['kind'], assignee_ids: [] })}>{Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field><Field label="Tarih ve saat · Europe/Istanbul">{id => <input id={id} type="datetime-local" required disabled={busy} value={draft.due_local} onChange={e => onChange({ ...draft, due_local: e.target.value })} />}</Field></div><Field label="Başlık">{id => <input id={id} maxLength={200} required disabled={busy} value={draft.title} onChange={e => onChange({ ...draft, title: e.target.value })} />}</Field><Field label={draft.kind === 'opinion' ? 'Gözetmen sorusu ve dosya bağlamı' : 'Açıklama'}>{id => <textarea id={id} rows={4} maxLength={20000} required={draft.kind === 'opinion'} disabled={busy} value={draft.description} onChange={e => onChange({ ...draft, description: e.target.value })} />}</Field><fieldset disabled={busy}><legend>Sorumlu / alıcı çalışanlar</legend>{people.filter(p => draft.kind !== 'opinion' || p.can_opine).map(person => <label key={person.id} className="check-option"><input type="checkbox" checked={draft.assignee_ids.includes(person.id)} onChange={e => onChange({ ...draft, assignee_ids: e.target.checked ? [...draft.assignee_ids, person.id] : draft.assignee_ids.filter(id => id !== person.id) })} />{person.name}</label>)}</fieldset></>;
}

function WorkDetail({ item, people, busy, mutate }: { item: WorkItem; people: WorkPerson[]; busy: boolean; mutate: (suffix: string, body: unknown, method?: string) => Promise<boolean> }) {
  const [draft, setDraft] = useState<WorkDraft>({ kind: item.kind, title: item.title, description: item.description || '', due_local: item.due_local, assignee_ids: item.assignee_ids });
  const [reason, setReason] = useState(''); const [status, setStatus] = useState(item.status);
  useEffect(() => { setDraft({ kind: item.kind, title: item.title, description: item.description || '', due_local: item.due_local, assignee_ids: item.assignee_ids }); setStatus(item.status); }, [item]);
  const own = item.responses.find(r => r.user_id === item.viewer_id && r.active);
  async function edit(e: FormEvent) { e.preventDefault(); await mutate('', { ...draft, revision: item.revision, status, reason }, 'PUT'); }
  return <article className="work-detail"><header><p className="eyebrow">{KIND_LABELS[item.kind]} · İSTEK SÜRÜMÜ {item.request_version}</p><h3>{item.title}</h3><p className="small">{workTime(item.due_at)} · İstanbul · {WORK_STATUS[item.status]}</p></header><p className="preserve-lines">{item.description}</p>
    {item.can_manage && <Detail title="İsteği, tarihi ve alıcıları düzenle"><form onSubmit={edit}><WorkFields draft={draft} onChange={value => setDraft({ ...value, kind: item.kind })} people={people} busy={busy} fixedKind /><p className="small muted">Gönderilmiş görüşler eski soru sürümüne bağlı kalır. Soruyu, tarihi veya alıcıları değiştirmek yeniden çalışma gerektirir. Önceki alıcılar ve kayıtlar geçmişte korunur. Çıkarılan alıcıların oturumu kapanır.</p><Field label="Kayıt durumu">{id => <select id={id} value={status} disabled={busy} onChange={e => setStatus(e.target.value)}><option value="open">Açık</option><option value="completed">Tamamlandı</option><option value="cancelled">İptal edildi</option></select>}</Field><Field label="Değişiklik gerekçesi">{id => <textarea id={id} required rows={2} maxLength={2000} disabled={busy} value={reason} onChange={e => setReason(e.target.value)} />}</Field><button className="button secondary" disabled={busy}>Değişikliği kaydet</button></form></Detail>}
    {own && item.status === 'open' && item.can_act && own.currently_eligible && <RecipientForm key={`${own.id}:${own.revision}`} item={item} own={own} busy={busy} mutate={mutate} />}
    {item.responses.map(response => <ResponseHistory key={`${response.id}:${response.revision}`} item={item} response={response} busy={busy} mutate={mutate} />)}
    <Detail title="İstek ve atama geçmişi">{item.history?.map(event => <div key={event.id} className="work-history"><p className="small">{event.actor_name} · {workTime(event.recorded_at)} · {event.action === 'created' ? 'Oluşturuldu' : 'Düzenlendi'}</p>{event.reason && <p>{event.reason}</p>}{event.snapshot && <div><strong>{event.snapshot.title}</strong><p className="preserve-lines">{event.snapshot.description}</p><p className="small">{event.snapshot.due_local.replace('T', ' ')} · İstanbul · {event.snapshot.assignee_ids.length} tarihsel alıcı</p></div>}</div>)}</Detail>
  </article>;
}

function RecipientForm({ item, own, busy, mutate }: { item: WorkItem; own: WorkResponse; busy: boolean; mutate: (s: string, b: unknown) => Promise<boolean> }) {
  const [text, setText] = useState(''); const [progress, setProgress] = useState('in_progress');
  const opinion = item.kind === 'opinion';
  if (opinion && ['submitted', 'accepted'].includes(own.status)) return <Notice>{WORK_STATUS[own.status]}. Yeni gönderim için gözetmenin değişiklik isteği veya yeni soru sürümü gerekir.</Notice>;
  async function submit(e: FormEvent) { e.preventDefault(); if (await mutate(opinion ? '/submissions' : '/progress', { revision: own.revision, ...(opinion ? { text } : { status: progress, note: text }) })) setText(''); }
  return <form className="work-action" onSubmit={submit}><h4>{opinion ? 'Yazılı görüşüm' : 'Çalışma durumum'}</h4>{opinion && <p className="small muted">Görüş kendi hesabınız ve metninizle kaydedilir. Bu form model çalıştırmaz veya sizin adınıza onay vermez.</p>}{!opinion && <Field label="İlerleme">{id => <select id={id} disabled={busy} value={progress} onChange={e => setProgress(e.target.value)}>{['pending', 'in_progress', 'completed'].map(value => <option key={value} value={value}>{WORK_STATUS[value]}</option>)}</select>}</Field>}<Field label={opinion ? 'Görüş metni' : 'İlerleme notu'}>{id => <textarea id={id} required maxLength={opinion ? 50000 : 4000} rows={opinion ? 8 : 3} disabled={busy} value={text} onChange={e => setText(e.target.value)} />}</Field><button className="button primary" disabled={busy || !text.trim()}>{opinion ? 'Görüşümü incelemeye gönder' : 'İlerlemeyi kaydet'}</button></form>;
}

function ResponseHistory({ item, response, busy, mutate }: { item: WorkItem; response: WorkResponse; busy: boolean; mutate: (s: string, b: unknown) => Promise<boolean> }) {
  const [note, setNote] = useState(''); const [decision, setDecision] = useState('revision_requested');
  const latest = latestSubmission(response);
  async function review(e: FormEvent) { e.preventDefault(); if (latest) await mutate(`/responses/${encodeURIComponent(response.user_id)}/review`, { revision: response.revision, submission_id: latest.id, decision, note }); }
  return <section className="work-response"><h4>{response.recipient_name} · {WORK_STATUS[response.status]}</h4>{(!response.active || !response.currently_eligible) && <Notice>{!response.active ? 'Bu alıcı artık istekte etkin değil. Geçmiş kayıtları korunuyor.' : 'Alıcının güncel dosya erişimi/işlem izni yok. Atama geçmişi erişim yetkisi vermez.'}</Notice>}
    {response.history?.map(event => <div key={event.id} className="work-history"><p className="small muted">{event.actor_name} · {workTime(event.recorded_at)} · {event.action === 'submitted' ? 'Görüş gönderimi' : event.action === 'reviewed' ? WORK_STATUS[event.decision || ''] : WORK_STATUS[event.status || '']} · istek sürümü {event.request_version}</p>{event.text && <p className="preserve-lines">{event.text}</p>}{event.note && <p className="preserve-lines">{event.note}</p>}</div>)}
    {item.kind === 'opinion' && item.can_review && response.user_id !== item.viewer_id && response.active && response.currently_eligible && response.status === 'submitted' && item.status === 'open' && latest && <form onSubmit={review}><Field label="İnceleme kararı">{id => <select id={id} value={decision} disabled={busy} onChange={e => setDecision(e.target.value)}><option value="revision_requested">Değişiklik iste</option><option value="accepted">Görüşü kabul et</option></select>}</Field><Field label="İnceleme gerekçesi">{id => <textarea id={id} required rows={3} maxLength={4000} disabled={busy} value={note} onChange={e => setNote(e.target.value)} />}</Field><button className="button secondary" disabled={busy || !note.trim()}>İncelemeyi kaydet</button><p className="small muted">Kabul bu insan görüşünün inceleme kaydıdır; kaynak, model veya hukuki doğruluk onayı değildir.</p></form>}
  </section>;
}
