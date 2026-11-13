import type { ReactNode } from 'react';
import { Detail } from '../../components';
import { FACT_LABELS } from '../../utils';
import { ANALYSIS_LABELS, type AnalysisContent } from './analysisTypes';

function Step({ number, title, count, children }: { number: string; title: string; count?: number; children: ReactNode }) {
  return <section className="reasoning-step"><header><span className="step-number" aria-hidden="true">{number}</span><h4>{title}</h4>{count !== undefined && <span className="count">{count}</span>}</header><div className="reasoning-step-body">{children}</div></section>;
}

export function AnalysisReasoning({ content, onSource, proposed }: { content: AnalysisContent; onSource: (id: string) => void; proposed: boolean }) {
  const facts = new Map(content.fact_snapshots.map(fact => [fact.id, fact]));
  return <div className="analysis-reasoning">
    <p className="small muted">{proposed ? 'Modelin onaylanmamış düzenleme önerisi.' : content.authorship === 'user_with_ai_assistance' ? 'Model önerisinden uyarlanmış avukat taslağı.' : 'Avukat tarafından yazılmış gerekçe.'} Otomatik hukuki sonuç veya modelin düşünce kaydı değildir.</p>
    <dl className="reading-metadata"><div><dt>Süreç</dt><dd>{content.posture || 'Belirtilmedi'}</dd></div><div><dt>Olay tarihi</dt><dd>{content.event_date || 'Bilinmiyor'}</dd></div></dl>
    <Step number="01" title="Öncüller" count={content.premises.length}>
      {!content.premises.length && <p className="section-empty">Bu sürümde öncül kaydedilmemiş.</p>}
      {content.premises.map(item => { const fact = facts.get(item.fact_id || ''); return <article className="reasoning-entry" key={item.id}><h5>{item.id} · {fact ? FACT_LABELS[fact.status as keyof typeof FACT_LABELS] || fact.status : ANALYSIS_LABELS[item.kind]}</h5><p className="authored-text">{fact?.text || item.text}</p>{fact?.evidence_id && <button type="button" className="source-link" onClick={() => onSource(fact.evidence_id!)}>Öncülün özgün dayanağı</button>}</article>; })}
    </Step>
    <Step number="02" title="Kural adayları ve koşullar" count={content.rules.length}>
      {!content.rules.length && <p className="section-empty">Bu sürümde kural adayı kaydedilmemiş.</p>}
      {content.rules.map(rule => <article className="reasoning-entry" key={rule.id}><h5>{rule.id} · {ANALYSIS_LABELS[rule.kind]}</h5><p className="authored-text">{rule.text}</p>
        {!!rule.conditions.length && <ul className="condition-list">{rule.conditions.map(item => <li key={item.id}><strong>{item.id} · {ANALYSIS_LABELS[item.kind]}</strong><p className="authored-text">{item.text}</p><span className="small muted">Gereken durum: {ANALYSIS_LABELS[item.required_status]}</span></li>)}</ul>}
        <Detail title="Kuralın kaynak bağlantıları" variant="technical"><p className="reference-id">Dayanaklar: {rule.evidence_ids.join(', ') || 'Bağlanmadı'}</p></Detail>
      </article>)}
    </Step>
    <Step number="03" title="Uygulama" count={content.applications.length}>
      {!content.applications.length && <p className="section-empty">Bu sürümde uygulama adımı kaydedilmemiş.</p>}
      {content.applications.map(item => <article className="reasoning-entry" key={item.id}><h5>{item.id} · {item.rule_id} / {item.premise_ids.join(', ') || 'Öncül yok'}</h5><p className="authored-text">{item.rationale}</p>
        {!!item.assessments.length && <ul className="condition-list">{item.assessments.map(assessment => <li key={assessment.condition_id}><strong>{assessment.condition_id} · {ANALYSIS_LABELS[assessment.status]}</strong><p className="small muted">Öncüller: {assessment.premise_ids.join(', ') || 'Bağlanmadı'}</p></li>)}</ul>}
      </article>)}
    </Step>
    <Step number="04" title="Alternatifler" count={content.alternatives.length}>
      {!content.alternatives.length && <p className="section-empty">Bu sürümde alternatif kaydedilmemiş.</p>}
      {content.alternatives.map(item => <article className="reasoning-entry" key={item.id}><h5>{item.id} · {ANALYSIS_LABELS[item.kind]}</h5><p className="authored-text">{item.text}</p>{!!item.evidence_ids.length && <p className="reference-id">Dayanaklar: {item.evidence_ids.join(', ')}</p>}</article>)}
    </Step>
    <Step number="05" title={proposed ? 'Modelin geçici sonuç önerisi' : 'Avukatın geçici sonuç metni'}>
      <p className="authored-text">{content.conclusion.text || 'Bu sürümde sonuç metni kaydedilmemiş.'}</p><p className="small muted">Talep edilen değerlendirme: {ANALYSIS_LABELS[content.conclusion.requested_disposition]}. Kontrol sonucu yukarıda ayrıca gösterilir.</p>
      {!!content.conclusion.uncertainty.length && <div className="reasoning-uncertainty"><h5>Belirsizlikler</h5><ul>{content.conclusion.uncertainty.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      {content.conclusion.next_step && <p className="authored-text"><strong>Sonraki adım:</strong> {content.conclusion.next_step}</p>}
      <Detail title="Sonucun adım bağlantıları" variant="technical"><p className="reference-id">Uygulamalar: {content.conclusion.application_ids.join(', ') || 'Bağlanmadı'} · Alternatifler: {content.conclusion.alternative_ids.join(', ') || 'Bağlanmadı'}</p></Detail>
    </Step>
  </div>;
}
