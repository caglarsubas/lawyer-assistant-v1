import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ValidityDetails } from './ValidityDetails';

it('separates exact validity proof from the provision and exposes the inclusive horizon without extrapolation', () => {
  const html = renderToStaticMarkup(<ValidityDetails validity={{ validity_end_status: 'open_ended', validity_checked_through: '2025-12-31', validity_evidence: [{ id: 'urn:proof:1', artifact_id: 'urn:source:1', locator: 'Sayfa 1', text: '<script>Sentetik dayanak</script>', sha256: 'a'.repeat(64), text_representation_id: 'urn:text:1', text_sha256: 'b'.repeat(64), locator_map_sha256: 'c'.repeat(64), start_offset: 0, end_offset: 35, grounding_status: 'verified_release_quote' }] }} />);
  expect(html).toContain('bu gün dahil'); expect(html).toContain('yeniden inceleme'); expect(html).toContain('hükmün metninden ayrı');
  expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>'); expect(html).toContain('Sayfa 1'); expect(html).not.toContain(' open=');
  expect(renderToStaticMarkup(<ValidityDetails validity={{ validity_end_status: 'closed' }} />)).toBe('');
});
