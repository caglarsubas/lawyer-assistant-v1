import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AnalysisAuthorities, { AuthorityContextView, LinkedAuthorityView, selectionPayload } from './AnalysisAuthorities';
import { committedAuthorityReceipt, occurrence, occurrenceKey } from './authorityTypes';
import type { AuthorityContext, AuthoritySelection, AuthoritySource, LinkedAuthority } from './authorityTypes';
import type { AnalysisRecord } from './analysisTypes';

const source: AuthoritySource = {
  assertion_id: 'urn:synthetic:assertion', passage_id: 'urn:synthetic:passage', authority_id: 'urn:synthetic:decision',
  document_id: 'urn:synthetic:raw', source_version_id: 'urn:synthetic:text', source_sha256: 'a'.repeat(64), release_id: 'b'.repeat(64),
  text: 'SYNTHETIC quote <img src="private">', locator: 'SYNTHETIC §1', start_offset: 5, end_offset: 48,
  quote_sha256: 'c'.repeat(64), text_sha256: 'd'.repeat(64), locator_map_sha256: 'e'.repeat(64), graph_family: 'jurisprudence',
  subject_id: 'urn:synthetic:decision', predicate: 'https://lawyer-assistant.local/ontology/cites', object_id: 'urn:synthetic:version-old',
  review_status: 'legally_reviewed', recorded_at: '2026-01-01T00:00:00Z', reviewed_at: '2026-01-01T00:00:00Z',
  valid_from: '2023-01-01', valid_to: '2030-01-01', validity_end_status: 'closed', validity_checked_through: null,
  target_provision_version: { id: 'urn:synthetic:version-old', version_of: 'urn:synthetic:provision', resolution: 'resolved',
    validity: { kind: 'closed', start: '1920-01-01', end: '2024-01-01', checked_through: null, evidence: [] } },
  candidate_only: true, matter_applicability: 'not_assessed', binding_effect: 'not_assessed',
};
const selection: AuthoritySelection = { ...occurrence(source), target_ids: ['rule:r1'], relationship: 'adverse_candidate', note: 'SYNTHETIC private lawyer note <script>private</script>' };
const linked: LinkedAuthority = { selection, evidence: source, target_snapshots: { 'rule:r1': { text: 'SYNTHETIC original private step' } }, temporal_alignment: {
  research_as_of: '2023-03-01', analysis_event_date: '2024-03-01', dates_equal: false, within_assertion_interval: true,
  target_version_within_interval: false, applicability: 'not_assessed',
} };

function context(): AuthorityContext {
  return { id: 'aac-' + 'a'.repeat(20) + '-' + 'b'.repeat(32), title: 'SYNTHETIC context', version_id: 'v1',
    registered_at: '2026-01-01T00:00:00Z', manifest_sha256: 'f'.repeat(64), packet_sha256: 'a'.repeat(64),
    public_source_access: true, freshness: { status: 'current', reasons: [] }, qualification_granted: false,
    production_qualified: false, runtime_authorization: 'none', manifest: {
      recipe: 'SYNTHETIC fixture', version_id: 'v1', product_id: 'r1', title: 'SYNTHETIC context', purpose: 'SYNTHETIC purpose',
      selections: [selection], sources: [linked], analysis_content: {} as AnalysisRecord, analysis_content_sha256: 'c'.repeat(64),
      analysis_review_id: null, product_sha256: 'd'.repeat(64),
      graph_release_pin: { status: 'verified', release_id: 'a'.repeat(64), serving_sha256: 'b'.repeat(64), activation_sequence: 3 },
      legal_approval: 'not_granted', matter_applicability: 'not_assessed', binding_effect: 'not_assessed', model_use: 'none',
    } };
}

describe('explicit private public-authority context', () => {
  it('preserves citation, exact occurrence, expired version and historical date differences without qualifying applicability', () => {
    const html = renderToStaticMarkup(<LinkedAuthorityView source={linked} />);
    for (const text of ['Karşı dayanak adayı', 'Avukat bağlantı beyanı', 'farklı ya da belirsiz', 'uygulanabilirlik belirlemez', 'cites', 'urn:synthetic:version-old', 'rule:r1', '[5, 48)', 'Kaynak SHA-256', 'Çıkarılmış metin sürümü']) expect(html).toContain(text);
    expect(html).not.toContain('<details open');
    expect(html).not.toContain('<img src'); expect(html).not.toContain('<script>private');
    expect(html).toContain('&lt;img'); expect(html).toContain('&lt;script');
  });
  it('hides the entire manifest when current publication access is unavailable even if a stale payload remains in memory', () => {
    const value = context(); value.public_source_access = false; value.freshness.status = 'withheld';
    const html = renderToStaticMarkup(<AuthorityContextView value={value} />);
    expect(html).toContain('Kamu içeriği bekletiliyor'); expect(html).toContain('Önceki kayıt korunur');
    expect(html).not.toContain(source.text); expect(html).not.toContain('SYNTHETIC original private step');
    expect(html).not.toContain('urn:synthetic:version-old');
  });
  it('labels stale snapshots as historical content with export closed while keeping the frozen lawyer role', () => {
    const value = context(); value.freshness.status = 'stale'; value.freshness.reasons = ['private_analysis_changed'];
    const html = renderToStaticMarkup(<AuthorityContextView value={value} />);
    expect(html).toContain('Aktarım kapalı'); expect(html).toContain('Saklanan önceki içerik');
    expect(html).toContain('Karşı dayanak adayı'); expect(html).toContain('Hukuki onay');
  });
  it('requires explicitly filled roles, notes and targets and strips source text from the selection payload', () => {
    expect(selectionPayload([{ ...selection, relationship: '' }])).toBeNull();
    expect(selectionPayload([{ ...selection, note: '  ' }])).toBeNull();
    expect(selectionPayload([{ ...selection, target_ids: [] }])).toBeNull();
    expect(selectionPayload([{ ...selection, target_ids: ['rule:r1', 'rule:r1'] }])).toBeNull();
    expect(selectionPayload([selection, selection])).toBeNull();
    expect(selectionPayload([{ ...source, ...selection }])).toEqual([selection]);
  });
  it('keeps authorities linked to the same passage as different exact occurrences', () => {
    expect(occurrenceKey(source)).not.toBe(occurrenceKey({ ...source, assertion_id: 'urn:synthetic:other-assertion' }));
    expect(occurrenceKey(source)).not.toBe(occurrenceKey({ ...source, authority_id: 'urn:synthetic:other-authority' }));
  });
  it('recognizes only an explicit safe committed-needs-revalidation receipt, never a generic error as a save', () => {
    const id = context().id;
    expect(committedAuthorityReceipt({ id, outcome: 'committed_needs_revalidation', needs_revalidation: true })).toBe(id);
    for (const value of [null, { id }, { id, outcome: 'failed', needs_revalidation: true }, { id: '../private', outcome: 'committed_needs_revalidation', needs_revalidation: true }]) expect(committedAuthorityReceipt(value)).toBeNull();
  });
  it('loads no sources or research automatically and leaves details collapsed', () => {
    const record = { id: 'analysis1', latest_version_id: 'v1' } as AnalysisRecord;
    const html = renderToStaticMarkup(<AnalysisAuthorities matterId="matter1" record={record} />);
    expect(html).toContain('Araştırma kayıtlarını getir'); expect(html).toContain('Saklanan dayanak bağlamlarını getir');
    expect(html).not.toContain(source.text); expect(html).not.toContain('<details open');
  });
});
