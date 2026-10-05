import { useEffect, useState, type FormEvent } from 'react';
import { request } from '../../api';
import { Detail, Notice } from '../../components';
import type { Matter } from '../../types';
import { messageOf } from '../../utils';
import { usePortfolio } from '../../workbench/portfolio';
export default function WorkspaceCustomers({ workspace, onChange }: { workspace: Matter; onChange: () => Promise<void> }) {
  const { customers } = usePortfolio(); const [selected, setSelected] = useState<string[]>(workspace.customer_ids || []); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { setSelected(workspace.customer_ids || []); }, [workspace.customer_ids]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { await request(`/workspaces/${encodeURIComponent(workspace.id)}/customers`, { method: 'PUT', body: JSON.stringify({ customer_ids: selected, revision: workspace.revision }) }); await onChange(); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <section className="workspace-customers"><p className="small-label">İLİŞKİLİ MÜVEKKİLLER</p><div className="customer-tags">{workspace.customers?.length ? workspace.customers.map(customer => <span key={customer.id}>{customer.name}</span>) : <p className="small muted">Henüz müvekkil ilişkilendirilmedi.</p>}</div><Detail title="Müvekkil bağlantılarını düzenle"><form onSubmit={submit}><p>Bu çalışma alanı birden fazla müvekkille ilişkili olabilir.</p>{customers.map(customer => <label key={customer.id} className="check-option"><input type="checkbox" checked={selected.includes(customer.id)} onChange={event => setSelected(previous => event.target.checked ? [...previous, customer.id] : previous.filter(id => id !== customer.id))} /><span>{customer.name}</span></label>)}{error && <Notice error>{error}</Notice>}<div className="form-actions"><a className="text-link" href="#/customers">Müvekkil ekle</a><button className="button secondary" disabled={busy}>{busy ? 'Kaydediliyor…' : 'Bağlantıları kaydet'}</button></div></form></Detail></section>;
}
