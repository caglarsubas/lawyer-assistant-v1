import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ApiError, onUnauthorized, setCsrfToken } from '../api';
import type { ProvisionCandidate, ProvisionCandidates, ProvisionMapping, ProvisionMappingState, ProvisionSpanPreview, User } from '../types';
import ProvisionMappingPage, { EMPTY_MAPPING_REVIEW, EMPTY_PROPOSAL, fetchMappingDossier, fetchProvisionSpan, MappingRecord, MappingSummary, mappingReviewDraft, mappingReviewPayload, matchesPreview, proposalPayload, ProvisionCandidateList, ProvisionQuote, provisionPath, spanCoordinates, writeProvisionMapping, type MappingReviewDraft } from './ProvisionMappingPage';

const sourceId = 'a'.repeat(64); const mappingId = 'b'.repeat(32); const user: User = { id: 'reviewer-1', name: 'İnceleyen', role: 'curator', firm_id: 'firm-1' };
const state: ProvisionMappingState = {
  source: { id: sourceId, title: '<img src=x onerror=alert(1)>', source_url: 'javascript:alert(1)', source_version_id: 'historical-enacted', domain: 'contracts', acquired_at: null, rights_status: 'rights_pending', review_status: 'legal_review_pending', passage_count: 3, publication_status: 'staged', dates: { published_on: null, effective_from: null, effective_until: null }, artifacts: { 'text.txt': { sha256: 'c'.repeat(64), bytes: 200 } }, integrity_scope: 'all_artifacts_verified', limitations: [], injection_risk_hints: [], review_evidence: { rights_supplied: false, identity_supplied: false, trust: 'operator_supplied_unverified' } },
  revision: 2, source_review_revision: 5, assigned_to: { id: user.id, name: user.name }, source_review_ready: true, items: [], history: [], history_truncated: false, handoff_ready: false, publication_eligible: false, limitations: ['Güncel hukuk olduğu varsayılamaz.'],
};
const preview: ProvisionSpanPreview = { source_id: sourceId, source_version_id: 'historical-enacted', text_sha256: 'c'.repeat(64), span: { start: 7, end: 20, text: '<script>⚖️</script>\nTürkçe.', sha256: 'd'.repeat(64) }, passage_ids: ['p1', 'p2'], non_whitespace_covered: true };
const candidate: ProvisionCandidate = { id: 'e'.repeat(64), kind: 'article', number: '1', label: 'MADDE 1', heading: { start: 7, end: 14, text: 'MADDE 1', sha256: 'f'.repeat(64) }, proposed_span: preview.span, passage_ids: ['p1'], warnings: ['Editoryal <iframe> metni olabilir.'], status: 'machine_proposed', identity_status: 'unresolved', non_whitespace_covered: true };
const candidates: ProvisionCandidates = { source_id: sourceId, source_version_id: 'historical-enacted', text_sha256: preview.text_sha256, extraction_version: 'heading-v1', items: [candidate], total: 21, next_offset: 20, truncated: false, limitations: ['Sınırlar insan incelemesi gerektirir.'] };
const accepted: MappingReviewDraft = { ...EMPTY_MAPPING_REVIEW, decision: 'accepted', rationale: 'Tam metin ve kimlik dayanakları incelendi.', reference: 'yerel inceleme belgesi', sha256: 'f'.repeat(64), start: '7', end: '20', instrument_ref: 'Tarihsel düzenleme', provision_ref: 'Madde 1 referansı', provision_version_ref: 'Kabul edilen ilk metin' };
const snapshot = { candidate_id: candidate.id, kind: candidate.kind, label: candidate.label, span: preview.span, passage_ids: preview.passage_ids, non_whitespace_covered: true, status: 'accepted' as const, resolution: { start: 7, end: 20, instrument_ref: 'javascript:untrusted()', provision_ref: 'Madde 1', provision_version_ref: 'İlk metin', text_role: 'unknown' as const, valid_from: null, valid_until: null }, reviewed_source_revision: 4 };
const mapping: ProvisionMapping = { id: mappingId, ...snapshot, stale: true, last_event: { id: 'event-1', mapping_id: mappingId, revision: 2, event_type: 'review', reviewer: { id: user.id, name: user.name }, created_at: '2026-10-04T10:00:00Z', rationale: '<img src=x> Tarih çözümlenemedi.', decision: 'accepted', evidence_refs: [{ reference: 'javascript:alert(1)', sha256: sourceId }], source_review_revision: 4, snapshot } };

describe('provision mapping review controls', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); setCsrfToken('test-csrf'); onUnauthorized(); });
  afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(''); onUnauthorized(); });

  it('denies noncurators before any source fetch or review form', () => {
    const markup = renderToStaticMarkup(<ProvisionMappingPage sourceId={sourceId} user={{ ...user, role: 'lawyer' }} />);
    expect(markup).toContain('İnceleme yetkisi gerekli'); expect(markup).not.toContain('<form'); expect(fetchMock).not.toHaveBeenCalled();
  });
  it.each(['../auth', 'A'.repeat(64), 'a'.repeat(63), `${sourceId}/export`, `${sourceId}?token=x`])('rejects unsafe source identifiers %s', identifier => {
    expect(() => provisionPath(identifier)).toThrow('Kaynak kimliği geçersiz');
    expect(renderToStaticMarkup(<ProvisionMappingPage sourceId={identifier} user={user} />)).toContain('Kaynak kimliği geçersiz');
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('renders automatic candidates as unresolved with escaped exact headings, warnings and explicit truncation', () => {
    const markup = renderToStaticMarkup(<ProvisionCandidateList data={{ ...candidates, truncated: true }} offset={0} selectedId={candidate.id} disabled={false} onSelect={() => undefined} onPage={() => undefined} />);
    expect(markup).toContain('Otomatik aday · kimlik çözülmedi'); expect(markup).toContain('1–1 / 21 başlık adayı');
    expect(markup).toContain('eksiksiz dökümü değildir'); expect(markup).toContain('&lt;iframe&gt;'); expect(markup).not.toContain('<iframe>');
    expect(markup).toContain('aria-pressed="true"'); expect(markup).toContain('disabled="">Önceki adaylar'); expect(markup).not.toContain('<details class="details" open');
  });
  it('shows actionable no-heading state and stops at the last candidate page', () => {
    const markup = renderToStaticMarkup(<ProvisionCandidateList data={{ ...candidates, items: [], next_offset: null }} offset={20} selectedId={null} disabled={false} onSelect={() => undefined} onPage={() => undefined} />);
    expect(markup).toContain('elle aralık önerebilirsiniz'); expect(markup).toContain('disabled="">Sonraki adaylar');
  });
  it('shows exact Unicode text as inert plain text with explicit missing-coverage warning', () => {
    const markup = renderToStaticMarkup(<ProvisionQuote preview={{ ...preview, non_whitespace_covered: false }} title="Tam metin" />);
    expect(markup).toContain('&lt;script&gt;⚖️&lt;/script&gt;\nTürkçe.'); expect(markup).not.toContain('<script>'); expect(markup).toContain('[7, 20)');
    expect(markup).toContain('Kabul için sınırları'); expect(markup).toContain('p1, p2'); expect(markup).not.toContain('<details class="details" open');
  });
  it('keeps human handoff, source rights and graph publication distinct', () => {
    const markup = renderToStaticMarkup(<MappingSummary state={{ ...state, handoff_ready: true }} user={user} />);
    expect(markup).toContain('yayın veya kullanım izni değildir'); expect(markup).toContain('Yayımlanmadı'); expect(markup).toContain('İnceleme bekliyor'); expect(markup).toContain('&lt;img'); expect(markup).not.toContain('<img');
  });
  it('renders stale accepted mappings with unknown dates and reviewer references that are never links', () => {
    const markup = renderToStaticMarkup(<MappingRecord mapping={mapping} />);
    expect(markup).toContain('Yeniden inceleme gerekli'); expect(markup).toContain('önceki kaynak incelemesine bağlı'); expect(markup).toContain('Bilinmiyor');
    expect(markup).toContain('doğrulanmış graf kimliği sayılmaz'); expect(markup).toContain('javascript:untrusted()'); expect(markup).not.toContain('href="javascript'); expect(markup).not.toContain('<img');
  });
  it.each([['', '2'], ['-1', '3'], ['1.5', '3'], ['1e2', '103'], ['3', '3'], ['4', '3'], ['0', '20001'], ['9007199254740993', '9007199254740994']])('rejects invalid Unicode span %s..%s', (start, end) => {
    expect(() => spanCoordinates(start, end)).toThrow(); expect(matchesPreview(preview, sourceId, start, end)).toBe(false);
  });
  it('requires preview of the exact source and current coordinates before recording a proposal', () => {
    const draft = { ...EMPTY_PROPOSAL, candidate_id: candidate.id, label: candidate.label, start: '7', end: '20', rationale: 'Sınırlar kontrol edildi.' };
    expect(matchesPreview(preview, sourceId, '7', '20')).toBe(true); expect(matchesPreview(preview, 'f'.repeat(64), '7', '20')).toBe(false); expect(matchesPreview(preview, sourceId, '7', '21')).toBe(false);
    expect(() => proposalPayload(draft, state, null)).toThrow('önizleyin');
    const payload = proposalPayload(draft, state, preview);
    expect(payload).toEqual({ expected_revision: 2, expected_source_review_revision: 5, candidate_id: candidate.id, start: 7, end: 20, kind: 'article', label: 'MADDE 1', rationale: draft.rationale });
    expect(payload).not.toHaveProperty('text'); expect(payload).not.toHaveProperty('reviewer');
    expect(proposalPayload({ ...draft, candidate_id: null }, state, { ...preview, non_whitespace_covered: false }).candidate_id).toBeNull();
  });
  it('requires accepted source review, complete preview coverage and independent identity refs for acceptance', () => {
    expect(() => mappingReviewPayload(accepted, { ...state, source_review_ready: false }, preview)).toThrow('dört kaynak');
    expect(() => mappingReviewPayload(accepted, state, { ...preview, non_whitespace_covered: false })).toThrow('pasajlarla kapsanmalı');
    expect(() => mappingReviewPayload({ ...accepted, end: '21' }, state, preview)).toThrow('önizleyin');
    for (const field of ['instrument_ref', 'provision_ref', 'provision_version_ref'] as const) expect(() => mappingReviewPayload({ ...accepted, [field]: '' }, state, preview)).toThrow('ayrı ayrı');
    expect(() => mappingReviewPayload({ ...accepted, reference: '', sha256: '' }, state, preview)).toThrow('dayanak referansı');
    expect(() => mappingReviewPayload({ ...accepted, sha256: 'F'.repeat(64) }, state, preview)).toThrow('küçük harfli SHA256');
  });
  it('preserves unknown dates and text role instead of silently inferring current applicability', () => {
    const payload = mappingReviewPayload(accepted, state, preview);
    expect(payload.expected_revision).toBe(2); expect(payload.expected_source_review_revision).toBe(5);
    expect(payload.resolution).toMatchObject({ instrument_ref: accepted.instrument_ref, provision_ref: accepted.provision_ref, provision_version_ref: accepted.provision_version_ref, text_role: 'unknown', valid_from: null, valid_until: null });
    expect(payload).not.toHaveProperty('signature'); expect(payload).not.toHaveProperty('reviewed_at'); expect(payload).not.toHaveProperty('reviewer');
    expect(EMPTY_MAPPING_REVIEW.instrument_ref).toBe(''); expect(EMPTY_MAPPING_REVIEW.provision_version_ref).toBe('');
  });
  it('rejects impossible or reversed dates, while preserving explicit historical dates and quotation role', () => {
    expect(() => mappingReviewPayload({ ...accepted, valid_from: '2025-02-30' }, state, preview)).toThrow('geçerli YYYY');
    expect(() => mappingReviewPayload({ ...accepted, valid_from: '2025-03-01', valid_until: '2025-02-28' }, state, preview)).toThrow('başlangıçtan önce');
    const payload = mappingReviewPayload({ ...accepted, text_role: 'quoted_text', valid_from: '1924-04-20' }, state, preview);
    expect(payload.resolution?.valid_from).toBe('1924-04-20'); expect(payload.resolution?.valid_until).toBeNull(); expect(payload.resolution?.text_role).toBe('quoted_text');
  });
  it('permits reasoned rejection without claiming identities, dates, acceptance prerequisites or evidence', () => {
    const payload = mappingReviewPayload({ ...accepted, decision: 'rejected', reference: '', sha256: '', valid_from: 'bad' }, { ...state, source_review_ready: false }, null);
    expect(payload.resolution).toBeNull(); expect(payload.evidence_refs).toEqual([]); expect(payload.decision).toBe('rejected');
  });
  it('records open validity only after an independent matching source preview', () => {
    const support = { ...preview, span: { ...preview.span, start: 30, end: 50, text: 'Sentetik yürürlük dayanağı.' } };
    const draft: MappingReviewDraft = { ...accepted, valid_from: '1924-04-20', validity_end_mode: 'open_ended', checked_through: '2025-01-01', validity_evidence_start: '30', validity_evidence_end: '50' };
    expect(() => mappingReviewPayload(draft, state, preview)).toThrow('dayanağını');
    expect(() => mappingReviewPayload(draft, state, preview, preview)).toThrow('dayanağını');
    expect(() => mappingReviewPayload(draft, state, preview, { ...support, non_whitespace_covered: false })).toThrow('pasaj kapsamı');
    expect(() => mappingReviewPayload(draft, state, preview, { ...support, source_id: 'f'.repeat(64) })).toThrow('dayanağını');
    const payload = mappingReviewPayload(draft, state, preview, support);
    expect(payload.resolution).toMatchObject({ valid_from: '1924-04-20', valid_until: null, open_ended_validity: { checked_through: '2025-01-01', evidence_start: 30, evidence_end: 50 } });
    expect(payload.resolution).not.toHaveProperty('text');
    for (const changes of [{ valid_from: '' }, { checked_through: '' }, { checked_through: '1924-04-19' }, { checked_through: '9999-12-31' }]) expect(() => mappingReviewPayload({ ...draft, ...changes }, state, preview, support)).toThrow('denetim');
    expect(() => mappingReviewPayload({ ...draft, valid_until: '2025-02-01' }, state, preview, support)).toThrow('çelişiyor');
  });
  it('keeps unknown, closed and explicitly open records distinct when reopening review', () => {
    expect(mappingReviewDraft(mapping).validity_end_mode).toBe('unknown');
    expect(mappingReviewPayload(accepted, state, preview).resolution).not.toHaveProperty('open_ended_validity');
    const closed = { ...mapping, resolution: { ...snapshot.resolution, valid_from: '1924-04-20', valid_until: '1961-07-09' } };
    expect(mappingReviewDraft(closed).validity_end_mode).toBe('closed');
    const draft = { ...accepted, valid_from: '1924-04-20', valid_until: '1961-07-09', validity_end_mode: 'closed' as const };
    expect(mappingReviewPayload(draft, state, preview).resolution?.valid_until).toBe('1961-07-09');
    expect(() => mappingReviewPayload({ ...draft, valid_until: '' }, state, preview)).toThrow('Bilinen');
    expect(() => mappingReviewPayload({ ...draft, valid_until: draft.valid_from }, state, preview)).toThrow('aynı gün');
    const open = { ...mapping, resolution: { ...snapshot.resolution, valid_from: '1924-04-20', open_ended_validity: { checked_through: '2025-01-01', evidence_start: 30, evidence_end: 50 } } };
    expect(mappingReviewDraft(open)).toMatchObject({ validity_end_mode: 'open_ended', checked_through: '2025-01-01', validity_evidence_start: '30', validity_evidence_end: '50', valid_until: '' });
    const html = renderToStaticMarkup(<MappingRecord mapping={open} />);
    expect(html).toContain('Açık uçlu · dayanakla incelendi'); expect(html).toContain('Denetlenen son tarih (dahil)'); expect(html).toContain('yeniden inceleme gerekir'); expect(html).toContain('[30, 50)');
  });
  it('refreshes conflicts using both revisions without mutating input or resubmitting', async () => {
    const draft = structuredClone(accepted); const payload = mappingReviewPayload(draft, state, preview);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Conflict' }), { status: 409 })).mockResolvedValueOnce(new Response(JSON.stringify({ ...state, revision: 3, source_review_revision: 6 })));
    const result = await writeProvisionMapping(sourceId, mappingId, payload);
    expect(result.conflict).toBe(true); expect(result.state.source_review_revision).toBe(6); expect(draft).toEqual(accepted); expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/v1/public-sources/${sourceId}/provision-mappings/${mappingId}/review`);
    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toMatchObject({ expected_revision: 2, expected_source_review_revision: 5 });
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('X-CSRF-Token')).toBe('test-csrf'); expect(fetchMock.mock.calls[1][1]?.method).toBeUndefined();
  });
  it('sends manual proposals to the collection and never includes caller-controlled identities', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(state)));
    await writeProvisionMapping(sourceId, null, { expected_revision: 0, expected_source_review_revision: 1 });
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/v1/public-sources/${sourceId}/provision-mappings`);
    await expect(writeProvisionMapping(sourceId, '../review', {})).rejects.toThrow('kimliği geçersiz'); expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('fails closed on conflict refresh permission loss and expired sessions', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 409 })).mockResolvedValueOnce(new Response('{}', { status: 403 }));
    await expect(writeProvisionMapping(sourceId, mappingId, {})).rejects.toMatchObject({ status: 403 }); expect(fetchMock).toHaveBeenCalledTimes(2);
    const expired = vi.fn(); onUnauthorized(expired); fetchMock.mockResolvedValueOnce(new Response('{}', { status: 401 }));
    await expect(writeProvisionMapping(sourceId, mappingId, {})).rejects.toBeInstanceOf(ApiError); expect(expired).toHaveBeenCalledOnce(); expect(fetchMock).toHaveBeenCalledTimes(3);
  });
  it('downloads only an authenticated inert attachment and rejects inline or denied output', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{"signed":false}', { headers: { 'Content-Disposition': 'attachment; filename="dossier.json"', 'Content-Type': 'application/json' } }));
    const blob = await fetchMappingDossier(sourceId); expect(blob.type).toBe('application/octet-stream'); expect(await blob.text()).toContain('"signed":false');
    expect(fetchMock.mock.calls[0]).toEqual([`/api/v1/public-sources/${sourceId}/provision-mappings/export`, { credentials: 'same-origin', cache: 'no-store', signal: undefined }]);
    fetchMock.mockResolvedValueOnce(new Response('<html>')).mockResolvedValueOnce(new Response('{}', { status: 403 }));
    await expect(fetchMappingDossier(sourceId)).rejects.toThrow('Güvenli dosya eki'); await expect(fetchMappingDossier(sourceId)).rejects.toMatchObject({ status: 403 });
  });
  it('verifies preview coordinates, immutable source version and text digest before accepting a preview', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(preview)));
    const result = await fetchProvisionSpan(sourceId, preview.source_version_id, preview.text_sha256, '7', '20');
    expect(result).toEqual(preview); expect(fetchMock.mock.calls[0][0]).toBe(`/api/v1/public-sources/${sourceId}/provision-span?start=7&end=20`);
    for (const changed of [{ ...preview, source_id: 'e'.repeat(64) }, { ...preview, source_version_id: 'different' }, { ...preview, text_sha256: 'e'.repeat(64) }, { ...preview, span: { ...preview.span, end: 21 } }]) {
      fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(changed)));
      await expect(fetchProvisionSpan(sourceId, preview.source_version_id, preview.text_sha256, '7', '20')).rejects.toMatchObject({ status: 409 });
    }
  });
  it('forwards cancellation without creating a background retry', async () => {
    const controller = new AbortController(); controller.abort(); fetchMock.mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'));
    await expect(writeProvisionMapping(sourceId, mappingId, {}, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).toHaveBeenCalledOnce(); expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });
});
