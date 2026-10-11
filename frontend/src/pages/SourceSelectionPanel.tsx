import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../api';
import { Detail, Loading, Notice } from '../components';
import type { PublicSourceRecord } from '../types';
import { messageOf } from '../utils';
import { RELATIONSHIPS } from './SourceRelationshipPanel';
import { fetchSelection, SELECTION_STATUSES, type SelectionEvidence, type SelectionHandoff } from './sourceSelection';

export default function SourceSelectionPanel({ sources }: { sources: PublicSourceRecord[] }) {
  const [selected, setSelected] = useState<string[]>([]), [result, setResult] = useState<SelectionEvidence | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [denied, setDenied] = useState(false);
  const operation = useRef<AbortController | null>(null), urls = useRef(new Set<string>());
  function clear() { operation.current?.abort(); setResult(null); setBusy(false); urls.current.forEach(URL.revokeObjectURL); urls.current.clear(); }
  function select(id: string) { clear(); setError(''); setSelected(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]); }
  async function verify(download = false) {
    if (busy || denied) return;
    clear(); setBusy(true); setError(''); const controller = new AbortController(); operation.current = controller;
    const timeout = window.setTimeout(() => { controller.abort(); setResult(null); setBusy(false); setError('Seçim zamanında doğrulanamadı. Elle yeniden doğrulayın.'); }, 30000);
    try {
      const value = await fetchSelection(selected, controller.signal, download);
      if (controller.signal.aborted) return;
      setResult(value);
      if (download) {
        const dossier = { schema_version: 'source-selection-dossier-v1', evidence_json: value.evidence_json, evidence_sha256: value.evidence_sha256 };
        const url = URL.createObjectURL(new Blob([JSON.stringify(dossier)], { type: 'application/json' })); urls.current.add(url);
        const link = document.createElement('a'); link.href = url; link.download = `kuruma-ozel-kaynak-secimi-${value.evidence_sha256.slice(0, 16)}.json`; document.body.append(link); link.click(); link.remove();
        window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 1000);
      }
    } catch (cause) {
      if (!controller.signal.aborted) { setResult(null); setError(messageOf(cause)); if (cause instanceof ApiError && [401, 403].includes(cause.status)) { setSelected([]); setDenied(true); } }
    } finally { clearTimeout(timeout); if (!controller.signal.aborted) setBusy(false); }
  }
  useEffect(() => { const activeUrls = urls.current; return () => { operation.current?.abort(); activeUrls.forEach(URL.revokeObjectURL); activeUrls.clear(); }; }, []);
  return <section className="source-review-section" aria-labelledby="source-selection-title"><h2 id="source-selection-title">Çalışma öncesi kaynak seçimi</h2>
    <p>Referans veya çalışma örneklerini seçmeden önce iki ile altı paketin doğrudan insan görüşlerini birlikte inceleyin.</p>
    <Notice>Seçiminiz ve ilişki kayıtları kurumunuza özeldir. Aynı eserin farklı temsilleri bağımsız örnek olarak sayılmaz; bu ekran bağımsız örnek sayısını belirlemez veya çalışma onayı vermez.</Notice>
    {error && <Notice error>{error}</Notice>}
    {denied ? <Notice error>Erişim doğrulanamadı. Kaynak kabul sayfasını yeniden açın.</Notice> : <>
      <fieldset className="source-review-fieldset"><legend>Bu katalog sayfasından kaynak seçin · {selected.length}/6</legend>
        {sources.filter(source => /^[a-f0-9]{64}$/.test(source.id)).map(source => <label className="checkbox-label" key={source.id}>
          <input type="checkbox" checked={selected.includes(source.id)} disabled={selected.length >= 6 && !selected.includes(source.id)} onChange={() => select(source.id)} />
          <span>{source.title}<span className="small reference-id"> · {source.id.slice(0, 12)}</span></span>
        </label>)}
      </fieldset>
      <p className="small muted">Seçim yalnızca burada görünen paketlerden oluşur; katalog veya ülke çapında kapsam sonucu değildir. Seçimi değiştirmek eski sonucu temizler.</p>
      <div className="button-group"><button className="button secondary" disabled={selected.length < 2 || busy} onClick={() => void verify()}>{busy ? 'Doğrulanıyor…' : 'Seçili kaynak ilişkilerini doğrula'}</button>
        <button className="text-button" onClick={() => { clear(); setSelected([]); setError(''); }}>Seçimi temizle</button></div>
      {busy && <Loading label="Kaynaklar ve insan görüşleri doğrulanıyor…" />}
      {result && <><SelectionSummary value={result.receipt} /><Detail title="Anlık kayıt ve dışa aktarım"><p className="reference-id">SHA256: {result.evidence_sha256}</p>
        <p className="small muted">İndirme tüm paketleri ve incelemeleri tekrar denetler; yeni veya değişmiş sonuç dosyada ve ekranda görünür. İndirilmiş kayıt güncel yetki veya sonraki değişikliklerin kanıtı değildir.</p>
        <button className="button secondary" disabled={busy} onClick={() => void verify(true)}>Kuruma özel seçim dosyasını yeniden doğrula ve indir</button>
      </Detail></>}
    </>}
  </section>;
}

export function SelectionSummary({ value }: { value: SelectionHandoff }) {
  const title = (id: string) => value.sources.find(source => source.source_id === id)?.title || id;
  return <div><h3>Seçili kaynakların inceleme kapsamı</h3>
    <p>{value.coverage.selected_source_count} paket · {value.coverage.expected_pair_count} doğrudan çift · {value.coverage.pair_status_counts.resolved} güncel çözümlenmiş görüş</p>
    <p>Bağımsız özgün örnek sayısı: belirlenmedi. {value.coverage.all_pairs_current_resolved ? 'Her çift için güncel insan görüşü var; çalışma yeterliliği ayrıca değerlendirilir.' : 'İlişki kapsamı eksik; aşağıdaki görüşleri tamamlayın veya yenileyin.'}</p>
    {value.identity_conflicts.length > 0 && <Notice error>{value.identity_conflicts.length} kaynakta eser/sürüm beyanları tutarsız. İnsan incelemesinde uzlaştırılmalıdır.</Notice>}
    {value.identity_conflicts.map(conflict => <Detail key={conflict.source_id} title={`${title(conflict.source_id)}: çelişen beyanlar`}><ul>{conflict.declarations.map(item => <li key={item.pair_id}>{item.work_ref} · {item.version_ref}<span className="small reference-id"> · çift {item.pair_id.slice(0, 12)}</span></li>)}</ul></Detail>)}
    {value.source_review_gaps.length > 0 && <Detail title="Ayrı kaynak incelemelerinin açık kategorileri"><ul>{value.source_review_gaps.map(gap => <li key={gap.source_id}><a className="text-link" href={`#/sources/${gap.source_id}`}>{title(gap.source_id)}</a> · {gap.categories.map(category => ({ rights: 'Haklar', source_identity: 'Kimlik', extraction: 'Metin doğruluğu', legal: 'Hukuki sürüm' })[category] || category).join(', ')}</li>)}</ul></Detail>}
    <div className="source-selection-table"><table aria-label="Seçili kaynakların doğrudan ilişki görüşleri"><thead><tr><th>Doğrudan kaynak çifti</th><th>Güncel durum</th><th>Korunan geçmiş</th></tr></thead><tbody>{value.pairs.map(pair => <tr key={pair.pair_id}>
      <td>{pair.source_ids.map(id => <p key={id}>{title(id)}<span className="small reference-id"> · {id.slice(0, 12)}</span></p>)}<a className="text-link" href={`#/sources/${pair.source_ids[0]}/compare?other_source_id=${pair.source_ids[1]}`}>Çiftin karşılaştırma ve inceleme ekranını aç</a></td>
      <td>{SELECTION_STATUSES[pair.status]}{pair.latest && <><p>{RELATIONSHIPS[pair.latest.input.classification]}</p><p className="small">{pair.latest.input.rationale}</p><p className="small muted">{pair.latest.reviewer.name} · {pair.latest.created_at}</p></>}</td>
      <td>{pair.history_count} görüş · {pair.historical_classification_changes} sınıflandırma değişikliği<p className="small muted">Tam geçmiş çiftin dosyasında; eski görüşler silinmez.</p></td>
    </tr>)}</tbody></table></div>
  </div>;
}
