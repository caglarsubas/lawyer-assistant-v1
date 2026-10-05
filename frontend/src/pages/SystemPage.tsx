import { useState } from 'react';
import { request } from '../api';
import { Badge, Detail, Icon, JsonDetails, Notice, PageHeader } from '../components';
import { IntakeReadinessDetails, ProviderReadiness, ReadinessIssues } from '../readiness';
import type { RuntimeReadiness, SystemStatus } from '../types';
import { formatDate, messageOf, statusLabel } from '../utils';

export default function SystemPage({ status, onStatus }: { status: SystemStatus | null; onStatus: (value: SystemStatus) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [readiness, setReadiness] = useState<RuntimeReadiness | null>(null);
  async function refresh() {
    setBusy(true); setError('');
    const [configuration, runtime] = await Promise.allSettled([
      request<SystemStatus>('/status'), request<RuntimeReadiness>('/readiness'),
    ]);
    if (configuration.status === 'fulfilled') onStatus(configuration.value);
    if (runtime.status === 'fulfilled') setReadiness(runtime.value);
    const failures = [configuration, runtime].flatMap((result) => result.status === 'rejected' ? [messageOf(result.reason)] : []);
    if (failures.length) setError(`${[...new Set(failures)].join(' · ')}${runtime.status === 'rejected' && readiness ? ' Aşağıda önceki denetim kaydı gösteriliyor.' : ''}`);
    setBusy(false);
  }
  return <>
    <PageHeader eyebrow="KURULUM VE HİZMETLER" title="Görünür durum, açık sınırlar." description="Hizmet bağlantılarını denetleyin ve çalışmaya başlamadan önce eksikleri görün." action={<button className="button secondary" disabled={busy} onClick={() => void refresh()}>{busy ? 'Denetleniyor…' : 'Bağlantıları denetle'}</button>} />
    {error && <Notice error>{error}</Notice>}
    <div className="system-layout"><section>
      <div className="section-heading"><h2>Dil modeli sağlayıcısı</h2>{!readiness && <Badge>Henüz denetlenmedi</Badge>}</div>
      {readiness ? <ProviderReadiness provider={readiness.provider} checkedAt={readiness.checked_at} /> : <p className="small muted">Canlı bağlantı kaydı yok. Bağlantıları denetleyerek seçili modele erişimi kontrol edin.</p>}
      {!readiness && status?.provider.readiness?.issues.length ? <ReadinessIssues issues={status.provider.readiness.issues} /> : null}
      {status && <Detail title="Sağlayıcı yapılandırması"><dl className="status-register">
        <div><dt>Bağlantı ayarları</dt><dd>{status.provider.configured ? 'Yapılandırılmış' : 'Yapılandırma bekleniyor'}</dd></div>
        <div><dt>Çalışma modu</dt><dd>{statusLabel(status.provider.mode)}</dd></div>
        <div><dt>Tenant</dt><dd>{status.provider.tenant_id || 'Belirtilmedi'}</dd></div>
        <div><dt>Organizasyon</dt><dd>{status.provider.organization || 'Belirtilmedi'}</dd></div>
        <div><dt>Anahtar kimliği</dt><dd>{status.provider.key_id || 'Belirtilmedi'}</dd></div>
        <div><dt>Operatör eşleşme beyanı</dt><dd>{status.provider.identity_verified ? 'Var' : 'Yok'}</dd></div>
      </dl><p className="small muted">API anahtarı yalnızca sunucuda tutulur. Anahtarın tanımlanması veya operatör beyanı, tenant eşleşmesinin bağımsız olarak doğrulandığı anlamına gelmez.</p></Detail>}

      <div className="section-heading section-spaced"><h2>Belge kabulü</h2><Badge status={readiness?.intake.status === 'ready' && !readiness.intake.demo_mode ? 'ready' : undefined}>{!readiness ? 'Henüz denetlenmedi' : readiness.intake.demo_mode ? 'Yalnızca sentetik demo' : readiness.intake.status === 'ready' ? 'Yükleme kullanılabilir' : 'Yükleme kullanılamıyor'}</Badge></div>
      {readiness ? <>
        <p className="small muted">Son denetim: {formatDate(readiness.checked_at, true)}</p>
        <p className="small">{readiness.intake.demo_mode ? 'Sentetik geliştirme modu etkin. Gerçek müvekkil belgesi yüklemeyin; üretim güvenlik kontrolleri bu modda doğrulanmaz.' : readiness.intake.status === 'ready' ? 'Belge kabulü için gerekli yerel hizmetler erişilebilir. Dosyalar yükleme sırasında ayrıca taranır.' : readiness.intake.issues[0]?.message || 'Belge kabulü için gerekli hizmetler doğrulanamadı.'}</p>
        <ReadinessIssues issues={readiness.intake.issues} />
        <IntakeReadinessDetails intake={readiness.intake} />
      </> : <p className="small muted">Zararlı içerik tarayıcısı ve belge çıkarım hizmeti birlikte kontrol edilir. Belge yüklemek için dil modelinin bağlı olması gerekmez.</p>}
      {status ? <>
        <div className="section-heading section-spaced"><h2>Bilgi grafı</h2><Badge status={status.graphs.legal_review_status} /></div>
        <dl className="status-register"><div><dt>Çalışma modu</dt><dd>{statusLabel(status.graphs.mode)}</dd></div><div><dt>Ontoloji sürümü</dt><dd>{status.graphs.ontology_version || 'Belirtilmedi'}</dd></div></dl>
        <JsonDetails value={status.services} title="Hizmetlerin teknik durumu" />
      </> : <Notice>Yapılandırma kaydı alınamadı. Bağlantıları denetleyerek yeniden deneyin.</Notice>}
    </section><aside className="system-limitations"><Icon name="shield" size={26} /><h2>Bu kurulumun<br />sınırları.</h2>
      <p>Bağlantı denetimi; yanıt üretimi, kaynak doğruluğu veya hukuki yeterlilik testi değildir.</p>
      <Detail title="Bildirilen sınırlılıklar">{[...(status?.limitations || []), ...(readiness?.limitations || [])].length ? <ul>{[...new Set([...(status?.limitations || []), ...(readiness?.limitations || [])])].map((item) => <li key={item}>{item}</li>)}</ul> : <p>Bildirilen sınırlılık yok. Bu kayıt tek başına üretim hazır olma kanıtı değildir.</p>}</Detail>
      <a className="text-link" href="#/coverage">Kaynak kapsamına git<Icon name="arrow" size={15} /></a>
    </aside></div>
  </>;
}
