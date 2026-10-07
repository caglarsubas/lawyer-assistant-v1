import { Badge, Detail, Notice } from '../../components';
import { FACT_LABELS, locatorText } from '../../utils';
import { FeedbackSummary } from './AnalysisFeedback';
import { ANALYSIS_LABELS, type AnalysisChecks, type AnalysisContent, type AnalysisFreshness, type AnalysisReviewProjection } from './analysisTypes';

export function AnalysisCheckPanel({ checks, freshness, review }: { checks: AnalysisChecks; freshness?: AnalysisFreshness; review?: AnalysisReviewProjection }) {
  const changesRequested = review?.latest?.decision === 'changes_requested';
  const disposition = freshness?.status === 'stale' || changesRequested ? 'withheld' : checks.effective_disposition;
  return <div>
    <div className="practice-record-heading"><Badge>{ANALYSIS_LABELS[disposition]}</Badge><span className="small muted">{checks.critical_count} kritik kontrol · Hukuki onay verilmedi</span></div>
    {freshness?.status === 'stale' && <Notice error>Dayanaklar değişti. Önceki metin korunuyor; yeni sürümde inceleyin.{freshness.reasons.map((reason) => <p key={reason}>{reason}</p>)}</Notice>}
    {changesRequested && <Notice error>Avukat değişiklik istedi; sonuç değerlendirmesi yeniden incelemeye kadar bekletilir. Yapısal kontrollerin özgün sonucu değiştirilmez.</Notice>}
    <Detail title={`Kontrol ayrıntıları (${checks.defects.length})`}>
      <p className="small muted">Kontroller beyan edilen bağlantıları ve koşulları inceler. Pasajın yorumu, çıkarımın doğruluğu ve hukuki uygulanabilirlik avukat incelemesi gerektirir.</p>
      <ul>{checks.defects.map((defect) => <li key={defect.id}><strong>{defect.severity === 'critical' ? 'Kritik' : 'İnceleme'} · {defect.target_id}:</strong> {defect.message}</li>)}</ul>
    </Detail>
  </div>;
}

export function AnalysisContentView({ content, freshness, review, onSource, proposed = false }: { content: AnalysisContent; freshness?: AnalysisFreshness; review?: AnalysisReviewProjection; onSource: (id: string) => void; proposed?: boolean }) {
  const facts = new Map(content.fact_snapshots.map((fact) => [fact.id, fact]));
  return <>
    <p className="authored-text"><strong>Mesele:</strong> {content.issue}</p>
    {content.ai_assistance && <Detail title="Model katkısı ve kayıt sınırları"><p>Model: {content.ai_assistance.provider.model} · {content.ai_assistance.passes} geçiş · Hukuki inceleme değildir.</p><p className="reference-id">Öneri: {content.ai_assistance.job_id} · Kaynak sürüm: {content.ai_assistance.source_version_id}</p><p className="small muted">Alınan önerinin doğrulanmamış notları; sonraki avukat değişikliklerini ayrıca inceleyin.</p><ul>{content.ai_assistance.review_notes?.map((note, index) => <li key={index}>{note.target_id} · Geçiş {note.pass}: {note.text}</li>)}</ul></Detail>}
    {content.ai_assistance?.review_feedback && <FeedbackSummary feedback={content.ai_assistance.review_feedback} responses={content.ai_assistance.feedback_responses} pass={content.ai_assistance.feedback_response_pass} onSource={onSource} />}
    <AnalysisCheckPanel checks={content.checks} freshness={freshness} review={review} />
    <Detail title="Öncül → kural → uygulama → alternatif → geçici sonuç">
      <p className="small muted">{proposed ? 'Modelin onaylanmamış düzenleme önerisi.' : content.authorship === 'user_with_ai_assistance' ? 'Model önerisinden uyarlanmış avukat taslağı.' : 'Avukat tarafından yazılmış gerekçe.'} Otomatik hukuki sonuç veya modelin düşünce kaydı değildir.</p>
      <p><strong>Süreç:</strong> {content.posture || 'Belirtilmedi'} · <strong>Olay tarihi:</strong> {content.event_date || 'Bilinmiyor'}</p>
      <h4>Öncüller</h4>{content.premises.map((item) => { const fact = facts.get(item.fact_id || ''); return <div key={item.id}><p className="authored-text"><strong>{item.id} · {fact ? FACT_LABELS[fact.status as keyof typeof FACT_LABELS] || fact.status : ANALYSIS_LABELS[item.kind]}:</strong> {fact?.text || item.text}</p>{fact?.evidence_id && <button className="source-link" onClick={() => onSource(fact.evidence_id!)}>Öncülün özgün dayanağı</button>}</div>; })}
      <h4>Kural adayları ve koşullar</h4>{content.rules.map((rule) => <div key={rule.id}><p className="authored-text"><strong>{rule.id} · {ANALYSIS_LABELS[rule.kind]}:</strong> {rule.text}</p><ul>{rule.conditions.map((item) => <li key={item.id}>{item.id} · {ANALYSIS_LABELS[item.kind]}: {item.text} · Gereken durum: {ANALYSIS_LABELS[item.required_status]}</li>)}</ul><p className="reference-id">Dayanaklar: {rule.evidence_ids.join(', ') || 'Bağlanmadı'}</p></div>)}
      <h4>Uygulama</h4>{content.applications.map((item) => <div key={item.id}><p className="authored-text"><strong>{item.id} · {item.rule_id} / {item.premise_ids.join(', ') || 'Öncül yok'}:</strong> {item.rationale}</p><ul>{item.assessments.map((assessment) => <li key={assessment.condition_id}>{assessment.condition_id}: {ANALYSIS_LABELS[assessment.status]} · Öncüller: {assessment.premise_ids.join(', ') || 'Bağlanmadı'}</li>)}</ul></div>)}
      <h4>Alternatifler</h4>{content.alternatives.map((item) => <p className="authored-text" key={item.id}><strong>{item.id} · {ANALYSIS_LABELS[item.kind]}:</strong> {item.text} <span className="reference-id">{item.evidence_ids.join(', ')}</span></p>)}
      <h4>{proposed ? 'Modelin geçici sonuç önerisi' : 'Avukatın geçici sonuç metni'}</h4><p className="authored-text">{content.conclusion.text}</p><p className="small muted">Talep edilen değerlendirme: {ANALYSIS_LABELS[content.conclusion.requested_disposition]}. Kontrol sonucu yukarıda ayrıca gösterilir.</p><p className="reference-id">Uygulamalar: {content.conclusion.application_ids.join(', ') || 'Bağlanmadı'} · Alternatifler: {content.conclusion.alternative_ids.join(', ') || 'Bağlanmadı'}</p>
      <ul>{content.conclusion.uncertainty.map((item, index) => <li key={index}>{item}</li>)}</ul><p><strong>Sonraki adım:</strong> {content.conclusion.next_step}</p>
    </Detail>
    <Detail title={`Özgün belge alıntıları (${content.evidence.length})`}>
      <p className="small muted">Unicode aralıkları sıfırdan başlar; son konum dahil değildir. Bir pasaj bağlamak, yazdığınız yorumun o pasajdan çıktığını kanıtlamaz.</p>
      <p className="small muted">Alıntılar saklanan sürümdendir. Kaynak düğmesi belgenin güncel görünümünü açar; değişmişse saklanan metinle karşılaştırın.</p>
      {content.evidence.map((item) => <div key={item.evidence_id}><button className="source-link" onClick={() => onSource(item.evidence_id)}>{item.name} · {locatorText(item.locator)} · Özgün pasajı aç</button><p className="small muted">[{item.start}, {item.end}) / {item.full_passage_length}</p><p className="authored-text">{item.text}</p></div>)}
    </Detail>
    {content.revision_comparison.previous_version_id && <Detail title="Önceki sürüme göre değişiklikler"><p>Değişen bölümler: {content.revision_comparison.changed_sections.join(', ') || 'Yok'} · Değişen dayanak grupları: {content.revision_comparison.changed_dependency_groups.join(', ') || 'Yok'}</p><p>{content.revision_comparison.checks_no_longer_triggered.length} kontrol artık tetiklenmiyor; {content.revision_comparison.new_check_ids.length} yeni kontrol.</p><p className="small muted">Bu karşılaştırma, bir hukuki kusurun düzeltildiğini veya kaldırılan bir adımın gereksiz olduğunu doğrulamaz.</p></Detail>}
  </>;
}
