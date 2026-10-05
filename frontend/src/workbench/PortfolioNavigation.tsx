import { useEffect, useState } from 'react';
import { request } from '../api';
import { Icon, Loading, Notice } from '../components';
import type { Matter, PortfolioFilters } from '../types';
import { formatDate, messageOf } from '../utils';
import { EMPTY_FILTERS, usePortfolio } from './portfolio';

export default function PortfolioNavigation({ page, workspaceId }: { page: string; workspaceId: string | null }) {
  const { customers, workspaces, filters, setFilters, loading, error, refresh } = usePortfolio();
  const [query, setQuery] = useState('');
  const nav = [{ id: 'matters', label: 'Çalışma alanları', icon: 'folder' as const }, { id: 'customers', label: 'Müvekkiller', icon: 'book' as const }, { id: 'graphs', label: 'Hukuk haritası', icon: 'graph' as const }, { id: 'coverage', label: 'Kaynak kapsamı', icon: 'layers' as const }, { id: 'system', label: 'Sistem durumu', icon: 'settings' as const }];
  const active = filters.customer_ids.length > 0 || Boolean(filters.date_from || filters.date_to);
  const visible = workspaces.filter(item => `${item.title} ${(item.customers || []).map(customer => customer.name).join(' ')}`.toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr')));
  return <div className="portfolio-navigation">
    <nav className="main-nav" aria-label="Ana gezinme">{nav.map(item => <a key={item.id} href={`#/${item.id}`} className={page === item.id || (page === 'workspaces' && item.id === 'matters') || (page === 'sources' && item.id === 'coverage') ? 'active' : ''} aria-current={page === item.id || (page === 'workspaces' && item.id === 'matters') ? 'page' : page === 'sources' && item.id === 'coverage' ? 'location' : undefined}><Icon name={item.icon} size={18} /><span>{item.label}</span></a>)}</nav>
    <section className="portfolio-filters" aria-label="Portföy filtreleri"><div className="nav-section-heading"><h2>Portföy filtresi</h2>{active && <button className="text-button" onClick={() => setFilters(EMPTY_FILTERS)}>Temizle</button>}</div>
      <details className="customer-filter" open><summary>Müvekkiller <span className="count">{filters.customer_ids.length || 'Tümü'}</span></summary><p>Seçili müvekkillerden en az biriyle ilişkili alanlar.</p><div className="customer-options">{customers.length ? customers.map(customer => <label key={customer.id} className="check-option"><input type="checkbox" checked={filters.customer_ids.includes(customer.id)} onChange={event => setFilters(previous => ({ ...previous, customer_ids: event.target.checked ? [...previous.customer_ids, customer.id] : previous.customer_ids.filter(id => id !== customer.id) }))} /><span>{customer.name}</span></label>) : <p className="small muted">Henüz müvekkil eklenmedi.</p>}</div><a className="text-link" href="#/customers"><Icon name="plus" size={14} />Müvekkil ekle</a></details>
      <label className="compact-field">Tarih alanı<select value={filters.date_field} onChange={event => setFilters(previous => ({ ...previous, date_field: event.target.value as PortfolioFilters['date_field'] }))}><option value="created_at">Oluşturulma tarihi</option><option value="updated_at">Son güncelleme</option><option value="relevant_date">Hukuken ilgili tarih</option></select></label>
      <div className="date-filter-grid"><label className="compact-field">Başlangıç<input type="date" aria-label="Filtre başlangıç tarihi" value={filters.date_from} onChange={event => setFilters(previous => ({ ...previous, date_from: event.target.value }))} /></label><label className="compact-field">Bitiş<input type="date" aria-label="Filtre bitiş tarihi" value={filters.date_to} min={filters.date_from || undefined} onChange={event => setFilters(previous => ({ ...previous, date_to: event.target.value }))} /></label></div>
    </section>
    <section className="workspace-tree" aria-label="Çalışma alanları ve yüklenen dosyalar"><div className="nav-section-heading"><h2>Çalışma alanları</h2><span className="count">{visible.length}</span></div><label className="search-input"><Icon name="search" size={15} /><input aria-label="Çalışma alanlarında ara" placeholder="Çalışma alanı ara" value={query} onChange={event => setQuery(event.target.value)} /></label><a className="new-workspace-link" href="#/matters?new=1"><Icon name="plus" size={16} />Yeni çalışma alanı</a>
    {error && <Notice error>{error}<button className="text-button" onClick={refresh}>Yeniden dene</button></Notice>}
    {loading ? <Loading label="Portföy yükleniyor…" /> : visible.length ? visible.map(workspace => <WorkspaceBranch key={workspace.id} workspace={workspace} selected={workspace.id === workspaceId} />) : <p className="nav-empty">{active || query ? 'Bu filtrelerle çalışma alanı bulunamadı.' : 'İlk çalışma alanınızı oluşturun, ardından dosyalarınızı yükleyin.'}</p>}
    </section><div className="navigation-footnote"><Icon name="shield" size={15} /><span>Yalnızca yetkili olduğunuz çalışmalar.</span></div>
  </div>;
}
function WorkspaceBranch({ workspace, selected }: { workspace: Matter; selected: boolean }) {
  const [open, setOpen] = useState(selected); const [detail, setDetail] = useState<Matter | null>(null); const [error, setError] = useState('');
  const { revision } = usePortfolio();
  useEffect(() => { if (selected) setOpen(true); }, [selected]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setError('');
    request<Matter>(`/workspaces/${encodeURIComponent(workspace.id)}`, { signal: controller.signal }).then(setDetail).catch(cause => { if (cause.name !== 'AbortError') setError(messageOf(cause)); });
    return () => controller.abort();
  }, [open, revision, workspace.id]);
  return <div className={`workspace-branch ${selected ? 'selected' : ''}`}><div className="workspace-branch-heading"><button className={`branch-toggle ${open ? 'expanded' : ''}`} onClick={() => setOpen(!open)} aria-label={`${workspace.title}: dosyaları ${open ? 'gizle' : 'göster'}`} aria-expanded={open}><Icon name="chevron" size={13} /></button><a href={`#/matters/${encodeURIComponent(workspace.id)}`} aria-current={selected ? 'page' : undefined}><strong>{workspace.title}</strong><span>{workspace.document_count || 0} dosya · {formatDate(workspace.updated_at || workspace.created_at)}</span>{Boolean(workspace.customers?.length) && <small>{workspace.customers?.map(customer => customer.name).join(' · ')}</small>}</a></div>{open && <div className="workspace-files">{error ? <p className="small error-text">{error}</p> : !detail ? <p className="small muted">Dosyalar yükleniyor…</p> : detail.documents?.length ? detail.documents.map(document => <a key={document.id} href={`#/matters/${encodeURIComponent(workspace.id)}?tab=documents&document=${encodeURIComponent(document.id)}`}><Icon name="file" size={14} /><span>{document.name}</span></a>) : <span className="small muted">Henüz dosya yüklenmedi.</span>}<a className="file-upload-link" href={`#/matters/${encodeURIComponent(workspace.id)}?tab=documents`}><Icon name="upload" size={14} />Dosya yükle</a></div>}</div>;
}
