import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadAuthorityComparison, post, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, messageOf } from '../../utils';
import { FindingViewContent } from './AuthorityFindings';
import { comparisonAssessment, committedComparisonReceipt, DISPOSITIONS } from './authorityComparisonTypes';
import type { AuthorityComparisonInputs, AuthorityComparisonSnapshot, AuthorityComparisonView, EditableDisposition } from './authorityComparisonTypes';
import { FINDING_OUTCOMES } from './authorityFindingTypes';
import type { FindingSummary, FindingView } from './authorityFindingTypes';

type Props = { matterId: string; analysisId: string; contextId: string; reviewId: string; onUnavailable: (cause: unknown) => void };

export function ComparisonEvidence({ comparison: comp }: { comparison: AuthorityComparisonSnapshot }) {
  const original = comp.authority_review_snapshot;
  return <><p className="small">Özgün taslak v{comp.base_version} → gösterilen taslak v{comp.candidate_version}. Önceki inceleme korunur; karşılaştırma hukuki karar veya otomatik bulgu giderme değildir.</p>
    {comp.historical_context_changes.includes('research_record_changed') && <Notice>Özgün araştırma kaydı güncelliğini yitirdi. Bu karşılaştırma saklanan kaynak adaylarını kullanır; araştırma kapsamını veya uygulanabilirliğini yenilemez.</Notice>}
    <Detail title={`Önceki / yeni adım değişiklikleri · ${comp.changes.length}`}>
      {!comp.changes.length && <p>Adım metni veya yapısında değişiklik yok.</p>}
      {comp.changes.map(item => <section key={item.target_id}><h4>{item.target_id}</h4><p>Önceki</p><pre className="data-pre">{JSON.stringify(item.before, null, 2)}</pre><p>Yeni</p><pre className="data-pre">{JSON.stringify(item.after, null, 2)}</pre></section>)}
    </Detail>
    <Detail title="Önceki ve yeni özel belge alıntıları">{comp.private_sources.map(item => <section key={item.source_ref}><h4>{item.source_ref} · {item.name}</h4><p className="small">{item.locator} · [{item.start}, {item.end})</p><blockquote className="authority-quote">{item.text}</blockquote><p className="reference-id">{item.quote_sha256}</p></section>)}</Detail>
    <Detail title="Saklanan özgün kamu dayanakları ve avukat bulguları"><FindingViewContent value={{ ...original, id: comp.review_id, snapshot: original, review_sha256: comp.authority_review_sha256, public_source_access: true, is_latest_review: false, freshness: { status: 'stale', reasons: ['Özgün sürüm incelemesi; yeni taslağı onaylamaz.'] }, runtime_authorization: 'none' } as FindingView} /></Detail>
    <Detail title="Tam önceki / yeni adımlar ve sürüm bağları"><p className="reference-id">{comp.base_version_id} · {comp.base_content_sha256}</p><p className="reference-id">{comp.candidate_version_id} · {comp.candidate_content_sha256}</p><pre className="data-pre">{JSON.stringify({ before: comp.before_targets, after: comp.after_targets }, null, 2)}</pre></Detail>
  </>;
}

export function AuthorityComparisonContent({ value }: { value: AuthorityComparisonView }) {
  const data = value.public_source_access && value.snapshot ? value.snapshot : null;
  return <><p className="small">{value.sequence}. karşılaştırma · {value.reviewer_name} · {formatDate(value.recorded_at, true)}</p><Badge status={value.freshness.status}>{value.freshness.status === 'current' ? 'Karşılaştırma bağları güncel' : value.freshness.status === 'stale' ? 'Yeniden inceleme gerekli · Aktarım kapalı' : 'İçerik bekletiliyor'}</Badge>
    {!data ? <Notice error>Kaynak izinleri veya kayıt tamamlaması doğrulanamadı. Kamu alıntıları ve bunları içerebilen tüm karşılaştırma notları bekletiliyor.</Notice> : <>
      <p className="authored-text">{data.assessment.note}</p><p className="small">Beyan edilen etkin inceleme süresi: {data.assessment.review_seconds === null ? 'Ölçülmedi' : `${data.assessment.review_seconds} saniye`}. Model çağrısı, otomatik hukuki onay ve fayda puanı yok.</p>
      <Detail title="Her özgün bulgu için saklanan avukat beyanı">{data.assessment.dispositions.map(item => {
        const source = data.comparison_snapshot.authority_review_snapshot.assessment.sources[item.source_index]; const original = source.observations.find(obs => obs.dimension === item.dimension)!;
        return <section key={`${item.source_index}:${item.dimension}`}><h4>{item.source_index + 1}. kaynak · {data.comparison_snapshot.dimensions[item.dimension]}</h4><p>Özgün: {FINDING_OUTCOMES[original.outcome]}</p><p className="authored-text">{original.note}</p><p><strong>{DISPOSITIONS[item.outcome]}</strong></p><p className="authored-text">{item.note}</p><p className="small">Özgün adımlar: {source.target_ids.join(' · ')} · Yeni adımlar: {item.after_target_ids.join(' · ') || 'Bağlanmadı'} · Özel alıntılar: {item.private_source_refs.join(' · ') || 'Bağlanmadı'}</p></section>;
      })}</Detail><ComparisonEvidence comparison={data.comparison_snapshot} />
    </>}<Detail title="Karşılaştırma kaydı ve güncellik"><p className="reference-id">{value.id} · {value.comparison_sha256}</p><p className="small">{value.freshness.reasons.join(' · ') || 'Teknik bağlar güncel; hukuki doğruluk belirlenmez.'}</p></Detail>
  </>;
}

function ComparisonEditor({ inputs, base, onSaved, onUnavailable }: { inputs: AuthorityComparisonInputs; base: string; onSaved: (pending: boolean) => void; onUnavailable: (cause: unknown) => void }) {
  const comp = inputs.comparison;
  const [rows, setRows] = useState<EditableDisposition[]>(() => comp.authority_review_snapshot.assessment.sources.flatMap((source, index) => source.observations.map(item => ({ source_index: index, dimension: item.dimension, outcome: '', note: '', after_target_ids: [], private_source_refs: [] }))));
  const [note, setNote] = useState(''); const [seconds, setSeconds] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []); const nonce = useRef<{ body: string; id: string } | null>(null);
  const assessment = comparisonAssessment(inputs, rows, note, seconds);
  function update(index: number, change: Partial<EditableDisposition>) { setRows(old => old.map((item, i) => i === index ? { ...item, ...change } : item)); }
  async function save() {
    if (!assessment) return; setBusy(true); setError('');
    const spec = { ...assessment, candidate_version_id: comp.candidate_version_id, expected_basis_sha256: inputs.basis_sha256, expected_comparison_id: inputs.expected_comparison_id }; const key = JSON.stringify(spec); if (nonce.current?.body !== key) nonce.current = { body: key, id: crypto.randomUUID().replaceAll('-', '') };
    try { await post(base, { ...spec, request_id: nonce.current.id }); if (mounted.current) onSaved(false); }
    catch (cause) { if (mounted.current) { if (cause instanceof ApiError && committedComparisonReceipt(cause.data)) onSaved(true); else if (cause instanceof ApiError && cause.status !== 0) onUnavailable(cause); else setError(messageOf(cause)); } }
    finally { if (mounted.current) setBusy(false); }
  }
  return <form className="authority-context-form" onSubmit={event => { event.preventDefault(); void save(); }}><ComparisonEvidence comparison={comp} />
    {!inputs.can_record && <Notice error>Dayanaklar değişti veya çalışma alanı arşivlendi; yeni karşılaştırma kaydedilemez. {inputs.freshness.reasons.join(' · ')}</Notice>}
    <p className="small">Her özgün kaynak bulgusunu ayrı değerlendirin. Ele alındı beyanı değişen yeni adıma ve yeni özel alıntıya bağlanır; bu bağlantı hukuki giderme kanıtı değildir. Eksik ve çözümlenmeyen hususlar açık kalır.</p>
    <fieldset disabled={busy || !inputs.can_record}>{rows.map((item, index) => { const source = comp.authority_review_snapshot.assessment.sources[item.source_index]; const original = source.observations.find(obs => obs.dimension === item.dimension)!;
      return <fieldset key={`${item.source_index}:${item.dimension}`}><legend>{item.source_index + 1}. kaynak · {comp.dimensions[item.dimension]}</legend><p className="small">Özgün bulgu: {FINDING_OUTCOMES[original.outcome]} · {original.note}</p><p className="small">Özgün bağlı adımlar: {source.target_ids.join(' · ')}</p>
        <Field label="Bulgunun yeni taslaktaki durumu">{id => <select id={id} required value={item.outcome} onChange={event => update(index, { outcome: event.target.value as EditableDisposition['outcome'] })}><option value="">Durum seçin</option>{Object.entries(DISPOSITIONS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</Field>
        <Field label="Karşılaştırma gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={2000} value={item.note} onChange={event => update(index, { note: event.target.value })} />}</Field>
        <Detail title="Yeni adımlar ve özel alıntılarla ilişkilendir"><Field label="Yeni sürüm adımları (çoklu seçim)">{id => <select id={id} multiple size={4} value={item.after_target_ids} onChange={event => update(index, { after_target_ids: Array.from(event.target.selectedOptions, option => option.value) })}>{Object.keys(comp.after_targets).map(key => <option key={key} value={key}>{key}</option>)}</select>}</Field><Field label="Özel alıntılar (çoklu seçim)">{id => <select id={id} multiple size={3} value={item.private_source_refs} onChange={event => update(index, { private_source_refs: Array.from(event.target.selectedOptions, option => option.value) })}>{comp.private_sources.map(ref => <option key={ref.source_ref} value={ref.source_ref}>{ref.source_ref} · {ref.name}</option>)}</select>}</Field></Detail>
      </fieldset>;
    })}<Field label="Genel karşılaştırma notu">{id => <textarea id={id} required minLength={3} maxLength={2000} value={note} onChange={event => setNote(event.target.value)} />}</Field><Field label="Ölçüldüyse etkin inceleme süresi (saniye)">{id => <input id={id} type="number" min={1} max={28800} step={1} value={seconds} onChange={event => setSeconds(event.target.value)} placeholder="Ölçülmedi" />}</Field><button className="button" disabled={!assessment} type="submit">Bulgulara bağlı karşılaştırmayı kaydet</button></fieldset>{error && <Notice error>{error}</Notice>}
  </form>;
}

export default function AuthorityComparisons({ matterId, analysisId, contextId, reviewId, onUnavailable }: Props) {
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(analysisId)}/authority-contexts/${encodeURIComponent(contextId)}/reviews/${encodeURIComponent(reviewId)}/comparisons`;
  const [inputs, setInputs] = useState<AuthorityComparisonInputs | null>(null); const [items, setItems] = useState<FindingSummary[]>([]); const [view, setView] = useState<AuthorityComparisonView | null>(null); const [busy, setBusy] = useState(false); const [loaded, setLoaded] = useState(false); const [more, setMore] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  function failed(cause: unknown) { setInputs(null); setView(null); setItems([]); setError(messageOf(cause)); if (cause instanceof ApiError && cause.status !== 0) onUnavailable(cause); }
  async function load() { setInputs(null); setView(null); setBusy(true); setError(''); try { const value = await request<AuthorityComparisonInputs>(`${base}/context`, { cache: 'no-store' }); if (mounted.current) setInputs(value); } catch (cause) { if (mounted.current) failed(cause); } finally { if (mounted.current) setBusy(false); } }
  async function history(append = false) { setInputs(null); setView(null); setBusy(true); setError(''); try { const page = await request<FindingSummary[]>(`${base}?limit=10&offset=${append ? items.length : 0}`, { cache: 'no-store' }); if (mounted.current) { setItems(old => append ? [...old, ...page.filter(item => !old.some(value => value.id === item.id))] : page); setLoaded(true); setMore(page.length === 10); } } catch (cause) { if (mounted.current) failed(cause); } finally { if (mounted.current) setBusy(false); } }
  async function inspect(id: string) { setInputs(null); setView(null); setBusy(true); setError(''); try { const value = await request<AuthorityComparisonView>(`${base}/${encodeURIComponent(id)}`, { cache: 'no-store' }); if (mounted.current) { if (!value.public_source_access) onUnavailable(new Error('Karşılaştırma içeriği bekletiliyor. Özgün incelemeyi yeniden açın.')); else setView(value); } } catch (cause) { if (mounted.current) failed(cause); } finally { if (mounted.current) setBusy(false); } }
  async function download(format: 'json' | 'docx' | 'pdf') { if (!view) return; setBusy(true); try { await downloadAuthorityComparison(matterId, analysisId, contextId, reviewId, view.id, format); } catch (cause) { if (mounted.current) failed(cause); } finally { if (mounted.current) setBusy(false); } }
  return <><p className="small">Özel taslağı ayrı bir sürüm olarak düzenledikten sonra özgün bulgularla karşılaştırın. Yeni kaynaklar ve karşı içtihat araştırması otomatik tamamlanmaz.</p><div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void load()}>Yeni taslakla karşılaştırma girdilerini getir</button><button className="text-button" disabled={busy} onClick={() => void history()}>Karşılaştırma geçmişini getir</button></div>
    {notice && <Notice>{notice}</Notice>}{inputs && <ComparisonEditor key={inputs.basis_sha256} inputs={inputs} base={base} onUnavailable={failed} onSaved={pending => { setInputs(null); setNotice(pending ? 'Karşılaştırma kaydedildi; son izin kontrolü tamamlanamadı. İçerik bekletiliyor; yeni girdilerle ayrı kayıt gerekli.' : 'Karşılaştırma kaydedildi. Saklanan kaydı açarak güncel bağları kontrol edin.'); void history(); }} />}
    {items.map(item => <Detail key={item.id} title={`${item.sequence}. karşılaştırma · ${item.reviewer_name}`}><button className="text-button" disabled={busy} onClick={() => void inspect(item.id)}>Karşılaştırmayı aç / bağları kontrol et</button>{view?.id === item.id && <><AuthorityComparisonContent value={view} /><div className="practice-record-actions">{(['json', 'docx', 'pdf'] as const).map(format => <button key={format} className="text-button" disabled={busy || view.freshness.status !== 'current' || !view.public_source_access} onClick={() => void download(format)}>{format.toUpperCase()} karşılaştırmayı indir</button>)}</div></>}</Detail>)}
    {loaded && !items.length && <p>Bu incelemeye bağlı karşılaştırma yok.</p>}{more && <button className="text-button" disabled={busy} onClick={() => void history(true)}>Önceki karşılaştırmaları getir</button>}{error && <Notice error>{error}</Notice>}
  </>;
}
