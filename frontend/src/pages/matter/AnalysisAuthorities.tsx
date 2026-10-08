import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadAuthorityContext, post, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { ValidityDetails } from '../../ValidityDetails';
import { formatDate, messageOf } from '../../utils';
import type { AnalysisRecord } from './analysisTypes';
import { AUTHORITY_ROLES, committedAuthorityReceipt, occurrence, occurrenceKey } from './authorityTypes';
import type { AuthorityCandidates, AuthorityContext, AuthorityManifest, AuthorityPreview, AuthorityRole, AuthoritySelection, AuthoritySource, AuthoritySpec, AuthoritySummary, LinkedAuthority } from './authorityTypes';

export function PublicAuthorityPassage({ source }: { source: AuthoritySource }) {
  const version = source.target_provision_version;
  return <><p className="small"><strong>{source.locator}</strong> · [{source.start_offset}, {source.end_offset}) · {source.graph_family === 'structure' ? 'Hukuk yapısı' : 'İçtihat'}</p>
    <p className="source-passage-text">{source.text}</p>
    <p className="small">İlişki dönemi: {formatDate(source.valid_from)} → {source.valid_to ? `${formatDate(source.valid_to)} (hariç)` : source.validity_end_status === 'open_ended' ? `${formatDate(source.validity_checked_through)} tarihine kadar incelendi` : 'Bitişi bilinmiyor'}</p>
    {version && <p className="small">Hedef hüküm sürümü: <span className="reference-id">{version.id}</span> · {version.resolution === 'resolved' ? 'Kimlik çözümlenmiş' : 'Kimlik belirsiz'} · {formatDate(version.validity.start)} → {version.validity.end ? `${formatDate(version.validity.end)} (hariç)` : version.validity.kind === 'open_ended' ? `${formatDate(version.validity.checked_through)} tarihine kadar incelendi` : 'Bitişi bilinmiyor'}</p>}
    <p className="small muted">Kaynakta beyan edilen ilişki: <span className="reference-id">{source.predicate.split('/').pop()}</span>. Atıf, uygulama veya bağlayıcılık beyanı olarak genişletilmez. Somut olaya uygulanabilirlik ve koşullar ayrıca incelenmelidir.</p>
    <ValidityDetails validity={source} />
    <Detail title="Tam kaynak kimliği ve doğrulama kaydı"><dl className="coverage-fields">
      {Object.entries({ 'İlişki kaydı': source.assertion_id, 'Pasaj': source.passage_id, 'Otorite': source.authority_id, 'Özne': source.subject_id, 'İlişki': source.predicate, 'Nesne': source.object_id, 'Özgün kaynak': source.document_id, 'Çıkarılmış metin sürümü': source.source_version_id, 'Hükmün mantıksal kimliği': version?.version_of ?? 'Belirlenmedi', 'Kaynak SHA-256': source.source_sha256, 'Metin SHA-256': source.text_sha256, 'Konum haritası SHA-256': source.locator_map_sha256, 'Alıntı SHA-256': source.quote_sha256, 'Yayın': source.release_id, 'Kaynak inceleme durumu': source.review_status, 'İnceleme zamanı': source.reviewed_at }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="reference-id">{value}</dd></div>)}
    </dl></Detail></>;
}

export function LinkedAuthorityView({ source }: { source: LinkedAuthority }) {
  const time = source.temporal_alignment;
  return <article className="authority-candidate"><p><strong>{AUTHORITY_ROLES[source.selection.relationship]}</strong> · Avukat bağlantı beyanı</p><p className="authored-text">{source.selection.note}</p>
    <p className="small">Araştırma tarihi {formatDate(time.research_as_of)} · Olay tarihi {time.analysis_event_date ? formatDate(time.analysis_event_date) : 'Belirtilmedi'}</p>
    {(time.dates_equal !== true || time.within_assertion_interval !== true || (source.evidence.target_provision_version && time.target_version_within_interval !== true)) && <Notice>Olay tarihi, araştırma tarihi veya kaynak dönemi farklı ya da belirsiz. Bu kayıt uygulanabilirlik belirlemez; tarih ve geçiş koşullarını inceleyin.</Notice>}
    <Detail title={`Bağlı analiz adımları (${source.selection.target_ids.length})`}>{Object.entries(source.target_snapshots).map(([id, value]) => <div key={id}><strong>{id}</strong><pre className="data-pre">{JSON.stringify(value, null, 2)}</pre></div>)}</Detail>
    <Detail title={`Özgün kamu pasajı · ${source.evidence.locator}`}><PublicAuthorityPassage source={source.evidence} /></Detail>
  </article>;
}

export function AuthorityManifestView({ manifest }: { manifest: AuthorityManifest }) {
  return <><p className="authored-text">{manifest.purpose}</p><p className="small muted">Bağlantılar avukatın araştırma beyanıdır. Hukuki onay, bağlayıcılık, semantik doğruluk ve karşı dayanak araştırmasının tamlığı belirlenmez. Taslak ve inceleme kararı değişmez; model çağrısı yapılmaz.</p>
    {manifest.sources.map((source) => <LinkedAuthorityView key={occurrenceKey(source.evidence)} source={source} />)}
    <Detail title="Sabit özel analiz ve sürüm bağları"><p className="reference-id">Analiz sürümü: {manifest.version_id} · Analiz SHA-256: {manifest.analysis_content_sha256} · Araştırma SHA-256: {manifest.product_sha256}</p><p className="reference-id">Yayın: {manifest.graph_release_pin.release_id} · Dağıtım: {manifest.graph_release_pin.serving_sha256} · Etkinleştirme sırası: {manifest.graph_release_pin.activation_sequence}</p><p className="reference-id">İnceleme kaydı: {manifest.analysis_review_id ?? 'Yok'}</p><pre className="data-pre">{JSON.stringify(manifest.analysis_content, null, 2)}</pre></Detail>
  </>;
}

export function AuthorityContextView({ value }: { value: AuthorityContext }) {
  const visible = value.public_source_access && value.manifest !== null;
  return <><Badge>{value.freshness.status === 'current' ? 'Kaynak bağları güncel · Hukuki onay yok' : value.freshness.status === 'stale' ? 'Güncelliğini yitirdi · Aktarım kapalı' : 'Kamu içeriği bekletiliyor'}</Badge>
    {!visible ? <Notice error>Kamu pasajları için güncel yayın izni veya kayıt tamamlaması doğrulanamadı. İçerik ve dışa aktarım bekletiliyor. Önceki kayıt korunur; yeni önizleme ile ayrı bağlam oluşturun.</Notice> : value.freshness.status === 'stale' && <Notice error>Özel analiz veya araştırma dayanağı değişti. Saklanan önceki içerik aşağıdadır; güncel kullanım ve dışa aktarım için yeni bağlam oluşturun.</Notice>}
    {visible && <AuthorityManifestView manifest={value.manifest!} />}
    <Detail title="Kayıt bilgileri"><p className="reference-id">{value.id} · {value.version_id}</p><p>{formatDate(value.registered_at, true)}</p><p className="reference-id">Bağlam SHA-256: {value.manifest_sha256}</p><p className="reference-id">{value.freshness.reasons.join(' · ') || 'Bağlarda değişiklik saptanmadı; hukuki değerlendirme değildir.'}</p></Detail>
  </>;
}

function ContextCard({ item, base, matterId, analysisId }: { item: AuthoritySummary; base: string; matterId: string; analysisId: string }) {
  const [view, setView] = useState<AuthorityContext | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function inspect() { setView(null); setError(''); setBusy(true); try { const value = await request<AuthorityContext>(`${base}/${encodeURIComponent(item.id)}`, { cache: 'no-store' }); if (mounted.current) setView(value); } catch (cause) { if (mounted.current) setError(messageOf(cause)); } finally { if (mounted.current) setBusy(false); } }
  async function download(format: 'json' | 'docx' | 'pdf') { setBusy(true); setError(''); try { await downloadAuthorityContext(matterId, analysisId, item.id, format); } catch (cause) { if (mounted.current) { setView(null); setError(messageOf(cause)); } } finally { if (mounted.current) setBusy(false); } }
  return <Detail title={item.title}><button className="text-button" disabled={busy} onClick={() => void inspect()}>{busy ? 'Kontrol ediliyor…' : 'Bağlamı aç / güncel izinleri kontrol et'}</button>{view && <><AuthorityContextView value={view} /><div className="practice-record-actions">{(['json', 'docx', 'pdf'] as const).map((format) => <button key={format} className="text-button" disabled={busy || !view.public_source_access || !view.manifest || view.freshness.status !== 'current'} onClick={() => void download(format)}>{format.toUpperCase()} bağlamı indir</button>)}</div></>}{error && <Notice error>{error}</Notice>}</Detail>;
}

type Editable = Omit<AuthoritySelection, 'relationship'> & { relationship: AuthorityRole | '' };
export function selectionPayload(items: Editable[]): AuthoritySelection[] | null {
  return items.length < 1 || items.length > 8 || new Set(items.map(occurrenceKey)).size !== items.length
    || items.some((item) => !item.relationship || !Object.hasOwn(AUTHORITY_ROLES, item.relationship) || item.note.trim().length < 3 || item.note.length > 2000 || !item.target_ids.length || item.target_ids.length > 12 || new Set(item.target_ids).size !== item.target_ids.length)
    ? null : items.map((item) => ({ ...occurrence(item), relationship: item.relationship as AuthorityRole, target_ids: [...item.target_ids], note: item.note }));
}

function ContextEditor({ candidates, productId, base, versionId, onSaved }: { candidates: AuthorityCandidates; productId: string; base: string; versionId: string; onSaved: (item: AuthoritySummary) => void }) {
  const [title, setTitle] = useState(''); const [purpose, setPurpose] = useState(''); const [selected, setSelected] = useState<Editable[]>([]);
  const [preview, setPreview] = useState<AuthorityPreview | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const nonce = useRef<{ sha: string; id: string } | null>(null); const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const links = selectionPayload(selected);
  const canPreview = candidates.current_version && candidates.private_freshness.status === 'current' && links !== null && title.trim().length >= 3 && purpose.trim().length >= 3;
  function edit(change: () => void) { change(); setPreview(null); nonce.current = null; setError(''); }
  async function inspect() { if (!canPreview || !links) return; setBusy(true); setError(''); setPreview(null); const spec: AuthoritySpec = { version_id: versionId, product_id: productId, title, purpose, selections: links }; try { const value = await post<AuthorityPreview>(`${base}/preview`, spec); if (mounted.current) setPreview(value); } catch (cause) { if (mounted.current) setError(messageOf(cause)); } finally { if (mounted.current) setBusy(false); } }
  async function freeze() { if (!preview) return; setBusy(true); setError(''); if (nonce.current?.sha !== preview.preview_sha256) nonce.current = { sha: preview.preview_sha256, id: crypto.randomUUID().replaceAll('-', '') };
    const body = { version_id: versionId, product_id: productId, title, purpose, selections: links, expected_preview_sha256: preview.preview_sha256, request_id: nonce.current.id };
    try { const value = await post<AuthorityContext>(base, body); if (mounted.current) onSaved(value); }
    catch (cause) { if (mounted.current) { const receipt = cause instanceof ApiError ? committedAuthorityReceipt(cause.data) : null; if (receipt) onSaved({ id: receipt, title, version_id: versionId }); else { setError(messageOf(cause)); if (cause instanceof ApiError && cause.status !== 0) setPreview(null); } } }
    finally { if (mounted.current) setBusy(false); }
  }
  return <form className="authority-context-form" onSubmit={(event) => { event.preventDefault(); void inspect(); }}>
    <p className="small">Araştırma tarihi {formatDate(candidates.research_as_of)} · Analiz olay tarihi {candidates.analysis_event_date ? formatDate(candidates.analysis_event_date) : 'Belirtilmedi'}. Kaynak ve inceleme bağları kayıt öncesinde yeniden doğrulanır.</p>
    {(!candidates.current_version || candidates.private_freshness.status !== 'current') && <Notice error>Güncel özel dayanaklı son analiz sürümü gerekli. Bu sürüm için yeni bağlam kaydedilemez.</Notice>}
    <fieldset disabled={busy}><legend>Kamu dayanak bağlamını hazırla</legend>
      <Field label="Bağlam başlığı">{(id) => <input id={id} value={title} minLength={3} maxLength={200} required onChange={(event) => edit(() => setTitle(event.target.value))} />}</Field>
      <Field label="Araştırma amacı">{(id) => <textarea id={id} value={purpose} minLength={3} maxLength={2000} required onChange={(event) => edit(() => setPurpose(event.target.value))} />}</Field>
      <p>En fazla 8 kaynak ilişkisi seçin. Her bağlantı için rol, gerekçe ve en az bir analiz adımını açıkça belirtin.</p>
      {!candidates.sources.length && <Notice>Bu araştırmada çözümlenmiş, izinli kaynak ilişkisi yok.</Notice>}
      {candidates.sources.map((source, index) => { const key = occurrenceKey(source); const item = selected.find((value) => occurrenceKey(value) === key); const update = (values: Partial<Editable>) => edit(() => setSelected((old) => old.map((value) => occurrenceKey(value) === key ? { ...value, ...values } : value)));
        return <article className="authority-candidate" key={key}><label className="authority-option"><input type="checkbox" checked={!!item} disabled={!item && selected.length >= 8} onChange={(event) => edit(() => setSelected((old) => event.target.checked ? [...old, { ...occurrence(source), target_ids: [], relationship: '', note: '' }] : old.filter((value) => occurrenceKey(value) !== key)))} />{index + 1}. kaynak ilişkisini seç · {source.locator}</label>
          <Detail title={`${index + 1}. kamu pasajını incele`}><PublicAuthorityPassage source={source} /></Detail>
          {item && <><Field label={`${index + 1}. kaynak bağlantısının rolü`}>{(id) => <select id={id} value={item.relationship} required onChange={(event) => update({ relationship: event.target.value as AuthorityRole | '' })}><option value="">Rol seçin</option>{Object.entries(AUTHORITY_ROLES).map(([role, label]) => <option key={role} value={role}>{label}</option>)}</select>}</Field>
            <Field label={`${index + 1}. kaynak bağlantısının gerekçesi`}>{(id) => <textarea id={id} value={item.note} minLength={3} maxLength={2000} required onChange={(event) => update({ note: event.target.value })} />}</Field>
            <fieldset className="authority-targets"><legend>{index + 1}. kaynak için analiz adımları · En fazla 12</legend>{Object.entries(candidates.targets).map(([id, target]) => <div key={id}><label className="authority-option"><input type="checkbox" checked={item.target_ids.includes(id)} disabled={!item.target_ids.includes(id) && item.target_ids.length >= 12} onChange={(event) => update({ target_ids: event.target.checked ? [...item.target_ids, id] : item.target_ids.filter((value) => value !== id) })} />{id}</label><Detail title={`${id} adımının mevcut içeriği`}><pre className="data-pre">{JSON.stringify(target, null, 2)}</pre></Detail></div>)}</fieldset>
          </>}
        </article>;
      })}
      <button className="button secondary" disabled={!canPreview} type="submit">Kaynak bağlamını önizle</button>
    </fieldset>
    {preview && <Detail title="Kayıt öncesi kaynak bağlamı" open><AuthorityManifestView manifest={preview.manifest} /><p className="reference-id">Önizleme SHA-256: {preview.preview_sha256}</p><button className="button" type="button" disabled={busy} onClick={() => void freeze()}>Önizlenen bağlamı değiştirilemez kaydet</button></Detail>}
    {error && <Notice error>{error}</Notice>}
  </form>;
}

export default function AnalysisAuthorities({ matterId, record }: { matterId: string; record: AnalysisRecord }) {
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(record.id)}/authority-contexts`;
  const [products, setProducts] = useState<{ id: string; title: string }[]>([]); const [product, setProduct] = useState(''); const [productMore, setProductMore] = useState(false);
  const [candidates, setCandidates] = useState<AuthorityCandidates | null>(null); const [items, setItems] = useState<AuthoritySummary[]>([]); const [more, setMore] = useState(false); const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function research(append = false) { setBusy(true); setError(''); setCandidates(null); try { const page = await request<{ id: string; title: string }[]>(`${base}/research-products?limit=10&offset=${append ? products.length : 0}`); if (mounted.current) { setProducts((old) => append ? [...old, ...page] : page); setProductMore(page.length === 10); } } catch (cause) { if (mounted.current) { setProducts([]); setError(messageOf(cause)); } } finally { if (mounted.current) setBusy(false); } }
  async function inspect() { if (!product) return; setBusy(true); setError(''); setCandidates(null); try { const params = new URLSearchParams({ version_id: record.latest_version_id, product_id: product }); const value = await request<AuthorityCandidates>(`${base}/candidates?${params}`, { cache: 'no-store' }); if (mounted.current) setCandidates(value); } catch (cause) { if (mounted.current) setError(messageOf(cause)); } finally { if (mounted.current) setBusy(false); } }
  async function history(append = false) { setBusy(true); setError(''); setCandidates(null); try { const page = await request<AuthoritySummary[]>(`${base}?limit=10&offset=${append ? items.length : 0}`); if (mounted.current) { setItems((old) => append ? [...old, ...page.filter((item) => !old.some((candidate) => candidate.id === item.id))] : page); setMore(page.length === 10); setLoaded(true); } } catch (cause) { if (mounted.current) { setItems([]); setError(messageOf(cause)); } } finally { if (mounted.current) setBusy(false); } }
  return <><p>İzinli kamu araştırmasından bir pasajı özel taslağın belirli adımlarına bağlayın. Başka çalışma alanlarına aktarılmaz; taslak hukuki onay kazanmaz.</p>
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void research()}>Araştırma kayıtlarını getir</button><button className="text-button" disabled={busy} onClick={() => void history()}>Saklanan dayanak bağlamlarını getir</button></div>
    {products.length > 0 && <><Field label="Kamu kaynakları içeren araştırma">{(id) => <select id={id} value={product} disabled={busy} onChange={(event) => { setProduct(event.target.value); setCandidates(null); setError(''); }}><option value="">Araştırma seçin</option>{products.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select>}</Field><button className="text-button" disabled={busy || !product} onClick={() => void inspect()}>İzinli kaynak adaylarını aç</button></>}
    {productMore && <button className="text-button" disabled={busy} onClick={() => void research(true)}>Önceki araştırmaları getir</button>}
    {candidates && <ContextEditor candidates={candidates} productId={product} versionId={record.latest_version_id} base={base} onSaved={(item) => { setCandidates(null); setItems((old) => [item, ...old.filter((value) => value.id !== item.id)]); setLoaded(true); }} />}
    {items.map((item) => <ContextCard key={item.id} item={item} base={base} matterId={matterId} analysisId={record.id} />)}
    {loaded && !items.length && <p>Bu analiz için saklanan dayanak bağlamı yok.</p>}{more && <button className="text-button" disabled={busy} onClick={() => void history(true)}>Önceki bağlamları getir</button>}{error && <Notice error>{error}</Notice>}
  </>;
}
