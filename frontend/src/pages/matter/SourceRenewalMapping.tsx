import { Detail, Field, Notice } from '../../components';
import { DISPOSITIONS, type Disposition, type EditableMapping, type RenewalComparison, type RenewalMetadata } from './sourceRenewalTypes';
import type { Selection } from './sourceReviewTypes';

export function SourceRenewalMapping({ meta, rows, reason, added, selections, change }: {
  meta: RenewalMetadata; rows: EditableMapping[]; reason: string; added: string[]; selections: Selection[];
  change: (rows: EditableMapping[], reason: string, added: string[]) => void;
}) {
  return <section><h4>Önceki kaynak seçimini açıkça yenile</h4>
    <Notice>Önceki alıntılar ve notlar burada açılmaz. Önceki kaynak izinleri veya inceleme kararı yeni kayda aktarılmaz; yeni bağımsız inceleme gerekir.</Notice>
    <p className="small reference-id">Önceki bağlam: {meta.id} · Analiz sürümü: {meta.version_id} · Seçimi yapan: {meta.recorded_by}</p>
    <Field label="Kaynak bağlamını yenileme gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={2000} value={reason} onChange={event => change(rows, event.target.value, added)} />}</Field>
    {rows.map((row, index) => {
      const before = meta.sources.find(item => item.identity.passage_id === row.parent_passage_id)!;
      function update(value: Partial<EditableMapping>) { change(rows.map((item, i) => i === index ? { ...item, ...value } : item), reason, added); }
      return <section className="authority-candidate" key={row.parent_passage_id}>
        <h4>{index + 1}. önceki pasajın yeni seçimle ilişkisi</h4>
        <Detail title="Önceki kimlik ve adım özetleri · Alıntı içermez"><pre className="data-pre">{JSON.stringify(before, null, 2)}</pre></Detail>
        <Field label={`${index + 1}. önceki pasaj için yenileme beyanı`}>{id => <select id={id} value={row.disposition} required onChange={event => update({ disposition: event.target.value as Disposition | '' })}><option value="">Beyan seçin</option>{Object.entries(DISPOSITIONS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select>}</Field>
        <Field label={`${index + 1}. önceki pasaj için eşleme gerekçesi`}>{id => <textarea id={id} required minLength={3} maxLength={1000} value={row.note} onChange={event => update({ note: event.target.value })} />}</Field>
        <fieldset><legend>{index + 1}. önceki pasajın açıkça bağlandığı yeni seçimler</legend>{selections.map((source, i) => <label className="authority-option" key={source.passage_id}>
          <input type="checkbox" checked={row.new_passage_ids.includes(source.passage_id)} onChange={event => update({ new_passage_ids: event.target.checked ? [...row.new_passage_ids, source.passage_id] : row.new_passage_ids.filter(id => id !== source.passage_id) })} />{i + 1}. seçilen pasaj
        </label>)}</fieldset>
      </section>;
    })}
    <fieldset><legend>Önceki pasajlarla eşlenmeyen, açıkça eklenen seçimler</legend>{selections.map((source, i) => <label className="authority-option" key={source.passage_id}>
      <input type="checkbox" checked={added.includes(source.passage_id)} onChange={event => change(rows, reason, event.target.checked ? [...added, source.passage_id] : added.filter(id => id !== source.passage_id))} />{i + 1}. seçilen pasajı ayrı ekleme olarak belirt
    </label>)}</fieldset>
  </section>;
}

export function SourceRenewalComparison({ value, reason }: { value: RenewalComparison; reason: string }) {
  return <section><h4>Kaynak bağlamı sürüm karşılaştırması</h4><p className="authored-text">{reason}</p>
    <p>Önceki kayıt ve kararlar korunur. Bu kayıt için yeni bağımsız inceleme gerekir; hukuki eşdeğerlik değerlendirilmedi.</p>
    <p className="small">Analiz içeriği: {value.analysis_changed ? 'Değişti' : 'Aynı özet'} · Araştırma: {value.research_changed ? 'Değişti' : 'Aynı özet'} · Kaynak yayını: {value.release_changed ? 'Değişti' : 'Aynı tam yayın'}</p>
    {value.entries.map((entry, index) => <Detail key={entry.parent_identity.passage_id} title={`${index + 1}. önceki pasaj · ${DISPOSITIONS[entry.disposition]}`}>
      <p className="authored-text">{entry.note}</p>
      {entry.successors.map(source => <p key={source.identity.passage_id}>Tam kaynak kimliği: {source.exact_evidence_same ? 'Aynı' : 'Farklı'} · Tam analiz adımları: {source.exact_targets_same ? 'Aynı' : 'Farklı'}</p>)}
      <pre className="data-pre">{JSON.stringify(entry, null, 2)}</pre>
    </Detail>)}
    <Detail title="Değiştirilemez geçmiş bağı · Önceki alıntı ve notlar bekletilir"><p className="reference-id">{value.parent_context_id} · {value.parent_manifest_sha256}</p>
      <p className="reference-id">Önceki analiz sürümü: {value.parent_version_id} · İnceleme: {value.parent_review_id || 'Yok'}</p>
      <p>Ayrı eklenen pasaj sayısı: {value.added_passage_ids.length}</p><p>Önceki kaynak ve izin bağımlılıkları özgün kayıtta kalır; bu işlem onları yeniden yetkilendirmez.</p>
    </Detail>
  </section>;
}
