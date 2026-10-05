import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { IntakeReadinessDetails, ProviderReadiness, uploadAllowed } from './readiness';
import DocumentsPanel from './pages/matter/DocumentsPanel';
import SystemPage from './pages/SystemPage';
import type { IntakeReadiness, Matter, RuntimeReadiness, SystemStatus } from './types';

const intake: IntakeReadiness = { status: 'ready', issues: [], scanner: { status: 'ready', version: '1.4', signature_date: '2026-10-04T08:00:00Z' }, extractor: { status: 'ready' } };
const matter: Matter = { id: 'm1', title: 'Çalışma', domain: 'contracts', objective: '', represented_party: '', stage: '', status: 'draft', document_count: 0, created_at: '2026-10-04T08:00:00Z', documents: [] };
const provider: RuntimeReadiness['provider'] = { status: 'ready', issues: [], model: 'local-model', checks: { configuration: true, connection: true, model: true }, qualification: 'runtime-connectivity-only' };
const status: SystemStatus = {
  demo_mode: false,
  provider: { configured: true, identity_verified: true, tenant_id: 'lawyer-assistant-v1', organization: 'org-lawyer', key_id: 'lawyer-assistant-v1-primary', mode: 'local' },
  graphs: { mode: 'local', ontology_version: 'v1', legal_review_status: 'unreviewed' }, services: {}, limitations: [],
};

describe('readiness evidence and upload boundaries', () => {
  it('identifies the approved laptop tunnel as internet transport inside details', () => {
    const markup = renderToStaticMarkup(<ProviderReadiness provider={{ ...provider, transport: { mode: 'approved_laptop_tunnel', uses_public_network: true } }} checkedAt="2026-10-05T00:00:00+08:00" />);
    expect(markup).toContain('Onaylı dizüstü tüneli (internet)');
    expect(markup).toContain('Bağlantı yolu');
    expect(markup).not.toContain('<details class="details" open');
  });
  it('fails closed for unknown, failed and refreshing intake while keeping provider setup independent', () => {
    expect(uploadAllowed(false, null, false)).toBe(false);
    expect(uploadAllowed(false, { ...intake, status: 'blocked' }, false)).toBe(false);
    expect(uploadAllowed(false, { ...intake, status: 'unavailable' }, false)).toBe(false);
    expect(uploadAllowed(false, intake, true)).toBe(false);
    expect(uploadAllowed(false, intake, false)).toBe(true);
    expect(uploadAllowed(true, null, false)).toBe(true);
  });

  it('disables all production upload entry points before a readiness response', () => {
    const markup = renderToStaticMarkup(<DocumentsPanel matter={matter} onChange={async () => undefined} />);
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>[^<]*<svg[\s\S]*?Dosya yükle<\/button>/);
    expect(markup).toMatch(/<input[^>]*type="file"[^>]*disabled=""/);
    expect(markup).toMatch(/class="upload-zone[^"]*" aria-disabled="true"/);
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Dosya seçin veya buraya bırakın<\/button>/);
    expect(markup).toContain('Belge kabulü denetleniyor');
  });

  it('permits demo upload only with an explicit synthetic-environment warning', () => {
    const markup = renderToStaticMarkup(<DocumentsPanel matter={matter} demo onChange={async () => undefined} />);
    expect(markup).toContain('Sentetik demo ortamı.');
    expect(markup).toContain('gerçek müvekkil belgesi yüklemeyin');
    expect(markup).not.toMatch(/<input[^>]*type="file"[^>]*disabled/);
    expect(markup).toContain('aria-disabled="false"');
  });

  it('does not mistake configured credentials or operator assertions for a live check', () => {
    const markup = renderToStaticMarkup(<SystemPage status={status} onStatus={() => undefined} />);
    expect(markup).toContain('Bağlantıları denetle');
    expect(markup).toContain('Henüz denetlenmedi');
    expect(markup).toContain('Canlı bağlantı kaydı yok.');
    expect(markup).not.toContain('Bağlantı doğrulandı');
    expect(markup).not.toContain('<details class="details" open');
  });

  it('shows timestamped connection evidence without implying model completion or legal qualification', () => {
    const markup = renderToStaticMarkup(<ProviderReadiness provider={provider} checkedAt="2026-10-04T08:00:00Z" />);
    expect(markup).toContain('Bağlantı doğrulandı');
    expect(markup).toContain('Son denetim:');
    expect(markup).toContain('local-model');
    expect(markup).toContain('Yanıt üretimi, model yetenekleri ve hukuki doğruluk bu denetimde sınanmaz.');
    expect(markup).toContain('tenant eşleşmesini');
    expect(markup).not.toContain('<details class="details" open');
    const failedMarkup = renderToStaticMarkup(<ProviderReadiness provider={{ ...provider, status: 'blocked', issues: [{ code: 'wrong_model', message: 'Seçili modele erişilemiyor.' }], checks: { ...provider.checks, model: false } }} checkedAt="2026-10-04T08:00:00Z" />);
    expect(failedMarkup).toContain('Seçili modele erişilemiyor.');
    expect(failedMarkup).not.toContain('Bağlantı doğrulandı');
  });

  it('keeps scanner evidence inspectable without claiming uploaded documents passed screening', () => {
    const markup = renderToStaticMarkup(<IntakeReadinessDetails intake={intake} />);
    expect(markup).toContain('Tarayıcı sürümü');
    expect(markup).toContain('İmza tarihi');
    expect(markup).toContain('Her dosya yüklenirken yeniden denetlenir.');
    expect(markup).not.toContain('<details class="details" open');
    const demoMarkup = renderToStaticMarkup(<IntakeReadinessDetails intake={{ ...intake, demo_mode: true, scanner: { status: 'demo-bypass' } }} />);
    expect(demoMarkup).toContain('üretim güvenlik kontrolleri doğrulanmaz');
    expect(demoMarkup).not.toContain('Her dosya yüklenirken yeniden denetlenir.');
  });
});
