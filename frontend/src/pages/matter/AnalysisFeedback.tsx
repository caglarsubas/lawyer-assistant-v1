import { Detail } from '../../components';
import type { AnalysisFeedback, AnalysisReviewEvent, FeedbackResponse } from './analysisTypes';

const OUTCOMES = { proposed_change: 'Düzenleme adayı', requires_manual_work: 'Elle çalışma gerekli', unresolved: 'Çözülmedi' };

export function ReviewFindingPicker({ review, indices, disabled, onChange, onSource }: { review: AnalysisReviewEvent; indices: number[]; disabled: boolean; onChange: (indices: number[]) => void; onSource: (id: string) => void }) {
  return <Detail title="İnceleme bulgularını modele ekle (isteğe bağlı)">
    <p>Son değişiklik isteğinden en fazla beş bulgu seçin. Yalnız seçilen bulgu metni ve önerilen değişiklik, sabit taslakla birlikte yerel modele iletilir. Seçim yapmazsanız inceleme metni eklenmez.</p>
    <p className="small muted">{indices.length}/5 bulgu seçildi. Model bulguları kapatamaz; yeni taslak yeniden avukat incelemesi gerektirir.</p>
    <fieldset disabled={disabled}><legend>Modele iletilecek bulgular</legend>{review.findings.map((finding, index) => <div key={index}>
      <label><input type="checkbox" checked={indices.includes(index)} disabled={!indices.includes(index) && indices.length >= 5} onChange={(event) => onChange(event.target.checked ? [...indices, index].sort((a, b) => a - b) : indices.filter((item) => item !== index))} /> {index + 1} · {finding.target_id} · {finding.severity}: {finding.text}</label>
      {finding.suggested_change && <p className="authored-text">İstenen değişiklik: {finding.suggested_change}</p>}
      {finding.evidence_ids.map((id) => <button type="button" key={id} className="source-link" onClick={() => onSource(id)}>Bulgunun özgün dayanağı</button>)}
    </div>)}</fieldset>
  </Detail>;
}

export function FeedbackResponses({ responses, onSource }: { responses: FeedbackResponse[]; onSource: (id: string) => void }) {
  return <ul>{responses.map((response) => <li key={response.finding_id}><strong>{response.finding_id} · {OUTCOMES[response.outcome]}:</strong> {response.text}<p className="reference-id">Bağlanan düzenlemeler: {response.edited_targets.join(', ') || 'Yok'}</p>{response.evidence_ids.map((id) => <button key={id} className="source-link" onClick={() => onSource(id)}>Yanıtın özgün dayanağı</button>)}</li>)}</ul>;
}

export function FeedbackSummary({ feedback, responses = [], pass, onSource }: { feedback: AnalysisFeedback; responses?: FeedbackResponse[]; pass?: number | null; onSource: (id: string) => void }) {
  return <Detail title={`Seçilen inceleme bulguları ve model yanıtları (${feedback.findings.length})`}>
    <p className="reference-id">Kaynak inceleme: {feedback.review_id} · Sürüm: {feedback.source_version_id} · İçerik özeti: {feedback.content_sha256}</p>
    <p className="small muted">Yanıtlar bulgunun giderildiğini veya hukuken onaylandığını göstermez. Sabit öncül, kural, kaynak ve bağlantı değişiklikleri elle yapılmalıdır. Önceki inceleme ve bulguları korunur.</p>
    {feedback.findings.map((finding) => <div key={finding.finding_id}><p className="authored-text"><strong>{finding.finding_id} · {finding.target_id} · {finding.severity}:</strong> {finding.text}</p>{finding.suggested_change && <p className="authored-text">İstenen değişiklik: {finding.suggested_change}</p>}<p className="reference-id">Beyan edilen bağlantılardan düzenleme adayları: {finding.editable_targets.join(', ') || 'Yok'}</p>{finding.evidence_ids.map((id) => <button key={id} className="source-link" onClick={() => onSource(id)}>Bulgunun özgün dayanağı</button>)}</div>)}
    {pass ? <p>Saklanan adayın yanıt geçişi: {pass}</p> : <p>Henüz saklanan aday yanıtı yok.</p>}
    <FeedbackResponses responses={responses} onSource={onSource} />
  </Detail>;
}
