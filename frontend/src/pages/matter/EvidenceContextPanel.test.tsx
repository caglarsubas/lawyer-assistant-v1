import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { EvidenceContextPack } from '../../types';
import { EvidenceContextPanel } from './EvidenceContextPanel';

function fixture(): EvidenceContextPack {
  return {
    recipe: 'private-evidence-pack-v1', scope: 'private_document_quotes', offset_unit: 'unicode_code_points',
    provider_use: 'validated_quote_response', limits: { max_passages: 8, context_limit_units: 8192 },
    prompt: { messages_sha256: 'a'.repeat(64), accounting: 'utf8_bytes_plus_fixed_reserves' },
    inventory: { input_passages: 4, examined_passages: 3, unexamined_passages: 1,
      selected_passages: 1, omitted_passages: 3, shortened_passages: 1, selected_documents: 1,
      examined_documents: 2, scanned_code_points: 3000, evidence_utf8_bytes: 200 },
    selected: [{ passage_id: 'e1', document_id: 'd1', document_name: '<script>PRIVATE</script>',
      document_revision: 2, document_sha256: 'b'.repeat(64), original_text_sha256: 'c'.repeat(64),
      excerpt_text_sha256: 'd'.repeat(64), excerpt_start: 1500, excerpt_end: 1600,
      full_passage_length: 3000, boundary: 'token_fragment', utf8_bytes: 200, matched_query_terms: 2 }],
    omitted: [{ passage_id: 'e2', document_id: 'd1', reason: 'prompt_budget' }],
    omission_counts: { prompt_budget: 2, scan_budget: 1 },
  };
}

function render(pack = fixture(), evidence = [{ id: 'e1', text: 'Ödeme yapılmaz. <img src="x">', locator: 'SYNTHETIC line' }]) {
  return renderToStaticMarkup(<EvidenceContextPanel pack={pack} evidence={evidence} onSource={() => {}} />);
}

describe('inspectable private context', () => {
  it('shows explicit partial coverage, original offsets and full-source control', () => {
    const html = render();
    expect(html).toContain('1 / 4 pasaj seçildi');
    expect(html).toContain('1 kısaltıldı');
    expect(html).toContain('3 dışarıda kaldı');
    expect(html).toContain('[1500, 1600)');
    expect(html).toContain('Unicode karakterleriyledir');
    expect(html).toContain('Cümle veya satır parçası seçildi');
    expect(html).toContain('Koşul, istisna');
    expect(html).toContain('Özgün pasajı aç');
    expect(html).toContain('tarama sınırı nedeniyle');
    expect(html).toContain('Model bağlam sınırı: 2');
    expect(html).toContain('Kamu kaynak adayları ayrı gösterilir');
  });
  it('keeps details collapsed and treats filenames and excerpts as text', () => {
    const html = render();
    expect(html).not.toContain('<details open');
    expect(html).not.toContain('<script>PRIVATE');
    expect(html).not.toContain('<img src');
    expect(html).toContain('&lt;script&gt;PRIVATE');
    expect(html).toContain('Ödeme yapılmaz. &lt;img');
  });
  it.each(['not_configured', 'no_selected_evidence'] as const)('does not imply model use for %s', (status) => {
    const pack = fixture();
    pack.provider_use = status;
    const html = render(pack);
    expect(html).toContain('Model çağrısı yapılmadı');
    expect(html).not.toContain('Model yanıtı, aşağıdaki');
  });
  it('identifies missing retained excerpts without pretending they are available', () => {
    expect(render(fixture(), [])).toContain('Kaydedilmiş alıntı metni bulunamadı');
  });
  it('distinguishes preparation only from an observed unused provider', () => {
    const pack = fixture();
    pack.provider_use = 'prepared_only';
    const html = render(pack);
    expect(html).toContain('model kullanımı doğrulanmadı');
    expect(html).not.toContain('Model çağrısı yapılmadı');
  });
});
