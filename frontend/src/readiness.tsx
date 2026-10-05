import { Badge, Detail } from './components';
import type { IntakeReadiness, ReadinessIssue, ReadinessState, RuntimeReadiness } from './types';
import { formatDate, statusLabel } from './utils';

const READINESS_LABELS: Record<ReadinessState, string> = {
  ready: 'Bağlantı doğrulandı', blocked: 'Kurulum tamamlanmalı', unavailable: 'Hizmete ulaşılamadı',
};

export function uploadAllowed(demo: boolean, intake: IntakeReadiness | null, checking: boolean) {
  return demo || (!checking && intake?.status === 'ready');
}

export function ReadinessIssues({ issues }: { issues: ReadinessIssue[] }) {
  return issues.length > 0 ? <Detail title={`Yapılacaklar (${issues.length})`}><ul>{issues.map((issue) => <li key={issue.code}>{issue.message}</li>)}</ul></Detail> : null;
}

export function ProviderReadiness({ provider, checkedAt }: { provider: RuntimeReadiness['provider']; checkedAt: string }) {
  return <div className="readiness-result" aria-label="Son sağlayıcı bağlantı denetimi">
    <div className="section-heading compact"><Badge status={provider.status === 'ready' ? 'ready' : 'unreviewed'}>{READINESS_LABELS[provider.status]}</Badge><span className="small muted">Son denetim: {formatDate(checkedAt, true)}</span></div>
    <p className="small">{provider.status === 'ready' ? 'Seçili modele erişim gözlendi. Yanıt üretimi, model yetenekleri ve hukuki doğruluk bu denetimde sınanmaz.' : provider.issues[0]?.message || 'Sağlayıcı bağlantısı doğrulanamadı. Yapılandırmayı gözden geçirip yeniden denetleyin.'}</p>
    <ReadinessIssues issues={provider.issues} />
    <Detail title="Denetimin kapsamı"><dl className="status-register">
      <div><dt>Yapılandırma</dt><dd>{provider.checks.configuration ? 'Uygun' : 'Tamamlanmadı'}</dd></div>
      <div><dt>Kimlik doğrulamalı bağlantı</dt><dd>{provider.checks.connection ? 'Doğrulandı' : 'Doğrulanmadı'}</dd></div>
      <div><dt>Seçili modele erişim</dt><dd>{provider.checks.model ? 'Doğrulandı' : 'Doğrulanmadı'}</dd></div>
      {provider.model && <div><dt>Seçili model</dt><dd>{provider.model}</dd></div>}
      {provider.transport && <div><dt>Bağlantı yolu</dt><dd>{provider.transport.mode === 'approved_laptop_tunnel' ? 'Onaylı dizüstü tüneli (internet)' : 'Özel ağ'}</dd></div>}
      <div><dt>Yanıt üretimi</dt><dd>Bu denetimin kapsamı dışında</dd></div>
    </dl><p className="small muted">Bu kayıt belirtilen zamandaki bağlantıyı gösterir; üretim yeterliliğini, tenant eşleşmesini veya hukuki doğruluğu onaylamaz.</p></Detail>
  </div>;
}

export function IntakeReadinessDetails({ intake }: { intake: IntakeReadiness }) {
  return <Detail title="Belge kabulü denetim ayrıntıları"><dl className="status-register">
    <div><dt>Zararlı içerik tarayıcısı</dt><dd>{statusLabel(intake.scanner.status)}</dd></div>
    {intake.scanner.version && <div><dt>Tarayıcı sürümü</dt><dd>{intake.scanner.version}</dd></div>}
    {intake.scanner.signature_date && <div><dt>İmza tarihi</dt><dd>{formatDate(intake.scanner.signature_date, true)}</dd></div>}
    <div><dt>Belge çıkarım hizmeti</dt><dd>{statusLabel(intake.extractor.status)}</dd></div>
  </dl><p className="small muted">{intake.demo_mode ? 'Sentetik geliştirme modunda üretim güvenlik kontrolleri doğrulanmaz. Gerçek müvekkil belgesi yüklemeyin.' : 'Her dosya yüklenirken yeniden denetlenir. Bağlantı denetimi bir dosyanın güvenli veya eksiksiz çıkarılabilir olduğunu garanti etmez.'}</p></Detail>;
}
