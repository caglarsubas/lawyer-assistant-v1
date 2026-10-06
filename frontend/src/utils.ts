import type { Passage } from './types';

export const DOMAIN_LABELS = { contracts: 'Sözleşmeler', commercial: 'Ticaret hukuku', employment: 'İş hukuku' };
export const FACT_LABELS = { documented: 'Belgelenmiş', alleged: 'Beyan', disputed: 'Çekişmeli', assumption: 'Varsayım', inference: 'Çıkarım' };
const STATUS_LABELS: Record<string, string> = {
  active: 'Açık', draft: 'Taslak', reviewed: 'İncelendi', approved: 'Uygun bulundu', rejected: 'Düzeltme gerekli',
  pending: 'Bekliyor', unreviewed: 'İncelenmedi', pending_review: 'İnceleme bekliyor', requires_review: 'İnceleme gerekli',
  stale: 'Yeniden inceleme gerekli', invalidated: 'Yeniden inceleme gerekli', queued: 'Sırada', running: 'Çalışıyor', cancelling: 'Durduruluyor',
  timed_out: 'Süre doldu', interrupted: 'Kesildi',
  processing: 'İşleniyor', completed: 'Tamamlandı', succeeded: 'Tamamlandı', failed: 'Tamamlanamadı', cancelled: 'İptal edildi',
  ready: 'Hazır', extracted: 'Metin çıkarıldı', unsupported: 'Desteklenmiyor', needs_review: 'İnceleme gerekli',
  blocked: 'Kurulum tamamlanmalı', unavailable: 'Hizmete ulaşılamadı', healthy: 'Erişilebilir', not_checked: 'Denetlenmedi',
  'demo-bypass': 'Demo · Tarama atlandı', 'demo-local': 'Demo · Yerel çıkarım',
  staged: 'Hazırlık kaydı', rights_pending: 'Kullanım hakları inceleme bekliyor', legal_review_pending: 'Hukuki inceleme bekliyor',
  fixture: 'Örnek veri', demo: 'Demo', disconnected: 'Bağlantı yok', not_configured: 'Yapılandırılmadı',
  documented: 'Belgelenmiş', alleged: 'Beyan', disputed: 'Çekişmeli', assumption: 'Varsayım', inference: 'Çıkarım',
  document_quote: 'Belge alıntısı', factual: 'Olgu', legal: 'Hukuki değerlendirme', quotation: 'Alıntı',
  extractive: 'Belgeden çıkarılan pasajlar', 'local-provider-validated-quotes': 'Yerel sağlayıcı · Denetlenen alıntılar',
  local: 'Yerel', fixture_only: 'Yalnızca örnek veri', unqualified: 'Doğrulama bekleniyor',
  catalog: 'Ontoloji kataloğu', 'configured-unqualified': 'Yapılandırılmış · Doğrulama bekliyor',
  not_loaded: 'Henüz yüklenmedi', observed: 'Kayıtlar gözlendi', legally_reviewed: 'Hukuki incelemeden geçti',
  unreviewed_schema: 'Şema · İncelenmedi', ontology_class: 'Ontoloji sınıfı', domain_concept: 'Hukuk kavramı',
  broader_concept: 'Daha geniş kavram', subclass_of: 'Alt sınıfı',
};
export function statusLabel(status?: string) { return status ? STATUS_LABELS[status.toLowerCase()] || status : 'Bilinmiyor'; }
export function formatDate(value?: string | null, withTime = false) {
  if (!value) return 'Belirtilmedi';
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00+03:00`) : new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'short', year: 'numeric', ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}) }).format(date);
}
export function locatorText(locator: Passage['locator']) {
  if (typeof locator === 'string') return locator;
  return Object.entries(locator || {}).map(([key, value]) => `${({ page: 'Sayfa', paragraph: 'Paragraf', sheet: 'Sayfa', cell: 'Hücre', line: 'Satır' } as Record<string, string>)[key] || key}: ${String(value)}`).join(' · ') || 'Konum belirtilmedi';
}
export function messageOf(error: unknown) { return error instanceof Error ? error.message : 'Beklenmeyen bir hata oluştu.'; }
export function isRunning(status: string) { return ['queued', 'running', 'cancelling', 'processing', 'pending'].includes(status); }
export function slugId(value: string) { return value.replace(/[^a-zA-Z0-9_-]/g, '-'); }
