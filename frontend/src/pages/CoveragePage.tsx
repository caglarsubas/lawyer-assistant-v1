import { useCallback, useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Detail, Icon, JsonDetails, Loading, Notice, PageHeader } from '../components';
import { messageOf, statusLabel } from '../utils';
import { fetchSourceCatalog, servingReleaseFromCoverage, ServingRelease, SourceCatalog, type SourceCatalogState } from './SourceReadiness';

const labels: Record<string, string> = {
  ontology: 'Ontoloji kapsamı', institutional: 'Kurumsal kapsam', corpus: 'Belge ve karar derlemi', assertion: 'İlişki incelemesi',
  assertions: 'İlişki incelemesi', structural: 'Yapısal kapsam', workflow: 'İş akışı doğrulaması', workflows: 'İş akışı doğrulaması',
  status: 'Durum', review_status: 'İnceleme durumu', legal_review_status: 'Hukuki inceleme', version: 'Sürüm',
  domains: 'Hukuk alanları', count: 'Sayı', source_count: 'Kaynak sayısı', document_count: 'Belge sayısı', decision_count: 'Karar sayısı',
  coverage: 'Kapsam', limitations: 'Sınırlılıklar', gaps: 'Eksikler', notes: 'Notlar', unknowns: 'Bilinmeyenler',
  history_start: 'Tarihsel başlangıç', reviewed: 'İncelenen', total: 'Toplam', source: 'Kaynak', sources: 'Kaynaklar',
  publication_status: 'Yayın durumu', coverage_status: 'Kapsam durumu', legal_review_required: 'Hukuki inceleme gerekli',
  populated: 'Veri eklenmiş', verified: 'Doğrulanmış', complete: 'Tamamlanmış', completeness: 'Tamlık',
  mode: 'Çalışma modu', classes: 'Sınıflar', relations: 'İlişkiler', reviewed_classes: 'İncelenen sınıflar',
  reviewed_relations: 'İncelenen ilişkiler', national_legal_review_complete: 'Ulusal hukuki inceleme tamamlandı',
  observed_count: 'Gözlenen kayıt sayısı', total_expected: 'Beklenen toplam', source_artifacts: 'Kaynak belgeler',
  historical_scope: 'Tarihsel kapsam', coverage_by_source_institution_domain_period: 'Kaynak, kurum, alan ve dönem kapsamı',
  legally_reviewed: 'Hukuki incelemeden geçen', eligible_for_legal_claims: 'Hukuki iddialarda kullanılabilir',
  start_year: 'Başlangıç yılı', predecessor_policy: 'Önceki düzenlemeler politikası',
};
export default function CoveragePage() {
  const [data, setData] = useState<unknown>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(true);
  const [sources, setSources] = useState<SourceCatalogState>({ status: 'loading' });
  const coverageRequest = useRef<AbortController | null>(null);
  const sourceRequest = useRef<AbortController | null>(null);
  const loadSources = useCallback(() => {
    sourceRequest.current?.abort(); const controller = new AbortController(); sourceRequest.current = controller;
    setSources({ status: 'loading' });
    void fetchSourceCatalog(controller.signal).then((result) => { if (!controller.signal.aborted) setSources(result); }).catch(() => { /* Superseded and unmounted requests stay silent. */ });
  }, []);
  const loadCoverage = useCallback(() => {
    coverageRequest.current?.abort(); const controller = new AbortController(); coverageRequest.current = controller;
    setLoading(true); setError(''); setData(null);
    request('/graphs/coverage', { signal: controller.signal }).then((result) => { if (!controller.signal.aborted) setData(result); }).catch((cause) => { if (!controller.signal.aborted) setError(messageOf(cause)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
  }, []);
  useEffect(() => { loadCoverage(); loadSources(); return () => { coverageRequest.current?.abort(); sourceRequest.current?.abort(); }; }, [loadCoverage, loadSources]);
  const sections = data && typeof data === 'object' && !Array.isArray(data) ? Object.entries(data).filter(([key]) => key !== 'serving_release') : [];
  return <>
    <PageHeader eyebrow="BİLDİKLERİMİZ VE SINIRLARI" title="Kapsamı bilerek çalışın." description="Bir hukuk alanının haritada bulunması, tüm kaynaklarının edinildiği veya iş akışının doğrulandığı anlamına gelmez." action={<button className="button secondary" onClick={() => { loadCoverage(); loadSources(); }} disabled={loading || sources.status === 'loading'}>Durumu yenile</button>} />
    <div className="coverage-intro"><Icon name="layers" size={26} /><p><strong>Beş ayrı değerlendirme.</strong> Yapısal harita, kaynak edinimi, tarihsel sürümler, ilişki incelemesi ve iş akışı doğrulaması ayrı izlenir. Bilinmeyen alanlar tamamlanmış kabul edilmez.</p></div>
    <a className="text-link coverage-jump" href="#public-source-catalog" onClick={(event) => { event.preventDefault(); const target = document.getElementById('public-source-catalog'); target?.focus({ preventScroll: true }); target?.scrollIntoView({ block: 'start' }); }}>Kaynak kabul kaydına git<Icon name="arrow" size={15} /></a>
    {error && <Notice error>{error}</Notice>}
    {loading ? <Loading label="Kapsam kaydı yükleniyor…" /> : <>
      <ServingRelease release={servingReleaseFromCoverage(data)} />
      <div className="coverage-register">{sections.map(([key, value], index) => <section key={key} className="coverage-section"><div className="coverage-section-title"><span className="matter-number">{String(index + 1).padStart(2, '0')}</span><h2>{labels[key] || key.replaceAll('_', ' ')}</h2></div><CoverageValue value={value} /></section>)}</div>
      {data !== null && <JsonDetails value={data} title="Kapsam kaydının tüm alanları" />}
    </>}
    <SourceCatalog state={sources} onRetry={loadSources} />
  </>;
}

function CoverageValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="muted">Bilinmiyor / belirtilmedi</span>;
  if (typeof value === 'boolean') return <span>{value ? 'Evet' : 'Hayır'}</span>;
  if (typeof value === 'string' || typeof value === 'number') return <p>{typeof value === 'string' ? statusLabel(value) : value}</p>;
  if (Array.isArray(value)) return value.length ? <ul className="coverage-values">{value.map((item, index) => <li key={index}><CoverageValue value={item} /></li>)}</ul> : <p className="muted">Kayıt bulunmuyor.</p>;
  return <dl className="coverage-fields">{Object.entries(value).map(([key, entry]) => <div key={key}><dt>{labels[key] || key.replaceAll('_', ' ')}</dt><dd>{entry !== null && typeof entry === 'object' ? <Detail title="Ayrıntıları göster"><CoverageValue value={entry} /></Detail> : <CoverageValue value={entry} />}</dd></div>)}</dl>;
}
