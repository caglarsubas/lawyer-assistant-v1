import { useRef, useState, type FormEvent } from 'react';
import { ApiError, post } from '../../api';
import { Detail, Field, Icon, JsonDetails, Notice } from '../../components';
import type { GatewayEvaluation } from '../../types';
import { messageOf } from '../../utils';

const decisionLabels: Record<string, string> = {
  ALLOW: 'Gönderime uygun',
  REQUIRE_APPROVAL: 'Tam sorgu için onay gerekiyor',
  DENY: 'Gönderim engellendi',
  QUARANTINE: 'İncelemeye alındı',
};

export default function GatewayPanel({ matterId }: { matterId: string }) {
  const [query, setQuery] = useState('');
  const [destination, setDestination] = useState('');
  const [queryType, setQueryType] = useState<'public' | 'matter'>('public');
  const [evaluation, setEvaluation] = useState<GatewayEvaluation | null>(null);
  const [approved, setApproved] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [submitted, setSubmitted] = useState<Pick<GatewayEvaluation, 'request_id' | 'payload_digest'> | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const base = `/matters/${encodeURIComponent(matterId)}/gateway`;

  function clearDecision() {
    setEvaluation(null);
    setApproved(false);
    setResult(null);
    setError('');
  }

  async function perform(action: () => Promise<void>, recovery?: (cause: unknown) => string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError('');
    try {
      await action();
    } catch (cause) {
      setError(recovery ? recovery(cause) : messageOf(cause));
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  function evaluate(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      clearDecision();
      setSubmitted(null);
      setEvaluation(await post<GatewayEvaluation>(`${base}/evaluate`, { query, destination, query_type: queryType }));
    });
  }

  function approve() {
    if (!evaluation) return;
    void perform(async () => {
      const receipt = await post<{ request_id: string; approved: boolean; payload_digest: string }>(
        `${base}/approve`, { request_id: evaluation.request_id },
      );
      if (receipt.request_id !== evaluation.request_id || receipt.payload_digest !== evaluation.payload_digest || receipt.approved !== true) {
        throw new Error('Onay kaydı, denetlenen istekle eşleşmiyor.');
      }
      setApproved(true);
    }, cause => {
      clearDecision();
      return `${messageOf(cause)} Yeniden işlem yapmak için sorguyu denetleyin.`;
    });
  }

  function execute() {
    if (!evaluation) return;
    void perform(async () => {
      // Requests are single-use. An error response may arrive after dispatch.
      clearDecision();
      setSubmitted({ request_id: evaluation.request_id, payload_digest: evaluation.payload_digest });
      setResult(await post(`${base}/execute`, { request_id: evaluation.request_id }));
    }, cause => {
      if (cause instanceof ApiError && [401, 403, 404, 422].includes(cause.status)) {
        setSubmitted(null);
        return `${cause.message} Yeni bir istek için sorguyu yeniden denetleyin.`;
      }
      if (cause instanceof ApiError && (
        (cause.status === 502 && cause.message === 'Kaynak güvenle alınamadı; istek yeniden kullanılmaz')
        || (cause.status === 503 && cause.message === 'Dış kaynak geçidi yapılandırılmadı')
      )) return `${cause.message}. Yeni bir istek için sorguyu yeniden denetleyin.`;
      return 'Gönderimin sonucu doğrulanamadı. Geçit kayıtlarının kontrolü için aşağıdaki istek kimliğini kullanın.';
    });
  }

  const decision = evaluation?.decision.toUpperCase();
  return <Detail title="Dış kaynak araştırması · Sorgu denetimi">
    <p className="small muted">Dışarı gönderilecek sorgu ve hedef adres önce denetlenir. Dosya içeriği yüklenmez. Ağ erişimi kapalıysa gerçek bir arama yapılmaz.</p>
    <form className="form-grid gateway-form" onSubmit={evaluate}>
      <Field label="Gönderilecek tam sorgu" className="span-full">{id => <textarea id={id} rows={2} required maxLength={500} disabled={pending} value={query}
        onChange={event => { setQuery(event.target.value); clearDecision(); }} placeholder="Kişisel veri içermeyen hukuki araştırma sorusu" />}</Field>
      <Field label="Hedef adres">{id => <input id={id} type="url" required maxLength={500} disabled={pending} placeholder="https://…" value={destination}
        onChange={event => { setDestination(event.target.value); clearDecision(); }} />}</Field>
      <Field label="Sorgu türü">{id => <select id={id} disabled={pending} value={queryType}
        onChange={event => { setQueryType(event.target.value as 'public' | 'matter'); clearDecision(); }}>
        <option value="public">Genel hukuki araştırma</option>
        <option value="matter">Dosyaya özgü, arındırılmış sorgu</option>
      </select>}</Field>
      <div className="span-full"><button className="button secondary" disabled={pending}>Sorguyu denetle<Icon name="shield" size={16} /></button></div>
    </form>
    {pending && <p className="small muted" role="status">İstek işleniyor…</p>}
    {error && <Notice error>{error}</Notice>}
    {evaluation && <div className="gateway-decision">
      <strong>{decisionLabels[decision || ''] || 'Sorgu için ek işlem gerekli'}</strong>
      <p className="small">{evaluation.reason_codes.join(' · ')}</p>
      <Detail title="İstek ve politika kaydı"><dl className="definition-grid">
        <div><dt>Politika sürümü</dt><dd>{evaluation.policy_version}</dd></div>
        <div><dt>İstek kimliği</dt><dd className="reference-id">{evaluation.request_id}</dd></div>
        <div className="span-full"><dt>İçerik özeti</dt><dd className="reference-id">{evaluation.payload_digest}</dd></div>
      </dl></Detail>
      {decision === 'REQUIRE_APPROVAL' && !approved && <button className="button secondary" disabled={pending} onClick={approve}>Bu sorguyu ve hedefi onayla</button>}
      {(decision === 'ALLOW' || (decision === 'REQUIRE_APPROVAL' && approved)) && <button className="button primary" disabled={pending} onClick={execute}>İsteği gönder<Icon name="external" size={16} /></button>}
      {approved && <p className="small muted">Onay yalnızca yukarıdaki tam sorgu ve hedef için geçerlidir.</p>}
    </div>}
    {result !== null && <JsonDetails value={result} title="Dış kaynak isteğinin sonucu" />}
    {submitted && <Detail title="Son gönderim için istek bilgileri">
      <dl className="definition-grid"><div><dt>İstek kimliği</dt><dd className="reference-id">{submitted.request_id}</dd></div>
        <div><dt>İçerik özeti</dt><dd className="reference-id">{submitted.payload_digest}</dd></div></dl>
    </Detail>}
  </Detail>;
}
