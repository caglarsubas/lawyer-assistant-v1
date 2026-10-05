import { ApiError, request } from '../api';
import { Badge, Detail, Loading, Notice } from '../components';
import type { GraphServingRelease, PublicSourceCatalog, PublicSourceRecord } from '../types';
import { DOMAIN_LABELS, formatDate, messageOf, statusLabel } from '../utils';

export type SourceCatalogState =
  | { status: 'loading' }
  | { status: 'restricted' }
  | { status: 'failed'; message: string }
  | { status: 'loaded'; catalog: PublicSourceCatalog };

export async function fetchSourceCatalog(signal?: AbortSignal): Promise<SourceCatalogState> {
  try {
    return { status: 'loaded', catalog: await request<PublicSourceCatalog>('/public-sources', { signal }) };
  } catch (cause) {
    if (signal?.aborted) throw cause;
    if (cause instanceof ApiError && cause.status === 403) return { status: 'restricted' };
    return { status: 'failed', message: messageOf(cause) };
  }
}

export function servingReleaseFromCoverage(data: unknown): GraphServingRelease | null {
  if (!data || typeof data !== 'object' || !('serving_release' in data)) return null;
  const value = data.serving_release;
  if (!value || typeof value !== 'object' || !('status' in value)) return null;
  if (!['unconfigured', 'verified', 'unavailable'].includes(String(value.status))) return null;
  return {
    status: value.status as GraphServingRelease['status'],
    ...('release_id' in value && typeof value.release_id === 'string' ? { release_id: value.release_id } : {}),
    ...('ontology_sha256' in value && typeof value.ontology_sha256 === 'string' ? { ontology_sha256: value.ontology_sha256 } : {}),
    ...('legal_review_verified' in value && typeof value.legal_review_verified === 'boolean' ? { legal_review_verified: value.legal_review_verified } : {}),
    ...('reason' in value && typeof value.reason === 'string' ? { reason: value.reason } : {}),
  };
}

export function ServingRelease({ release }: { release: GraphServingRelease | null }) {
  const verified = release?.status === 'verified';
  const title = !release ? 'Sürüm durumu bilinmiyor' : verified ? 'Sürüm bütünlüğü doğrulandı' : release.status === 'unconfigured' ? 'Etkin sürüm tanımlanmadı' : 'Sürüm doğrulanamadı';
  return <section className="coverage-section" aria-labelledby="serving-release-title">
    <div className="coverage-section-title"><h2 id="serving-release-title">Etkin graf sürümü</h2></div>
    <div><Badge status={verified ? 'ready' : 'unreviewed'}>{title}</Badge>
      <p className="small source-summary">{verified ? 'Graf hizmetinin değiştirilemez sürüm kaydı doğrulandı. Kaynak kapsamı ve hukuki inceleme ayrı değerlendirilir.' : !release ? 'Etkin sürüme ilişkin kayıt alınamadı. Kapsam verisini yenileyerek yeniden deneyin.' : release.status === 'unconfigured' ? 'Graf hizmeti için doğrulanacak bir sürüm seçilmemiş. Kaynak hazırlık kayıtları etkin bir hukuk derlemi oluşturmaz.' : 'Graf hizmetinin seçili sürümü doğrulanamadı. Bu durumdan kapsam veya hukuki yeterlilik sonucu çıkarılamaz.'}</p>
      <Detail title="Sürüm kaydı ve inceleme sınırı"><dl className="coverage-fields">
        <div><dt>Sürüm kimliği</dt><dd className="reference-id">{release?.release_id || 'Belirtilmedi'}</dd></div>
        <div><dt>Ontoloji içerik özeti</dt><dd className="reference-id">{release?.ontology_sha256 || 'Belirtilmedi'}</dd></div>
        <div><dt>Hukuki inceleme kaydı</dt><dd>{release?.legal_review_verified === true ? 'Doğrulandı' : release?.legal_review_verified === false ? 'Doğrulanmadı' : 'Belirtilmedi'}</dd></div>
        {release?.reason && <div><dt>Denetim açıklaması</dt><dd>{release.reason}</dd></div>}
      </dl><p className="small muted">Sürüm bütünlüğü veya inceleme kaydı; tüm kaynakların edinildiğini, belirli bir dosyaya uygulanabilirliği veya hukuki sonuçların doğruluğunu garanti etmez.</p></Detail>
    </div>
  </section>;
}

export function SourceCatalog({ state, onRetry }: { state: SourceCatalogState; onRetry: () => void }) {
  return <section id="public-source-catalog" tabIndex={-1} className="coverage-section" aria-labelledby="public-source-title">
    <div className="coverage-section-title"><h2 id="public-source-title">Kaynak kabul kaydı</h2></div>
    <div>
      <p className="small">Edinilen kamu kaynaklarının hazırlık kaydıdır. Kaynak veya pasaj sayısı; kullanım izni, hukuki inceleme, yayımlanmış sürüm veya derlemin tamlığı anlamına gelmez.</p>
      {state.status === 'loading' ? <Loading label="Kaynak hazırlık kayıtları yükleniyor…" /> : state.status === 'restricted' ? <Notice>Kaynak hazırlık kayıtlarını yalnızca yönetici ve küratörler görebilir. Genel kapsamı ve etkin graf sürümünün durumunu bu sayfadan incelemeye devam edebilirsiniz.</Notice> : state.status === 'failed' ? <Notice error>{state.message} Kaynak kabul kaydı alınamadı; genel kapsam bilgisi ayrı değerlendirilir.</Notice> : <>
        {state.catalog.items.length ? <div className="source-records">{state.catalog.items.map((source) => <SourceRecord key={source.id} source={source} />)}</div> : <p className="small muted source-summary">Henüz görünür hazırlık kaydı yok. Bu durum, ilgili hukuk alanında kaynak bulunmadığı anlamına gelmez.</p>}
        {state.catalog.limitations.length > 0 && <Detail title="Kaynak kabul kaydının sınırları"><ul>{state.catalog.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul></Detail>}
      </>}
      {state.status !== 'restricted' && <button className="text-button" disabled={state.status === 'loading'} onClick={onRetry}>{state.status === 'loading' ? 'Yükleniyor…' : 'Kaynak kaydını yenile'}</button>}
    </div>
  </section>;
}

function SourceRecord({ source }: { source: PublicSourceRecord }) {
  return <article className="source-record">
    <div className="section-heading compact"><h3>{source.title}</h3><Badge>{statusLabel(source.publication_status)}</Badge></div>
    <p className="small muted">{DOMAIN_LABELS[source.domain as keyof typeof DOMAIN_LABELS] || source.domain} · Edinim: {formatDate(source.acquired_at, true)}</p>
    <p className="small source-summary">{statusLabel(source.rights_status)} · {statusLabel(source.review_status)}</p>
    {/^[a-f0-9]{64}$/.test(source.id) && <a className="text-link" href={`#/sources/${source.id}`}>Kaynağı incele</a>}
    <Detail title="Kaynak ve sürüm ayrıntıları"><dl className="coverage-fields">
      <div><dt>Kaynak adresi</dt><dd className="reference-id">{source.source_url}</dd></div>
      <div><dt>Kaynak sürümü</dt><dd className="reference-id">{source.source_version_id}</dd></div>
      <div><dt>Kayıt kimliği</dt><dd className="reference-id">{source.id}</dd></div>
      <div><dt>Kullanım hakları</dt><dd>{statusLabel(source.rights_status)}</dd></div>
      <div><dt>Hukuki inceleme</dt><dd>{statusLabel(source.review_status)}</dd></div>
      <div><dt>Yayın durumu</dt><dd>{statusLabel(source.publication_status)}</dd></div>
      <div><dt>Hazırlanan pasajlar</dt><dd>{source.passage_count}</dd></div>
    </dl><p className="small muted">Kaynak adresi köken bilgisidir; bu ekran dış bağlantı kurmaz. Hazırlık kaydı araştırmada kullanılabilecek yayımlanmış bir hukuki dayanak değildir.</p></Detail>
  </article>;
}
