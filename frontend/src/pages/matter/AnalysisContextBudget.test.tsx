import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisContextBudget } from './AnalysisContextBudget';
import type { AnalysisContextPreview } from './analysisTypes';

function preview(fits = true): AnalysisContextPreview {
  return { recipe: 'private-analysis-context-budget-v1', scope: 'exact_first_pass_only', source_version_id: 'SYNTHETIC-v1',
    source_revision: 1, source_content_sha256: 'a'.repeat(64), source_review_id: null, mode: 'repair', max_passes: 2,
    model: '<script>SYNTHETIC</script>', transport: { mode: 'private_network', uses_public_network: false },
    prompt: { utf8_bytes: 3000, total_upper_bound_units: 4256, completion_tokens: 1000, messages_sha256: 'b'.repeat(64) },
    framing_reserve_units: 256, context_limit_units: fits ? 8192 : 4000, remaining_units: fits ? 3936 : 0,
    excess_units: fits ? 0 : 256, fits, configuration_ready: true, can_start: fits, preview_sha256: 'c'.repeat(64),
    evidence: [{ evidence_id: 'SYNTHETIC-source', document_revision: 2, start: 3, end: 100,
      passage_sha256: 'd'.repeat(64), quote_sha256: 'e'.repeat(64) }],
  };
}

describe('exact private analysis context budget', () => {
  it('shows exact source pins and accounting without implying model or legal verification', () => {
    const html = renderToStaticMarkup(<AnalysisContextBudget value={preview()} />);
    for (const text of ['İlk geçiş bağlama sığıyor', '4.256 / 8.192', '3.936 birim boşluk', 'UTF-8 bayt', 'Çerçeve payı',
      'çıktı', 'SYNTHETIC-v1', 'Belge revizyonu 2', '[3, 100)', 'Pasaj:', 'Alıntı:', 'düzeltme geçişi', 'hukuki onay değildir']) {
      expect(html.toLocaleLowerCase('tr-TR')).toContain(text.toLocaleLowerCase('tr-TR'));
    }
    expect(html).not.toContain('<script>'); expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<details open');
  });
  it('explains overflow and disabled configuration without offering automatic evidence removal', () => {
    const value = preview(false); value.configuration_ready = false;
    value.transport = { mode: 'approved_laptop_tunnel', uses_public_network: true };
    const html = renderToStaticMarkup(<AnalysisContextBudget value={value} />);
    for (const text of ['İş başlatılmaz', '256 birim aşım', 'Metin veya dayanak kesilmedi', 'önceki denemeler korunur',
      'ayrı, odaklı bir taslak sürümü', 'kimlik doğrulama veya model çağrısı yapmaz', 'air-gapped değildir']) expect(html).toContain(text);
  });
});
