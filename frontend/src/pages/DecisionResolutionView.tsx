import { Detail } from '../components';
import type { DecisionResolution } from './decisionMapping';

const labels: Record<keyof DecisionResolution, string> = {
  start: 'Dayanak başlangıcı', end: 'Dayanak bitişi', occurrence_role: 'Anma rolü', proceeding_ref: 'Yargılama referansı',
  decision_ref: 'Karar referansı', institution_ref: 'Kurum referansı', target_ref: 'Atıf hedefi', target_version_ref: 'Hedef sürümü',
  event_role: 'Tarih rolü', event_date: 'Tarih', authority_treatment: 'Atfın kullanımı',
};
const values: Partial<Record<keyof DecisionResolution, Record<string, string>>> = {
  occurrence_role: { unknown: 'Bilinmiyor', own_decision: 'Belgenin kendi kararı', cited_authority: 'Atıf yapılan otorite', editorial: 'Editoryal bilgi' },
  event_role: { unknown: 'Bilinmiyor', decision: 'Karar tarihi', publication: 'Yayım tarihi' },
  authority_treatment: { unknown: 'Bilinmiyor', cites: 'Atıf yapıyor', quotes: 'Alıntılıyor', applies: 'Uyguluyor', distinguishes: 'Ayırt ediyor' },
};
export function DecisionResolutionView({ resolution }: { resolution: DecisionResolution }) {
  return <><dl className="coverage-fields decision-resolution">{Object.entries(resolution).map(([key, value]) =>
    <div key={key}><dt>{labels[key as keyof DecisionResolution] || key}</dt><dd>{value === null ? 'Bilinmiyor' : values[key as keyof DecisionResolution]?.[String(value)] ?? value}</dd></div>
  )}</dl><Detail title="Kaydedilen alan değerleri" variant="technical"><pre className="recorded-values">{JSON.stringify(resolution, null, 2)}</pre></Detail></>;
}
