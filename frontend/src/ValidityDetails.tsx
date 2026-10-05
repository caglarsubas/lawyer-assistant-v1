import { Detail } from './components';
import type { ValidityMetadata } from './types';
import { formatDate } from './utils';

export function ValidityDetails({ validity }: { validity: ValidityMetadata }) {
  if (validity.validity_end_status !== 'open_ended') return null;
  return <Detail title="Yürürlük incelemesinin kapsamı">
    <p className="small">Açık uçlu durum, <strong>{formatDate(validity.validity_checked_through)}</strong> tarihine kadar (bu gün dahil) incelendi. Sonraki tarihlerde uygulanabilirlik için yeniden inceleme gerekir.</p>
    <p className="small muted">Aşağıdaki pasajlar yürürlük incelemesinin dayanağıdır; hükmün metninden ayrı gösterilir.</p>
    {validity.validity_evidence?.length ? validity.validity_evidence.map(proof => <article key={proof.id}>
      <p className="small"><strong>{proof.locator}</strong> · [{proof.start_offset}, {proof.end_offset})</p>
      <p className="source-passage-text">{proof.text}</p>
      <Detail title="Dayanağın doğrulama kaydı"><dl className="coverage-fields">
        <div><dt>Pasaj</dt><dd className="reference-id">{proof.id}</dd></div>
        <div><dt>Kaynak özeti</dt><dd className="reference-id">{proof.sha256}</dd></div>
        <div><dt>Metin özeti</dt><dd className="reference-id">{proof.text_sha256}</dd></div>
      </dl></Detail>
    </article>) : <p className="small">Bu kayıtta inceleme dayanağı gösterilemiyor; kaynağı ayrıca doğrulayın.</p>}
  </Detail>;
}
