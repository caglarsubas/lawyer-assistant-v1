import { Badge, Detail, JsonDetails } from '../../components';
import type { SourceCandidates } from '../../types';
import { locatorText } from '../../utils';

export function SourceCandidatesPanel({ candidates }: { candidates: SourceCandidates }) {
  return <section className="authority-candidates">
    <Detail title="Bağımsız kamu kaynak pasajları">
      <p className="small muted">Bu alıntılar kaynak incelemesi içindir. Hukuki etkisi, kesinleşme durumu ve olay tarihine uygunluğu ayrıca değerlendirilmelidir.</p>
      <p className="small muted">{candidates.hits.length} pasaj gösteriliyor. Ulusal hukuk derleminin tamlığı bilinmiyor.</p>
      {candidates.coverage.status === 'partial' && <p className="small muted">Tarama veya çıktı sınırına ulaşıldı; ilgili kaynakların tamamı incelenmiş sayılmaz.</p>}
      {candidates.coverage.status === 'unavailable' && <p className="small muted">Kaynak izni veya sürümü doğrulanamadı; kaynak pasajları gösterilmiyor.</p>}
      {candidates.hits.length ? <div className="authority-candidate-list">{candidates.hits.map((hit) => <article className="authority-candidate" key={`${hit.source_version_id}:${hit.passage_id}`}>
        <div className="section-heading compact"><h3>{locatorText(hit.locator)}</h3><Badge>Kaynak alıntısı</Badge></div>
        <blockquote>{hit.text}</blockquote>
        <Detail title="Alıntının kaynağı ve sürümü"><dl className="definition-grid">
          <div><dt>Pasaj kimliği</dt><dd className="reference-id">{hit.passage_id}</dd></div>
          <div><dt>Kaynak kimliği</dt><dd className="reference-id">{hit.document_id}</dd></div>
          <div><dt>Kaynak sürümü</dt><dd className="reference-id">{hit.source_version_id}</dd></div>
          <div><dt>Kaynak SHA-256</dt><dd className="reference-id">{hit.source_sha256}</dd></div>
          <div><dt>Alıntı SHA-256</dt><dd className="reference-id">{hit.quote_sha256}</dd></div>
          <div><dt>Alıntı aralığı</dt><dd>[{hit.start_offset}, {hit.end_offset}) · Unicode karakterleri</dd></div>
          <div><dt>Hukuki uygulanabilirlik</dt><dd>Değerlendirilmedi</dd></div>
          <div><dt>Kesinleşme</dt><dd>Bilinmiyor</dd></div>
        </dl></Detail>
      </article>)}</div> : <p className="small muted">Kaynak pasajı alınamadı. Bu sonuç, ilgili mevzuat veya emsal bulunmadığını göstermez.</p>}
      {candidates.limitations.length > 0 && <Detail title="Kaynak taramasının sınırları"><ul>{candidates.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></Detail>}
      <JsonDetails title="Kaynak taraması ve sürüm kaydı" value={{ coverage: candidates.coverage, snapshot: candidates.snapshot }} />
    </Detail>
  </section>;
}
