import { Detail } from '../../components';
import { FINDING_OUTCOMES } from './authorityFindingTypes';
import type { AuthorityFeedback, AuthorityResponse } from './authorityProposalTypes';

const labels = { proposed_change: 'Düzenleme adayı', requires_manual_work: 'Elle çalışma gerekli', unresolved: 'Çözülmedi' };
export default function AuthorityProposalSummary({ feedback, responses, pass }: { feedback: AuthorityFeedback; responses?: AuthorityResponse[]; pass?: number | null }) {
  return <Detail title="Seçilen kamu dayanakları ve model yanıtları">
    <p>Bu bulgular otomatik giderilmiş sayılmaz. Kaynak bağları, tarih, anlam ve karşı dayanaklar avukat tarafından incelenmelidir.</p>
    <p className="reference-id">İnceleme: {feedback.dependency.review_id} · Aday yanıt geçişi: {pass ?? 'Yok'}</p>
    {feedback.findings.map(finding => <section key={finding.finding_id}><strong>{finding.finding_id} · {FINDING_OUTCOMES[finding.outcome]}</strong><p className="authored-text">{finding.note}</p><p className="small">Düzenlenebilir bağlı adımlar: {finding.editable_targets.join(' · ') || 'Elle çalışma gerekli'}</p></section>)}
    {responses?.map(response => <section key={response.finding_id}><strong>{labels[response.outcome]} · {response.finding_id}</strong><p className="authored-text">{response.text}</p><p className="small">Düzenlemeler: {response.edited_targets.join(' · ') || 'Yok'} · Kamu dayanakları: {response.authority_ids.join(' · ')}</p></section>)}
    {feedback.sources.map(source => <Detail key={source.id} title={`${source.id} · Özgün kamu pasajı`}><p className="reference-id">{source.evidence.source_version_id} · {source.evidence.locator} · SHA-256: {source.evidence.quote_sha256}</p><blockquote>{source.evidence.text}</blockquote><p className="small">Beyan edilen ilişki: {source.selection.relationship}. Somut olaya uygulanabilirlik belirlenmedi.</p><pre className="data-pre">{JSON.stringify(source.temporal_alignment, null, 2)}</pre></Detail>)}
  </Detail>;
}
