import { useEffect, useState } from 'react';
import { request } from '../../api';
import { Detail, Notice } from '../../components';
import { messageOf } from '../../utils';
interface Access { direct_case_grant: boolean; client_all_cases_origins: string[]; permissions: string[]; supervisor: boolean; responsible: boolean; team: { user_id: string; name: string; supervisor: boolean; responsible: boolean }[] }
export default function CaseAccessPanel({ matterId }: { matterId: string }) {
  const [access, setAccess] = useState<Access | null>(null); const [error, setError] = useState('');
  useEffect(() => { const controller = new AbortController(); request<Access>(`/workspaces/${encodeURIComponent(matterId)}/access`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setAccess(value); }).catch(cause => { if (!controller.signal.aborted) { setAccess(null); setError(messageOf(cause)); } }); return () => controller.abort(); }, [matterId]);
  return <Detail title="Erişimim ve dosya ekibi"><p className="reference-id">Atama referansı: {matterId}</p>{error && <Notice error>{error}</Notice>}{access && <><p>{access.direct_case_grant ? 'Doğrudan dosya atamanız var.' : 'Müvekkil kapsamından erişiyorsunuz.'}</p>{Boolean(access.client_all_cases_origins.length) && <p>Müvekkil üzerinden tüm bağlı dosyalar izni: {access.client_all_cases_origins.join(', ')}</p>}<p>{access.supervisor ? 'Dosya gözetmenisiniz. ' : ''}{access.responsible ? 'Sorumlu avukatsınız. ' : ''}Ekip değişikliklerini yalnızca büro yöneticisi kaydeder. Görev ve görüş takibi sonraki aşamadadır.</p><ul>{access.team.map(person => <li key={person.user_id}>{person.name} · {person.supervisor ? 'gözetmen' : 'erişimli çalışan'}{person.responsible ? ' · sorumlu avukat' : ''}</li>)}</ul><details><summary>Etkin işlem izinleri</summary><ul>{access.permissions.map(value => <li key={value}>{value}</li>)}</ul></details></>}</Detail>;
}
