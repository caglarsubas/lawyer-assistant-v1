import { Detail, JsonDetails } from '../../components';
import type { EvidenceContextPack, Passage } from '../../types';
import { locatorText } from '../../utils';

const reasons: Record<string, string> = {
  empty_text: 'Boş metin',
  question_exceeds_context: 'Soru, model bağlam sınırını aşıyor',
  passage_limit: 'Pasaj sayısı sınırı',
  text_budget: 'Toplam metin sınırı',
  prompt_budget: 'Model bağlam sınırı',
  no_complete_token: 'Sınır içinde tam bir metin parçası seçilemedi',
  scan_budget: 'Tarama sınırı nedeniyle incelenmedi',
};

export function EvidenceContextPanel({ pack, evidence, onSource }: {
  pack: EvidenceContextPack; evidence: Passage[]; onSource: (id: string) => void;
}) {
  const { inventory } = pack;
  const used = pack.provider_use === 'validated_quote_response';
  return <section aria-label="Hazırlanan belge bağlamı">
    <p className="small muted">{inventory.selected_passages} / {inventory.input_passages} pasaj seçildi
      {' · '}{inventory.shortened_passages} kısaltıldı{' · '}{inventory.omitted_passages} dışarıda kaldı.</p>
    <Detail title="Belge bağlamını ve seçim sınırlarını incele">
      <p>{used ? 'Model yanıtı, aşağıdaki seçilmiş belge metinleriyle karşılaştırıldı.'
        : pack.provider_use === 'prepared_only' ? 'Yalnızca bağlam hazırlandı; model kullanımı doğrulanmadı.'
          : 'Bu seçim hazırlık için kaydedildi. Model çağrısı yapılmadı.'}</p>
      <p className="small muted">Seçim, tam dosya incelemesi veya hukuki uygulanabilirlik kanıtı değildir.
        Kamu kaynak adayları ayrı gösterilir; bu model bağlamına alınmadı.</p>
      {inventory.unexamined_passages > 0 && <p className="error-text">{inventory.unexamined_passages} pasaj,
        tarama sınırı nedeniyle sıralama için incelenmedi.</p>}
      <div className="authority-candidate-list">{pack.selected.map((item) => {
        const passage = evidence.find((candidate) => candidate.id === item.passage_id);
        return <article className="authority-candidate" key={item.passage_id}>
          <h4>{item.document_name || 'Belge pasajı'}</h4>
          {passage && <p className="passage-label">{locatorText(passage.locator)}</p>}
          <p className="small muted">Özgün pasajdaki karakter aralığı: [{item.excerpt_start}, {item.excerpt_end})
            {' / '}{item.full_passage_length}. Sayım Unicode karakterleriyledir.</p>
          {item.boundary !== 'full_passage' && <p className="small">
            {item.boundary === 'token_fragment' ? 'Cümle veya satır parçası seçildi. ' : 'Pasajın bir bölümü seçildi. '}
            Koşul, istisna ve diğer bağlam için özgün pasajı inceleyin.</p>}
          {passage ? <blockquote>{passage.text}</blockquote>
            : <p className="error-text">Kaydedilmiş alıntı metni bulunamadı; özgün kaynağı kontrol edin.</p>}
          <button className="text-button" onClick={() => onSource(item.passage_id)}>Özgün pasajı aç</button>
        </article>;
      })}</div>
      {Object.keys(pack.omission_counts).length > 0 && <>
        <h4>Dışarıda kalan pasajlar</h4>
        <ul>{Object.entries(pack.omission_counts).map(([reason, count]) =>
          <li key={reason}>{reasons[reason] || 'Diğer seçim sınırı'}: {count}</li>)}</ul>
      </>}
      <JsonDetails title="Seçim ve mesaj doğrulama kaydı" value={pack} />
    </Detail>
  </section>;
}
