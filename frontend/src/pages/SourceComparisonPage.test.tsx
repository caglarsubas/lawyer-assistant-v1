import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { PublicSourcePassages, User } from '../types';
import SourceComparisonPage, { ComparisonResult } from './SourceComparisonPage';
import { commonEdges, comparisonHash, fetchSourceComparison, type ComparisonSelection, type SourceComparison } from './sourceComparison';

async function selection(id: string, text: string): Promise<ComparisonSelection> {
  const passage = { id: 'p1', text, start: 10, end: 10 + Array.from(text).length, text_sha256: await comparisonHash(text), locator: 'synthetic passage' };
  const source: PublicSourcePassages = { source_id: id.repeat(64), source_version_id: 'synthetic-version', raw_sha256: id.repeat(64), text_sha256: await comparisonHash(`whole-${text}`), offset_unit: 'unicode_code_points', integrity_scope: 'all_artifacts_verified', items: [passage], total: 1, next_offset: null };
  return { source, passage };
}
const left = await selection('a', '😀İABC\r\n<script>bad</script>ş'), right = await selection('b', '😀I\u0307ABC\n<script>bad</script>ş');
async function window(value: ComparisonSelection, offset: number) {
  const text = Array.from(value.passage.text).slice(offset, offset + 2000).join('');
  const end = value.passage.start + offset + Array.from(text).length;
  return { source_id: value.source.source_id, source_version_id: value.source.source_version_id, title: '<script>source</script>', source_url: 'https://official.example/no-fetch', domain: 'contracts', raw_media_type: 'text/html',
    artifacts: Object.fromEntries(['raw.bin', 'text.txt', 'source.json', 'locators.json'].map(name => [name, { sha256: name === 'raw.bin' ? value.source.raw_sha256 : name === 'text.txt' ? value.source.text_sha256 : 'c'.repeat(64), bytes: 100 }])),
    source_text_code_points: 300, passage_id: value.passage.id, locator: value.passage.locator, passage_start: value.passage.start, passage_end: value.passage.end, passage_sha256: value.passage.text_sha256,
    start: value.passage.start + offset, end, text, window_sha256: await comparisonHash(text), next_offset: end < value.passage.end ? end - value.passage.start : null, integrity_scope: 'all_artifacts_verified' };
}
async function envelope(change: (data: SourceComparison) => void = () => {}, offset = 0, otherOffset = 0) {
  const a = await window(left, offset), b = await window(right, otherOffset), edges = commonEdges(a.text, b.text);
  const data: SourceComparison = { schema_version: 'public-source-comparison-v1', left: a, right: b, offset_unit: 'unicode_code_points', window_limit: 2000, raw_bytes_equal: false, extracted_text_equal: false,
    difference: { scope: 'selected_windows_only', equal: a.text === b.text, common_prefix_code_points: edges.prefix, common_suffix_code_points: edges.suffix, left_range: edges.left as [number, number], right_range: edges.right as [number, number], range_unit: 'window_relative_unicode_code_points', method: 'literal_common_edges_v1' },
    normalization: 'none', legal_identity_status: 'unresolved', legal_version_status: 'unresolved', independent_originals_verified: false, current_law_verified: false, human_review_recorded: false, limitations: ['synthetic mechanical record'] };
  change(data);
  const evidence_json = JSON.stringify(data), evidence_sha256 = await comparisonHash(evidence_json);
  return { receipt: data, evidence_json, evidence_sha256 };
}

describe('bounded source representation comparison', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); });
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
  it('requests only exact local identifiers with fresh same-origin access and verifies Unicode evidence', async () => {
    const fixture = await envelope(); fetchMock.mockResolvedValue(new Response(JSON.stringify(fixture)));
    const result = await fetchSourceComparison(left, right);
    expect(result).toEqual(fixture); expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0]; expect(String(url)).toContain(`/api/v1/public-sources/${left.source.source_id}/comparison?other_source_id=${right.source.source_id}&passage_id=p1&other_passage_id=p1&offset=0&other_offset=0&limit=2000`);
    expect(init?.cache).toBe('no-store'); expect(init?.credentials).toBe('same-origin'); expect(init?.body).toBeUndefined();
    expect(result.receipt.difference.left_range[0]).toBe(1); expect(result.receipt.left.text).toContain('😀İ');
  });
  it('honors independent offsets without inferring correspondence', async () => {
    const fixture = await envelope(() => {}, 1, 2); fetchMock.mockResolvedValue(new Response(JSON.stringify(fixture)));
    expect((await fetchSourceComparison(left, right, 1, 2)).receipt.left.start).toBe(11);
    expect(fixture.receipt.right.start).toBe(12);
  });
  it.each(['identity', 'version', 'passage', 'text', 'window_hash', 'artifact', 'coordinates', 'scope', 'edges', 'normalized', 'review', 'independent', 'effect', 'raw_equal', 'text_equal', 'next', 'limit'])('rejects digest-valid but mismatched evidence: %s', async kind => {
    const fixture = await envelope(data => {
      switch (kind) {
        case 'identity': data.right.source_id = 'f'.repeat(64); break;
        case 'version': data.left.source_version_id = 'new'; break;
        case 'passage': data.right.passage_id = 'p2'; break;
        case 'text': data.right.text = 'rewritten'; break;
        case 'window_hash': data.left.window_sha256 = 'f'.repeat(64); break;
        case 'artifact': data.right.artifacts['raw.bin'].sha256 = 'f'.repeat(64); break;
        case 'coordinates': data.left.end++; break;
        case 'scope': data.left.integrity_scope = 'manifest_only'; break;
        case 'edges': data.difference.left_range = [0, 20000]; break;
        case 'normalized': data.normalization = 'corrected' as 'none'; break;
        case 'review': data.human_review_recorded = true as false; break;
        case 'independent': data.independent_originals_verified = true as false; break;
        case 'effect': data.current_law_verified = true as false; break;
        case 'raw_equal': data.raw_bytes_equal = true; break;
        case 'text_equal': data.extracted_text_equal = true; break;
        case 'next': data.right.next_offset = 1; break;
        case 'limit': data.window_limit = 20000; break;
      }
    });
    fetchMock.mockResolvedValue(new Response(JSON.stringify(fixture)));
    await expect(fetchSourceComparison(left, right)).rejects.toThrow('eşleşmiyor'); expect(fetchMock).toHaveBeenCalledOnce();
  });
  it('rejects altered or malformed evidence before display', async () => {
    const fixture = await envelope(); fixture.evidence_json += ' ';
    fetchMock.mockResolvedValue(new Response(JSON.stringify(fixture)));
    await expect(fetchSourceComparison(left, right)).rejects.toThrow('içerik özeti');
    const evidence_json = 'not JSON'; fetchMock.mockResolvedValue(new Response(JSON.stringify({ evidence_json, evidence_sha256: await comparisonHash(evidence_json) })));
    await expect(fetchSourceComparison(left, right)).rejects.toThrow('okunamadı');
  });
  it.each([-1, 0.5, 20000, Number.NaN])('rejects invalid offsets before request: %s', async offset => {
    await expect(fetchSourceComparison(left, right, offset)).rejects.toThrow('seçimi geçersiz'); expect(fetchMock).not.toHaveBeenCalled();
  });
  it('rejects same-source or absent passage selections before requesting', async () => {
    await expect(fetchSourceComparison(left, left)).rejects.toThrow('farklı');
    await expect(fetchSourceComparison({ ...left, passage: { ...left.passage, id: 'missing' } }, right)).rejects.toThrow('seçimi geçersiz'); expect(fetchMock).not.toHaveBeenCalled();
  });
  it.each([401, 403, 409, 422])('withholds denied/corrupt sources without retry: %i', async status => {
    fetchMock.mockResolvedValue(new Response('{}', { status })); await expect(fetchSourceComparison(left, right)).rejects.toMatchObject({ status }); expect(fetchMock).toHaveBeenCalledOnce();
  });
  it('cancels after a late response before displaying or exporting it', async () => {
    const controller = new AbortController(), fixture = await envelope();
    fetchMock.mockImplementation(async () => { controller.abort(); return new Response(JSON.stringify(fixture)); });
    await expect(fetchSourceComparison(left, right, 0, 0, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });
  it('bounds transfer time and clears late evidence', async () => {
    vi.useFakeTimers(); const fixture = await envelope(); let finish: ((response: Response) => void) | undefined;
    fetchMock.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const pending = fetchSourceComparison(left, right).catch(cause => cause);
    await vi.advanceTimersByTimeAsync(30000); expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    finish!(new Response(JSON.stringify(fixture))); expect(await pending).toMatchObject({ name: 'AbortError' }); expect(vi.getTimerCount()).toBe(0);
  });
  it('escapes source markup, highlights code-point ranges and leaves legal identity unresolved', async () => {
    const markup = renderToStaticMarkup(<ComparisonResult value={await envelope()} />);
    expect(markup).toContain('&lt;script&gt;source&lt;/script&gt;'); expect(markup).toContain('&lt;script&gt;bad&lt;/script&gt;'); expect(markup).toContain('<mark>İ');
    expect(markup).toContain('henüz çözümlenmedi'); expect(markup).toContain('inceleme kabulü veya bağımsızlık kararı kaydetmez');
    for (const unsafe of ['<script>', '<iframe', '<object', 'href="https:', '<input', '<form']) expect(markup).not.toContain(unsafe);
  });
  it('gates action permissions before loading comparison state', () => {
    const user = { id: 'reviewer', role: 'curator', permissions: [] } as unknown as User;
    expect(renderToStaticMarkup(<SourceComparisonPage sourceId={left.source.source_id} user={user} />)).toContain('küratör yetkisi');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
