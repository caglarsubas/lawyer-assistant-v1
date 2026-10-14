export const READINESS_STATES = {
  pending: 'Son izin kontrolü bekliyor', unavailable: 'Özel bağlar doğrulanamadı', needs_renewal: 'Yeni bağlam gerekli',
  changes_requested: 'Değişiklik istendi', awaiting_review: 'Bağımsız karar bekliyor', inspection_required: 'Güncel kaynak kontrolü gerekli',
} as const;
export const READINESS_REASONS = {
  context_admission_pending: 'Bağlamın son izin kontrolü tamamlanmadı.', review_admission_pending: 'Kararın son izin kontrolü tamamlanmadı.',
  analysis_version_changed: 'Analizin son sürümü değişti.', analysis_content_changed: 'Sabit analiz içeriği değişti.',
  analysis_review_head_changed: 'Özel analizin inceleme sırası değişti.', private_recipe_changed: 'Özel inceleme kuralları değişti.',
  private_dependency_unavailable: 'Seçili özel dayanak artık erişilebilir değil.', private_dependency_changed: 'Seçili özel dayanak değişti.',
  contradiction_basis_changed: 'Bağlı çelişki kayıtları değişti.', source_review_basis_changed: 'Kaynak kararının kayıt bağı veya ölçütleri değişti.',
  reviewer_access_changed: 'Önceki incelemecinin güncel bağımsız yetkisi doğrulanamadı.', research_basis_changed: 'Araştırma kaydının tam dayanağı değişti.',
  research_basis_unavailable: 'Araştırma kaydı artık doğrulanamıyor.', parent_basis_changed_or_unavailable: 'Önceki yenileme bağlamının kayıt veya karar bağı değişti ya da doğrulanamadı.',
  observation_budget_exhausted: 'Sınırlı gözlem bütçesi doldu; tam kontrol ayrıca gerekli.', private_basis_unavailable: 'Özel kayıt bağı doğrulanamadı.',
  record_integrity_unavailable: 'Saklanan kaydın bütünlüğü doğrulanamadı.',
} as const;
export type ReadinessItem = {
  id: string; recorded_at: string; state: keyof typeof READINESS_STATES;
  version_id?: string; product_id?: string; manifest_sha256?: string;
  historical_review: { state: 'unknown' | 'unreviewed' | 'changes_requested' | 'reviewed_conditional'; id: string | null; recorded_at: string | null };
  private_observation: { state: 'unknown' | 'unchanged' | 'changed'; reasons: (keyof typeof READINESS_REASONS)[] };
  source_verification: 'not_checked'; legal_readiness: 'not_established';
};
export type ReadinessPage = {
  recipe: 'private-source-review-readiness-v1'; matter_id: string; analysis_id: string; observed_at: string;
  items: ReadinessItem[]; coverage: { scope: 'authorized_analysis_window_only'; scanned_count: number; returned_count: number;
    has_more: boolean; pagination_limit_reached: boolean; next_offset: number | null; priority_scope: 'current_window_only'; total_count: null; source_verification: 'not_checked' };
  legal_readiness: 'not_established'; qualification_granted: false;
};
export type ReadinessFilters = { bucket: 'all' | 'action_required'; date_from: string; date_to: string };
const keys = (value: object, allowed: string[]) => Object.keys(value).every(key => allowed.includes(key));
const stamp = (value: string) => typeof value === 'string' && value.length <= 40 && Number.isFinite(Date.parse(value));
const boundedId = (value: unknown) => typeof value === 'string' && value.length > 0 && value.length <= 64;

export function verifyReadiness(value: ReadinessPage, matterId: string, analysisId: string, offset: number) {
  const fail = () => { throw new Error('İnceleme kuyruğunun kapsamı veya sınırlı gözlem bağı doğrulanamadı.'); };
  if (!value || !keys(value, ['recipe', 'matter_id', 'analysis_id', 'observed_at', 'items', 'coverage', 'legal_readiness', 'qualification_granted'])
    || value.recipe !== 'private-source-review-readiness-v1' || value.matter_id !== matterId || value.analysis_id !== analysisId
    || !stamp(value.observed_at) || value.legal_readiness !== 'not_established' || value.qualification_granted !== false
    || !Array.isArray(value.items) || value.items.length > 10 || !value.coverage) fail();
  const coverage = value.coverage;
  if (!keys(coverage, ['scope', 'scanned_count', 'returned_count', 'has_more', 'next_offset', 'pagination_limit_reached', 'priority_scope', 'total_count', 'source_verification'])
    || coverage.scope !== 'authorized_analysis_window_only' || coverage.priority_scope !== 'current_window_only' || coverage.total_count !== null
    || coverage.source_verification !== 'not_checked' || !Number.isInteger(coverage.scanned_count) || coverage.scanned_count < 0 || coverage.scanned_count > 10
    || coverage.returned_count !== value.items.length || coverage.returned_count > coverage.scanned_count || typeof coverage.has_more !== 'boolean'
    || typeof coverage.pagination_limit_reached !== 'boolean'
    || (coverage.pagination_limit_reached !== (coverage.has_more && offset + 10 > 10000))
    || (coverage.has_more && !coverage.pagination_limit_reached ? coverage.scanned_count !== 10 || coverage.next_offset !== offset + 10 : coverage.next_offset !== null)) fail();
  if (new Set(value.items.map(item => item.id)).size !== value.items.length) fail();
  for (const item of value.items) {
    if (!keys(item, ['id', 'recorded_at', 'state', 'version_id', 'product_id', 'manifest_sha256', 'historical_review', 'private_observation', 'source_verification', 'legal_readiness'])
      || !/^sac-[a-f0-9]{20}-[a-f0-9]{32}$/.test(item.id) || !stamp(item.recorded_at) || !Object.hasOwn(READINESS_STATES, item.state)
      || item.source_verification !== 'not_checked' || item.legal_readiness !== 'not_established'
      || (item.version_id !== undefined && !boundedId(item.version_id)) || (item.product_id !== undefined && !boundedId(item.product_id))
      || (item.manifest_sha256 !== undefined && !/^[a-f0-9]{64}$/.test(item.manifest_sha256)) || !item.historical_review || !item.private_observation) fail();
    const historical = item.historical_review; const observation = item.private_observation;
    if (!keys(historical, ['state', 'id', 'recorded_at']) || !['unknown', 'unreviewed', 'changes_requested', 'reviewed_conditional'].includes(historical.state)
      || (historical.id !== null && (typeof historical.id !== 'string' || !/^sar-[a-f0-9]{20}-[a-f0-9]{32}$/.test(historical.id)))
      || (historical.recorded_at !== null && !stamp(historical.recorded_at)) || !keys(observation, ['state', 'reasons'])
      || !['unknown', 'unchanged', 'changed'].includes(observation.state) || !Array.isArray(observation.reasons) || observation.reasons.length > 20
      || observation.reasons.some(reason => !Object.hasOwn(READINESS_REASONS, reason))) fail();
  }
}
