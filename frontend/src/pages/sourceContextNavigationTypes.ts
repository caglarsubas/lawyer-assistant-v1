import { hasExactKeys as keys } from '../workbench/privateObservationValidation';
export const navigationIdentifier = (value: unknown): value is string => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(value);
export const navigationContextId = (value: unknown): value is string => typeof value === 'string' && /^sac-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value);
export const navigationReviewId = (value: unknown): value is string => typeof value === 'string' && /^sar-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value);
export const navigationReturnToken = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
export type SourceTarget = { kind: 'selected'; matter_id: string; analysis_id: string; context_id: string; review_id?: string; return_token?: string; prepare?: 'renewal' | 'review' };
export type SourceSelection = SourceTarget | { kind: 'none' | 'invalid' };
export function sourceNavigationSelection(pathname: string, params: URLSearchParams): SourceSelection {
  const tabs = params.getAll('tab');
  const returnIntent = params.has('return') && ['matters', 'workspaces'].includes(pathname.split('/')[1]);
  if (!params.has('analysis') && !params.has('source_context') && !params.has('review') && !params.has('prepare') && !returnIntent && !tabs.includes('source-review')) return { kind: 'none' };
  const parts = pathname.split('/'); let matter: string;
  try { matter = decodeURIComponent(parts[2] || ''); } catch { return { kind: 'invalid' }; }
  const analysis = params.getAll('analysis'); const context = params.getAll('source_context'); const review = params.getAll('review'); const token = params.getAll('return'); const prepare = params.getAll('prepare');
  if (parts.length !== 3 || !['matters', 'workspaces'].includes(parts[1]) || tabs.length !== 1 || tabs[0] !== 'source-review'
    || [...params.keys()].some(key => !['tab', 'analysis', 'source_context', 'review', 'return', 'prepare'].includes(key)) || analysis.length !== 1 || context.length !== 1
    || prepare.length > 1 || prepare.length === 1 && (!['renewal', 'review'].includes(prepare[0]) || token.length !== 1 || review.length !== 0)
    || token.length > 1 || (token.length === 1 && !navigationReturnToken(token[0]))
    || review.length > 1 || (review.length === 1 && !navigationReviewId(review[0]))
    || !navigationIdentifier(matter) || !navigationIdentifier(analysis[0]) || !navigationContextId(context[0])) return { kind: 'invalid' };
  return { kind: 'selected', matter_id: matter, analysis_id: analysis[0], context_id: context[0], ...(review.length ? { review_id: review[0] } : {}), ...(token.length ? { return_token: token[0] } : {}), ...(prepare.length ? { prepare: prepare[0] as 'renewal' | 'review' } : {}) };
}
export function sourceContextHref(matter: string, analysis: string, context: string, review?: string, token?: string): string | null {
  return navigationIdentifier(matter) && navigationIdentifier(analysis) && navigationContextId(context) && (review === undefined || navigationReviewId(review)) && (token === undefined || navigationReturnToken(token))
    ? `#/matters/${encodeURIComponent(matter)}?${new URLSearchParams({ tab: 'source-review', analysis, source_context: context, ...(review ? { review } : {}), ...(token ? { return: token } : {}) })}` : null;
}
export type NavigationMetadata = {
  recipe: 'private-source-context-navigation-v1'; matter_id: string; analysis_id: string; context_id: string; observed_at: string;
  analysis: { id: string; current_version_id: string | null; revision: number };
  context: { id: string; version_id: string | null; manifest_sha256: string | null; recorded_at: string };
  admission: { context_state: 'complete' | 'pending' | 'unavailable'; review_state: 'complete' | 'pending' | 'unavailable' | 'unknown' | 'not_recorded' };
  historical_review: { state: 'unknown' | 'unreviewed' | 'changes_requested' | 'reviewed_conditional'; id: string | null; recorded_at: string | null };
  version_relation: 'same' | 'different' | 'unknown'; integrity: 'verified' | 'unavailable'; tools_available: boolean;
  source_verification: 'not_checked'; legal_readiness: 'not_established'; qualification_granted: false;
};
const stamp = (value: unknown) => typeof value === 'string' && value.length <= 40 && Number.isFinite(Date.parse(value));
const sha = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export function verifyNavigation(value: NavigationMetadata, target: SourceTarget) {
  const fail = () => { throw new Error('Seçilen kaynak bağlamının tam gezinme bağı doğrulanamadı.'); };
  if (!value || !keys(value, ['recipe', 'matter_id', 'analysis_id', 'context_id', 'observed_at', 'analysis', 'context', 'admission', 'historical_review', 'version_relation', 'integrity', 'tools_available', 'source_verification', 'legal_readiness', 'qualification_granted'])
    || value.recipe !== 'private-source-context-navigation-v1' || value.matter_id !== target.matter_id || value.analysis_id !== target.analysis_id || value.context_id !== target.context_id
    || !stamp(value.observed_at) || value.source_verification !== 'not_checked' || value.legal_readiness !== 'not_established' || value.qualification_granted !== false) fail();
  const a = value.analysis, c = value.context, p = value.admission, r = value.historical_review;
  if (!a || !c || !p || !r || !keys(a, ['id', 'current_version_id', 'revision']) || a.id !== target.analysis_id || !Number.isInteger(a.revision) || a.revision < 1
    || (a.current_version_id !== null && !navigationIdentifier(a.current_version_id)) || !keys(c, ['id', 'version_id', 'manifest_sha256', 'recorded_at']) || c.id !== target.context_id
    || (c.version_id !== null && !navigationIdentifier(c.version_id)) || (c.manifest_sha256 !== null && !sha(c.manifest_sha256)) || !stamp(c.recorded_at)
    || !keys(p, ['context_state', 'review_state']) || !['complete', 'pending', 'unavailable'].includes(p.context_state)
    || !['complete', 'pending', 'unavailable', 'unknown', 'not_recorded'].includes(p.review_state)
    || !keys(r, ['state', 'id', 'recorded_at']) || !['unknown', 'unreviewed', 'changes_requested', 'reviewed_conditional'].includes(r.state)
    || (r.id !== null && !/^sar-[a-f0-9]{20}-[a-f0-9]{32}$/.test(r.id)) || (r.recorded_at !== null && !stamp(r.recorded_at))
    || !['same', 'different', 'unknown'].includes(value.version_relation) || !['verified', 'unavailable'].includes(value.integrity) || typeof value.tools_available !== 'boolean') fail();
  if (value.integrity === 'verified' && (!sha(c.manifest_sha256) || !navigationIdentifier(c.version_id) || p.context_state === 'unavailable')) fail();
  if (value.integrity === 'unavailable' && (c.manifest_sha256 !== null || c.version_id !== null || value.tools_available)) fail();
  if (value.tools_available && (!navigationIdentifier(a.current_version_id) || value.integrity !== 'verified')) fail();
  if (value.version_relation !== (a.current_version_id && c.version_id ? (a.current_version_id === c.version_id ? 'same' : 'different') : 'unknown')) fail();
}
