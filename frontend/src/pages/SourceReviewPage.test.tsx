import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ApiError, onUnauthorized, request, setCsrfToken } from '../api';
import type { PublicSourceOriginalText, PublicSourcePassages, SourceReviewState, User } from '../types';
import SourceReviewPage, { assessmentPayload, canReviewSource, EMPTY_ASSESSMENT, fetchSourceAttachment, fetchOriginalSourceText, SourceOriginalView, SourcePassageList, SourceReviewSummary, sourceReviewPath, writeSourceReview, type AssessmentDraft } from './SourceReviewPage';

const sourceId = 'a'.repeat(64);
const user: User = { id: 'reviewer-1', name: 'İnceleyen', role: 'curator', firm_id: 'firm-1' };
const state: SourceReviewState = {
  source: { id: sourceId, title: '<img src=x onerror=alert(1)>', source_url: 'javascript:alert(1)', source_version_id: 'historical-enacted', domain: 'contracts', acquired_at: null, rights_status: 'rights_pending', review_status: 'legal_review_pending', passage_count: 21, publication_status: 'staged', dates: { published_on: null, effective_from: null, effective_until: null }, artifacts: { 'raw.bin': { sha256: sourceId, bytes: 400 } }, integrity_scope: 'all_artifacts_verified', limitations: ['Tarihsel metin.'], injection_risk_hints: [], review_evidence: { rights_supplied: false, identity_supplied: false, trust: 'operator_supplied_unverified' } },
  revision: 4, assigned_to: { id: user.id, name: user.name }, assessments: [], history: [], history_truncated: false, handoff_ready: false, publication_eligible: false, limitations: [],
};
const passages: PublicSourcePassages = { source_id: sourceId, source_version_id: 'historical-enacted', raw_sha256: sourceId, text_sha256: 'b'.repeat(64), offset_unit: 'unicode_code_points', items: [{ id: 'p01', locator: '<a href="https://example.org">konum</a>', start: 7, end: 38, text_sha256: 'c'.repeat(64), text: '<script>alert("source")</script>\nTam metin.' }], total: 21, next_offset: 20, integrity_scope: 'all_artifacts_verified' };
const accepted: AssessmentDraft = { ...EMPTY_ASSESSMENT, decision: 'accepted', rationale: 'Dayanak incelendi.', reference: 'yerel/kayit.pdf', sha256: 'd'.repeat(64), permitted_uses: ['storage'] };

describe('source review evidence and permissions', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); onUnauthorized(); setCsrfToken('test-csrf'); });
  afterEach(() => { vi.unstubAllGlobals(); onUnauthorized(); setCsrfToken(''); });

  it('renders role denial without source content, forms or fetching', () => {
    expect(canReviewSource(user)).toBe(true);
    expect(canReviewSource({ ...user, role: 'admin' })).toBe(true);
    const markup = renderToStaticMarkup(<SourceReviewPage sourceId={sourceId} user={{ ...user, role: 'lawyer' }} />);
    expect(markup).toContain('İnceleme yetkisi gerekli');
    expect(markup).not.toContain('<form');
    expect(markup).not.toContain('Pasaj SHA256');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(['../../auth', 'a'.repeat(63), 'A'.repeat(64), `${sourceId}/review`, `${sourceId}?export=1`])('rejects non-package route identifiers: %s', id => {
    expect(() => sourceReviewPath(id)).toThrow('Kaynak kimliği geçersiz');
    expect(renderToStaticMarkup(<SourceReviewPage sourceId={id} user={user} />)).toContain('Kaynak kimliği geçersiz');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('renders source passages and locators as exact escaped plain text, never HTML or links', () => {
    const markup = renderToStaticMarkup(<SourcePassageList data={passages} offset={0} selected={['p01']} canSelect onSelect={() => undefined} onPage={() => undefined} />);
    expect(markup).toContain('&lt;script&gt;alert(&quot;source&quot;)&lt;/script&gt;\nTam metin.');
    expect(markup).toContain('&lt;a href=&quot;https://example.org&quot;&gt;');
    expect(markup).not.toContain('<script>'); expect(markup).not.toContain('href="https://');
    expect(markup).toContain('[7, 38)'); expect(markup).toContain('checked=""');
    expect(markup).toContain('disabled="">Önceki');
    expect(markup).not.toContain('<details class="details" open');
  });

  it('does not show extraction selection controls to a reader or permit paging past the last page', () => {
    const markup = renderToStaticMarkup(<SourcePassageList data={{ ...passages, next_offset: null }} offset={20} selected={[]} canSelect={false} onSelect={() => undefined} onPage={() => undefined} />);
    expect(markup).not.toContain('checkbox'); expect(markup).toContain('disabled="">Sonraki'); expect(markup).toContain('21–21 / 21 pasaj');
  });

  it('keeps completed dossier, acquisition rights and publication separate; supporting references are not executable', () => {
    const event = { id: 'event-1', revision: 2, event_type: 'assessment' as const, reviewer: { id: user.id, name: user.name }, created_at: '2026-10-04T08:00:00Z', rationale: '<iframe src=x></iframe>', category: 'legal' as const, decision: 'accepted' as const, evidence_refs: [{ reference: 'javascript:alert(1)', sha256: sourceId }], passage_ids: [], permitted_uses: [] };
    const markup = renderToStaticMarkup(<SourceReviewSummary state={{ ...state, handoff_ready: true, assessments: [event] }} />);
    expect(markup).toContain('yayın veya kullanım izni değildir');
    expect(markup).toContain('Kullanım hakları inceleme bekliyor');
    expect(markup).toContain('Hukuki inceleme bekliyor');
    expect(markup).toContain('Kabul edildi'); expect(markup).toContain('&lt;iframe src=x&gt;');
    expect(markup).not.toContain('<iframe'); expect(markup).not.toContain('href="javascript:');
    expect(markup).not.toContain('<details class="details" open');
  });

  it('requires bound evidence, rights scope and extraction passages before acceptance', () => {
    expect(() => assessmentPayload({ ...accepted, reference: '', sha256: '' }, 4)).toThrow('dayanak referansı');
    expect(() => assessmentPayload({ ...accepted, sha256: 'D'.repeat(64) }, 4)).toThrow('küçük harfli SHA256');
    expect(() => assessmentPayload({ ...accepted, permitted_uses: [] }, 4)).toThrow('izin verilen kullanım');
    expect(() => assessmentPayload({ ...accepted, category: 'extraction', passage_ids: [] }, 4)).toThrow('pasajları seçin');
    expect(() => assessmentPayload({ ...accepted, rationale: 'x' }, 4)).toThrow('3–4000');
    expect(() => assessmentPayload({ ...accepted, passage_ids: ['p1', 'p1'] }, 4)).toThrow('100 farklı');
    const payload = assessmentPayload({ ...accepted, category: 'extraction', passage_ids: ['p01'] }, 4);
    expect(payload).toEqual({ expected_revision: 4, category: 'extraction', decision: 'accepted', rationale: accepted.rationale, evidence_refs: [{ reference: accepted.reference, sha256: accepted.sha256 }], passage_ids: ['p01'], permitted_uses: [] });
    expect(payload).not.toHaveProperty('reviewer'); expect(payload).not.toHaveProperty('created_at');
  });

  it('allows reasoned changes or rejection without claiming evidence or permitted uses', () => {
    expect(assessmentPayload({ ...EMPTY_ASSESSMENT, category: 'legal', rationale: 'Eksik kaynak sürümü.', permitted_uses: ['export'], passage_ids: ['p01'] }, 0)).toEqual({ expected_revision: 0, category: 'legal', decision: 'needs_changes', rationale: 'Eksik kaynak sürümü.', evidence_refs: [], passage_ids: [], permitted_uses: [] });
  });

  it('refreshes after a revision conflict without mutating the draft or repeating a write', async () => {
    const draft = structuredClone(accepted); const payload = assessmentPayload(draft, 4);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Revision conflict' }), { status: 409 })).mockResolvedValueOnce(new Response(JSON.stringify({ ...state, revision: 5 })));
    const result = await writeSourceReview(sourceId, 'assessments', payload);
    expect(result.conflict).toBe(true); expect(result.state.revision).toBe(5); expect(draft).toEqual(accepted);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/v1/public-sources/${sourceId}/review/assessments`);
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST'); expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('X-CSRF-Token')).toBe('test-csrf');
    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string).expected_revision).toBe(4);
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/v1/public-sources/${sourceId}/review`);
    expect(fetchMock.mock.calls[1][1]?.method).toBeUndefined();
  });

  it('fails a conflict refresh closed if permission changed and never resubmits', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 409 })).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Revoked' }), { status: 403 }));
    await expect(writeSourceReview(sourceId, 'assignment', { expected_revision: 4, action: 'claim', rationale: 'İnceleme.' })).rejects.toMatchObject({ status: 403 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('propagates expired sessions from review writes without attempting claim or reassignment', async () => {
    const expired = vi.fn(); onUnauthorized(expired);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Expired' }), { status: 401 }));
    await expect(writeSourceReview(sourceId, 'assessments', assessmentPayload(accepted, 4))).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledOnce(); expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('keeps confidential source review writes out of portfolio refresh events while preserving workspace refresh', async () => {
    const dispatchEvent = vi.fn(); vi.stubGlobal('window', { dispatchEvent });
    fetchMock.mockImplementation(async () => new Response('{}'));
    await request(`/public-sources/${sourceId}/review/assignment`, { method: 'POST', body: '{}' });
    await request(`/public-sources/${sourceId}/review/assessments`, { method: 'POST', body: '{}' });
    expect(dispatchEvent).not.toHaveBeenCalled();
    await request('/workspaces/workspace-1/comments', { method: 'POST', body: '{}' });
    expect(dispatchEvent).toHaveBeenCalledOnce();
    expect(dispatchEvent.mock.calls[0][0].type).toBe('portfolio-updated');
  });

  it('downloads only authenticated local attachments with opaque bytes, never rendered HTML', async () => {
    fetchMock.mockResolvedValue(new Response('<script>untrusted</script>', { headers: { 'Content-Disposition': 'attachment; filename="unsafe.html"', 'Content-Type': 'text/html' } }));
    const blob = await fetchSourceAttachment(sourceId, 'original');
    expect(blob.type).toBe('application/octet-stream'); expect(await blob.text()).toBe('<script>untrusted</script>');
    expect(fetchMock.mock.calls[0]).toEqual([`/api/v1/public-sources/${sourceId}/original`, { credentials: 'same-origin', signal: undefined, cache: 'no-store' }]);
    fetchMock.mockResolvedValue(new Response('{}', { headers: { 'Content-Disposition': 'attachment; filename="dossier.json"' } }));
    await fetchSourceAttachment(sourceId, 'export'); expect(fetchMock.mock.calls[1][0]).toBe(`/api/v1/public-sources/${sourceId}/review/export`);
  });

  it('refuses inline or failed downloads and forwards cancellation', async () => {
    fetchMock.mockResolvedValueOnce(new Response('<html>inline</html>')).mockResolvedValueOnce(new Response('{}', { status: 403 }));
    await expect(fetchSourceAttachment(sourceId, 'original')).rejects.toThrow('Güvenli dosya eki');
    await expect(fetchSourceAttachment(sourceId, 'export')).rejects.toMatchObject({ status: 403 });
    const controller = new AbortController(); controller.abort();
    fetchMock.mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'));
    await expect(fetchSourceAttachment(sourceId, 'original', controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock.mock.calls[2][1]?.signal).toBe(controller.signal);
  });
});

const originalText = '  İ😀 &amp; <script>fetch("https://untrusted.invalid")</script>\r\n';
const original: PublicSourceOriginalText = { source_id: sourceId, source_version_id: passages.source_version_id, passage_id: 'p01', raw_sha256: passages.raw_sha256, text_sha256: passages.text_sha256, decoded_original_sha256: 'd'.repeat(64), window_sha256: 'e'.repeat(64), encoding: 'utf-8', offset_unit: 'unicode_code_points_excluding_initial_utf8_bom', range_start: 40, range_end: 40 + Array.from(originalText).length, start: 40, end: 40 + Array.from(originalText).length, next_offset: null, text: originalText, integrity_scope: 'all_artifacts_verified', locator_coordinate_status: 'consistent_not_fidelity_reviewed', extraction_fidelity_verified: false };

describe('inert original-source inspection', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); onUnauthorized(); });
  afterEach(() => { vi.unstubAllGlobals(); onUnauthorized(); });

  it('requests only a selected source passage and bounded window; passes cancellation', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(original), { status: 200 }));
    const controller = new AbortController();
    expect(await fetchOriginalSourceText(passages, 'p01', 0, controller.signal)).toEqual(original);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/v1/public-sources/${sourceId}/original-text?passage_id=p01&offset=0&limit=12000`);
    expect(options?.signal).toBe(controller.signal);
    expect(options?.credentials).toBe('same-origin');
    expect(options?.body).toBeUndefined();
  });

  it.each(['../private', 'unknown', 'p01?secret=1'])('rejects a caller-supplied passage before any request: %s', async id => {
    await expect(fetchOriginalSourceText(passages, id, 0)).rejects.toThrow('konumu geçersiz');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([-1, 1.5, 1048577, Number.NaN])('rejects out-of-budget offsets before requesting: %s', async offset => {
    await expect(fetchOriginalSourceText(passages, 'p01', offset)).rejects.toThrow('konumu geçersiz');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    { source_id: 'f'.repeat(64) }, { source_version_id: 'other-version' }, { passage_id: 'other-passage' },
    { raw_sha256: 'f'.repeat(64) }, { text_sha256: 'f'.repeat(64) }, { extraction_fidelity_verified: true },
    { integrity_scope: 'manifest_only' }, { offset_unit: 'utf16' }, { locator_coordinate_status: 'reviewed' },
    { start: 39 }, { end: original.end + 1 }, { range_end: 1048577 }, { next_offset: 0 },
    { text: originalText + 'altered' }, { text: null }, { window_sha256: 'broken' }, { decoded_original_sha256: 'broken' },
  ])('withholds original content with a mismatched identity/window: %j', async change => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ...original, ...change }), { status: 200 }));
    await expect(fetchOriginalSourceText(passages, 'p01', 0)).rejects.toThrow('eşleşmiyor');
  });

  it('propagates authorization denial and unavailable-locator errors without a fallback request', async () => {
    for (const status of [401, 403, 409, 422]) {
      fetchMock.mockReset();
      fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Özgün kaynak gösterilemiyor' }), { status }));
      await expect(fetchOriginalSourceText(passages, 'p01', 0)).rejects.toMatchObject({ status });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    }
  });

  it('escapes original script, entities and URLs without executing, linking or recording acceptance', () => {
    const markup = renderToStaticMarkup(<SourceOriginalView data={original} onPage={() => undefined} onClose={() => undefined} />);
    expect(markup).toContain('&lt;script&gt;fetch(&quot;https://untrusted.invalid&quot;)&lt;/script&gt;');
    expect(markup).toContain('&amp;amp;');
    expect(markup).not.toContain('<script>'); expect(markup).not.toContain('<iframe'); expect(markup).not.toContain('href="https://');
    expect(markup).toContain('insan incelemesi gerektirir');
    expect(markup).not.toContain('checkbox'); expect(markup).not.toContain('Kabul edildi');
    expect(markup).toContain('disabled="">Önceki kaynak aralığı');
    expect(markup).toContain('disabled="">Sonraki kaynak aralığı');
  });

  it('opens a source comparison only for a recognized locator and keeps extraction selection separate', () => {
    const mapped = { ...passages, items: [{ ...passages.items[0], locator: 'HTML source line 2, column 4; decoded code points [40,90)' }] };
    const markup = renderToStaticMarkup(<SourcePassageList data={mapped} offset={0} selected={[]} canSelect={false} onSelect={() => undefined} onPage={() => undefined} onOriginal={() => undefined} original={{ passageId: 'p01', offset: 0, state: { status: 'loaded', value: original } }} />);
    expect(markup).toContain('Özgün kaynak koduyla karşılaştır');
    expect(markup).toContain('source-comparison'); expect(markup).not.toContain('checkbox');
    expect(markup).not.toContain('<script>');
    const unsupported = renderToStaticMarkup(<SourcePassageList data={passages} offset={0} selected={[]} canSelect={false} onSelect={() => undefined} onPage={() => undefined} onOriginal={() => undefined} />);
    expect(unsupported).not.toContain('Özgün kaynak koduyla karşılaştır');
  });

  it('does not present old original content under a different selected passage', () => {
    const markup = renderToStaticMarkup(<SourcePassageList data={passages} offset={0} selected={[]} canSelect={false} onSelect={() => undefined} onPage={() => undefined} original={{ passageId: 'not-p01', offset: 0, state: { status: 'loaded', value: original } }} />);
    expect(markup).not.toContain('Özgün HTML kaynak kodu');
    expect(markup).not.toContain(original.window_sha256);
  });
});
