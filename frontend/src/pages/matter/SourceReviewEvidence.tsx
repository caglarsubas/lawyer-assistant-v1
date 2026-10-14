import { Badge, Detail, Notice } from '../../components';
import { formatDate } from '../../utils';
import { AUTHORITY_ROLES } from './authorityTypes';
import { currentView, DIMENSION_LABELS, OUTCOMES, occurrenceKey, type ContextView, type Manifest, type Quote } from './sourceReviewTypes';

export function SourceQuote({ quote }: { quote: Quote }) {
  return <><p className="small"><strong>{quote.locator}</strong> · [{quote.start_offset}, {quote.end_offset}) · Unicode karakterleri</p>
    <p className="source-passage-text">{quote.text}</p>
    <Detail title="Özgün kaynak ve tam sürüm"><dl className="coverage-fields">{Object.entries({ 'Pasaj': quote.passage_id, 'Belge': quote.document_id,
      'Metin sürümü': quote.source_version_id, 'Alıntı SHA-256': quote.quote_sha256, 'Kaynak SHA-256': quote.source_sha256,
      'Metin SHA-256': quote.text_sha256, 'Konum haritası SHA-256': quote.locator_map_sha256, 'Yayın sürümü': quote.release_id }).map(([label, value]) =>
      <div key={label}><dt>{label}</dt><dd className="reference-id">{value}</dd></div>)}</dl></Detail></>;
}
export function SourceManifest({ manifest }: { manifest: Manifest }) {
  return <><h4>{manifest.title}</h4><p className="authored-text">{manifest.purpose}</p>
    <p className="small">Olay tarihi: {manifest.event_date ? formatDate(manifest.event_date) : 'Bilinmiyor'} · Araştırma tarihi: {manifest.research_snapshot.as_of ? formatDate(manifest.research_snapshot.as_of) : 'Belirtilmedi'}</p>
    <p className="small muted">Hukuki uygulanabilirlik değerlendirilmedi; kesinleşme bilinmiyor. Ulusal derlemin tamlığı bilinmiyor. Bağlantı, avukatın çalışma alanına özel yorumudur.</p>
    {manifest.sources.map(source => <section className="authority-candidate" key={occurrenceKey(source.evidence)}>
      <p><strong>Kaynak seçimini yapanın yorumu: {AUTHORITY_ROLES[source.selection.relationship]}</strong></p><p className="authored-text">{source.selection.note}</p>
      <SourceQuote quote={source.evidence} /><Detail title="Bağlanan analiz adımları">{Object.entries(source.target_snapshots).map(([id, target]) => <div key={id}><strong>{id}</strong><pre className="data-pre">{JSON.stringify(target, null, 2)}</pre></div>)}</Detail>
    </section>)}
    <Detail title="Araştırma sınırları ve kayıt bağları"><ul>{manifest.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
      <pre className="data-pre">{JSON.stringify(manifest.coverage, null, 2)}</pre><p className="reference-id">Analiz sürümü: {manifest.version_id}</p>
      <p className="reference-id">Sürüm yazarı: {manifest.analysis_author_id} · İlk analiz sahibi: {manifest.analysis_owner_id}</p>
      <p className="reference-id">Analiz özeti: {manifest.analysis_content_sha256} · Araştırma özeti: {manifest.product_sha256}</p>
    </Detail></>;
}
export function SourceContextView({ value }: { value: ContextView }) {
  if (!currentView(value)) return <Notice error>Kaynak veya özel dayanaklar güncel değil ya da izin doğrulanamadı. Alıntılar, notlar ve dışa aktarım bekletiliyor. Önceki kayıt korunur; yeni inceleme gerekli.</Notice>;
  const event = value.review.snapshot;
  return <><Badge>Kaynak bağları güncel · Hukuki onay verilmedi</Badge><SourceManifest manifest={value.manifest!} />
    <p className="small reference-id">Kaynak seçimini yapan: {value.recorded_by || 'Kayıt kimliği belirtilmedi'}</p>
    {!event ? <Notice>Bağımsız inceleme henüz kaydedilmedi.</Notice> : <section>
      <h4>Bağımsız incelemecinin kararı</h4><p><strong>{value.review.effective_state === 'reviewed_conditional' ? 'Koşullu inceleme tamamlandı' : 'Değişiklik istendi'}</strong> · Avukat beyanı</p>
      {!value.review.is_latest && <Notice>Önceki inceleme kararı. Güncel kararın yerine geçmez; bu kayıt üzerinden dışa aktarım açılmaz.</Notice>}
      <p className="small">{formatDate(event.recorded_at, true)} · <span className="reference-id">İncelemeci: {event.recorded_by}</span></p><p className="authored-text">{event.input.note}</p>
      {event.input.sources.map(source => <Detail key={occurrenceKey(source)} title={`İncelemecinin yorumu · ${AUTHORITY_ROLES[source.relationship]}`}><p className="authored-text">{source.note}</p>
        <p className="small">Analiz adımları: {source.target_ids.join(' · ')}</p>{source.observations.map(item => <section key={item.dimension}><h4>{DIMENSION_LABELS[item.dimension]}</h4><p><strong>{OUTCOMES[item.outcome]}</strong></p><p className="authored-text">{item.note}</p></section>)}
      </Detail>)}<Detail title="Değiştirilemez karar kaydı"><p className="reference-id">{value.review.id} · {event.packet_sha256}</p><p className="reference-id">Önceki karar: {event.previous_review_id || 'Yok'}</p></Detail>
    </section>}</>;
}
