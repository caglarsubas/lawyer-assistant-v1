import { sourceBindingReason } from './lineageTypes';
import { Badge, Detail, Icon, Notice } from '../../components';
import { locatorText } from '../../utils';
import { SourceExcerpt } from '../../SourceExcerpt';
import { AnalysisReasoning } from './AnalysisReasoning';
import AuthorityProposalSummary from './AuthorityProposalSummary';
import { FeedbackSummary } from './AnalysisFeedback';
import { ANALYSIS_LABELS, type AnalysisChecks, type AnalysisContent, type AnalysisRecord, type AnalysisFreshness, type AnalysisReviewProjection } from './analysisTypes';

export function AnalysisCheckPanel({ checks, freshness, review }: { checks: AnalysisChecks; freshness?: AnalysisFreshness; review?: AnalysisReviewProjection }) {
  const changesRequested = review?.latest?.decision === 'changes_requested';
  const disposition = freshness?.status === 'stale' || changesRequested ? 'withheld' : checks.effective_disposition;
  return <div>
    <div className="practice-record-heading"><Badge>{ANALYSIS_LABELS[disposition]}</Badge><span className="small muted">{checks.critical_count} kritik kontrol · Hukuki onay verilmedi</span></div>
    {freshness?.status === 'stale' && <Notice error>Dayanaklar değişti. Önceki metin korunuyor; yeni sürümde inceleyin.{freshness.reasons.map((reason) => <p key={reason}>{sourceBindingReason(reason)}</p>)}</Notice>}
    {changesRequested && <Notice error>Avukat değişiklik istedi; sonuç değerlendirmesi yeniden incelemeye kadar bekletilir. Yapısal kontrollerin özgün sonucu değiştirilmez.</Notice>}
    <Detail title={`Kontrol ayrıntıları (${checks.defects.length})`}>
      <p className="small muted">Kontroller beyan edilen bağlantıları ve koşulları inceler. Pasajın yorumu, çıkarımın doğruluğu ve hukuki uygulanabilirlik avukat incelemesi gerektirir.</p>
      <ul className="check-findings">{checks.defects.map((defect) => <li key={defect.id}><span className="check-finding-kind">{defect.severity === 'critical' ? 'Kritik' : 'İnceleme'} · {defect.target_id}</span><p>{defect.message}</p></li>)}</ul>
    </Detail>
  </div>;
}

export function AnalysisContentView({ content, freshness, review, onSource, proposed = false, includeEvidence = true }: { content: AnalysisContent; freshness?: AnalysisFreshness; review?: AnalysisReviewProjection; onSource: (id: string) => void; proposed?: boolean; includeEvidence?: boolean }) {
  return <div className="analysis-content">
    <p className="authored-text"><strong>Mesele:</strong> {content.issue}</p>
    {content.focus_lineage && <Detail title="Odak kapsamı, dışarıda kalanlar ve ana sürüm bağı">
      <p>{content.focus_lineage.limitation}</p><p>{content.focus_lineage.omission_note}</p>
      <p className="reference-id">Ana analiz: {content.focus_lineage.parent_analysis_id} · Tam sürüm: {content.focus_lineage.parent_version_id} · İçerik SHA-256: {content.focus_lineage.parent_content_sha256}</p>
      <p className="small muted">Bu kayıt yalnız oluşturma seçimini açıklar; sonraki düzenlemeler ayrıca incelenmelidir. Ana analizdeki inceleme kararları aktarılmadı. Ana analiz ve özgün belgeler korunur.{content.focus_lineage.derived_ai && ' Ana sürümden türeyen model katkısı ayrıca incelenmelidir.'}</p>
      <p className="reference-id">Oluşturma sırasında ana inceleme: {content.focus_lineage.parent_review_id || 'Yok'} · Yeniden yazılan bölümler: {content.focus_lineage.replaced_sections.join(', ')}</p>
      <ul>{Object.entries(content.focus_lineage.omitted).map(([kind, items]) => <li key={kind}>Dışarıda kalan {kind}: {items.join(', ') || 'Yok'}</li>)}</ul>
      <ul>{content.focus_lineage.narrowed_ranges.map(item => <li key={item.evidence_id}>{item.evidence_id}: [{item.parent_start}, {item.parent_end}) → [{item.start}, {item.end})</li>)}</ul>
    </Detail>}
    {content.ai_assistance && <Detail title="Model katkısı ve kayıt sınırları"><p>Model: {content.ai_assistance.provider.model} · {content.ai_assistance.passes} geçiş · Hukuki inceleme değildir.</p><p className="reference-id">Öneri: {content.ai_assistance.job_id} · Kaynak sürüm: {content.ai_assistance.source_version_id}</p><p className="small muted">Alınan önerinin doğrulanmamış notları; sonraki avukat değişikliklerini ayrıca inceleyin.</p><ul>{content.ai_assistance.review_notes?.map((note, index) => <li key={index}>{note.target_id} · Geçiş {note.pass}: {note.text}</li>)}</ul></Detail>}
    {content.authority_contributions?.map((item, index) => <Detail key={item.job_id} title={`Saklanan kamu katkısı ${index + 1}`}><p className="small">Model: {item.provider_pin.model} · Önceki katkı, güncel model yanıtı değildir.</p><p className="reference-id">Öneri: {item.job_id} · Kaynak sürüm: {item.source_version_id}</p><AuthorityProposalSummary feedback={item.feedback} responses={item.responses} pass={item.response_pass} /></Detail>)}
    {content.ai_assistance?.review_feedback && <FeedbackSummary feedback={content.ai_assistance.review_feedback} responses={content.ai_assistance.feedback_responses} pass={content.ai_assistance.feedback_response_pass} onSource={onSource} />}
    {!!content.authority_revalidations?.length && <Detail title={`Saklanan kaynak bağı yenilemeleri (${content.authority_revalidations.length})`}><p className="small muted">Bu kayıtlar özgün katkıların yerine geçmez. Güncel gözlemleri yeniden inceleme araçlarından açın; hukuki onay verilmez.</p>{content.authority_revalidations.map(item => <p key={item.id} className="reference-id">{item.id} · SHA-256: {item.sha256}</p>)}</Detail>}
    <AnalysisCheckPanel checks={content.checks} freshness={freshness} review={review} />
    <Detail title="Öncül → kural → uygulama → alternatif → geçici sonuç" open={includeEvidence ? undefined : true}>
      <AnalysisReasoning content={content} onSource={onSource} proposed={proposed} />
    </Detail>
    {includeEvidence && <Detail title={`Özgün belge alıntıları (${content.evidence.length})`}><AnalysisEvidence content={content} onSource={onSource} /></Detail>}
    {content.revision_comparison.previous_version_id && <Detail title="Önceki sürüme göre değişiklikler"><p>Değişen bölümler: {content.revision_comparison.changed_sections.join(', ') || 'Yok'} · Değişen dayanak grupları: {content.revision_comparison.changed_dependency_groups.join(', ') || 'Yok'}</p><p>{content.revision_comparison.checks_no_longer_triggered.length} kontrol artık tetiklenmiyor; {content.revision_comparison.new_check_ids.length} yeni kontrol.</p><p className="small muted">Bu karşılaştırma, bir hukuki kusurun düzeltildiğini veya kaldırılan bir adımın gereksiz olduğunu doğrulamaz.</p></Detail>}
  </div>;
}

export function AnalysisEvidence({ content, onSource }: { content: AnalysisContent; onSource: (id: string) => void }) {
  return <div className="analysis-evidence">
    <p className="small muted">Alıntılar analiz kaydedilirken seçilen belge sürümüne aittir. Özgün pasajı açtığınızda belgenin güncel görünümüyle karşılaştırabilirsiniz.</p>
    {!content.evidence.length && <p className="practice-empty">Bu analize henüz belge alıntısı bağlanmamış.</p>}
    {content.evidence.map((item) => <SourceExcerpt key={item.evidence_id} name={item.name} location={`${locatorText(item.locator)} · Belge sürümü ${item.document_revision}`} text={item.text} onOpen={() => onSource(item.evidence_id)} metadata={<>
      <p className="small muted">Unicode aralığı [{item.start}, {item.end}) / {item.full_passage_length}. Son konum dahil değildir.</p>
      <dl className="provenance-list"><div><dt>Belge SHA-256</dt><dd>{item.document_sha256 || 'Kaydedilmedi'}</dd></div><div><dt>Pasaj SHA-256</dt><dd>{item.passage_sha256}</dd></div><div><dt>Alıntı SHA-256</dt><dd>{item.quote_sha256}</dd></div></dl>
    </>} />)}
  </div>;
}

export function AnalysisOverview({ record, onSource, onReview }: { record: AnalysisRecord; onSource: (id: string) => void; onReview: () => void }) {
  return <div className="analysis-overview">
    <section className="analysis-conclusion" aria-label="Taslağın özeti">
      <h4>Geçici değerlendirme</h4>
      <p className="authored-text">{record.conclusion.text || 'Bu taslakta henüz bir sonuç metni yok.'}</p>
    </section>
    {record.focus_lineage && <p className="analysis-scope">{record.focus_lineage.limitation}</p>}
    {!!record.conclusion.uncertainty.length && <section className="analysis-questions"><h4>Netleştirilmesi gerekenler</h4><ul>{record.conclusion.uncertainty.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}
    {record.conclusion.next_step && <section className="analysis-next"><h4>Taslaktaki sonraki adım</h4><p className="authored-text">{record.conclusion.next_step}</p></section>}
    <div className="analysis-review-action"><p>Değerlendirmenizi bu sürüme kaydedin. Düzeltme istediğiniz noktaları ayrıca belirtebilirsiniz.</p><button type="button" className="button primary" onClick={onReview}>İncelemeye geç <Icon name="arrow" size={16} /></button></div>
    <Detail title="Analizin tamamını oku"><AnalysisContentView content={record} freshness={record.freshness} review={record.review} onSource={onSource} includeEvidence={false} /></Detail>
  </div>;
}
