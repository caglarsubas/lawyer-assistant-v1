import { Detail, Notice } from '../../components';
import type { AnalysisContextPreview } from './analysisTypes';

export function AnalysisContextBudget({ value }: { value: AnalysisContextPreview }) {
  const number = (value: number) => value.toLocaleString('tr-TR');
  return <section aria-label="Bağlam bütçesi önizlemesi">
    <p><strong>{value.fits ? 'İlk geçiş bağlama sığıyor' : 'Bağlam sınırı aşılıyor · İş başlatılmaz'}</strong></p>
    <p>{number(value.prompt.total_upper_bound_units)} / {number(value.context_limit_units)} muhasebe birimi · {value.fits ? `${number(value.remaining_units)} birim boşluk` : `${number(value.excess_units)} birim aşım`}</p>
    <p className="small muted">Tam serileştirilmiş ileti: {number(value.prompt.utf8_bytes)} UTF-8 bayt · Çerçeve payı: {number(value.framing_reserve_units)} · Çıktı payı: {number(value.prompt.completion_tokens)} token. Bu, muhafazakâr mühendislik hesabıdır; ölçülmüş tokenizer kullanımı veya çalışma garantisi değildir.</p>
    {value.prompt.response_contract_utf8_bytes !== undefined && <p className="small muted">Yanıt sözleşmesi: {number(value.prompt.response_contract_utf8_bytes)} UTF-8 bayt · Yukarıdaki toplam bütçeye dahildir.</p>}
    {!value.fits && <Notice error>Metin veya dayanak kesilmedi. Kaydedilmiş analiz ve önceki denemeler korunur. Gerekirse özgün kaynakları inceleyerek ayrı, odaklı bir taslak sürümü hazırlayın; kapsam eksiklerini açıkça kaydedin.</Notice>}
    {!value.configuration_ready && <Notice error>Yerel sağlayıcı yapılandırması hazır değil. Önizleme bağlantı, kimlik doğrulama veya model çağrısı yapmaz.</Notice>}
    <p className="small muted">Yalnız ilk geçiş hesaplandı.{value.max_passes > 1 && ' Olası düzeltme geçişi, değişen tam metin üzerinden çağrıdan önce yeniden ölçülür; sığacağı varsayılmaz.'} Önizleme iş başlatmaz, mevcut taslağı veya inceleme kararını değiştirmez; hukuki onay değildir.</p>
    {value.transport.uses_public_network && <p className="small muted">Onaylı dizüstü tüneli internet üzerinden yerel modele erişir; bu aktarım air-gapped değildir.</p>}
    <Detail title={`Tam sürüm ve dayanak bağları (${value.evidence.length})`}>
      <p className="reference-id">Kaynak analiz sürümü: {value.source_version_id} · Revizyon {value.source_revision}</p>
      <p className="reference-id">Model: {value.model} · İnceleme kaydı: {value.source_review_id || 'Yok'}</p>
      <p className="reference-id">İleti SHA-256: {value.prompt.messages_sha256}</p>
      {value.prompt.response_contract_sha256 && <p className="reference-id">Yanıt sözleşmesi SHA-256: {value.prompt.response_contract_sha256}</p>}
      <p className="reference-id">Önizleme SHA-256: {value.preview_sha256}</p>
      <ul>{value.evidence.map(item => <li key={item.evidence_id}><span className="reference-id">{item.evidence_id}</span> · Belge revizyonu {item.document_revision} · [{item.start}, {item.end})<p className="reference-id">Pasaj: {item.passage_sha256}<br />Alıntı: {item.quote_sha256}</p></li>)}</ul>
      <p className="small muted">Bu bağlar ve özetler özel çalışma alanı verisidir. Başlatırken sürüm, dayanaklar, inceleme, erişim ve sağlayıcı ayarları yeniden doğrulanır.</p>
    </Detail>
  </section>;
}
