import { useCallback, useEffect, useState } from 'react';
import { request } from '../api';
import { Badge, Detail, Icon, Loading, Notice, PageHeader } from '../components';
import type { Matter } from '../types';
import { DOMAIN_LABELS, formatDate, messageOf } from '../utils';
import DocumentsPanel from './matter/DocumentsPanel';
import FactsPanel from './matter/FactsPanel';
import ResearchPanel from './matter/ResearchPanel';
import PracticePanel from './matter/PracticePanel';
import WorkspaceComments from './matter/WorkspaceComments';
import WorkspaceCustomers from './matter/WorkspaceCustomers';

export default function MatterPage({ matterId, demo, userRole, permissions, tab: selectedTab, selectedDocumentId }: { matterId: string; demo: boolean; userRole: string; permissions?: string[]; tab: string; selectedDocumentId: string | null }) {
  const [matter, setMatter] = useState<Matter | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(true);
  const tab = ['overview', 'documents', 'facts', 'practice', 'research', 'comments'].includes(selectedTab) ? selectedTab : 'overview';
  function setTab(value: string) { window.location.hash = `/matters/${encodeURIComponent(matterId)}?tab=${value}`; }
  const reload = useCallback(async () => { const data = await request<Matter>(`/workspaces/${encodeURIComponent(matterId)}`); setMatter(data); }, [matterId]);
  useEffect(() => { reload().catch((cause) => setError(messageOf(cause))).finally(() => setLoading(false)); }, [reload]);
  if (loading) return <Loading label="Çalışma alanı açılıyor…" />;
  if (!matter) return <Notice error>{error || 'Çalışma alanı bulunamadı.'} <a href="#/matters" className="text-link">Çalışma alanlarına dön</a></Notice>;
  const tabs = [{ id: 'overview', label: 'Genel bakış' }, { id: 'documents', label: 'Dosyalar', count: matter.documents?.length || 0 }, { id: 'facts', label: 'Olgular', count: matter.facts?.length || 0 }, { id: 'practice', label: 'Çalışma notları' }, { id: 'research', label: 'Araştırma', count: matter.products?.length || 0 }, { id: 'comments', label: 'Yorumlar' }];
  return <>
    <a href="#/matters" className="back-link"><Icon name="arrow" size={16} />Tüm çalışma alanları</a>
    <PageHeader eyebrow={DOMAIN_LABELS[matter.domain] || matter.domain} title={matter.title} action={<Badge status={matter.status} />} />
    <div className="matter-context"><span><Icon name="clock" size={15} />{formatDate(matter.created_at)}</span>{matter.stage && <span>{matter.stage}</span>}{matter.relevant_date && <span>İlgili tarih: {formatDate(matter.relevant_date)}</span>}</div>
    <nav className="tabs" aria-label="Çalışma alanı bölümleri">{tabs.map((item) => <button key={item.id} type="button" aria-current={tab === item.id ? 'page' : undefined} className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)}>{item.label}{item.count !== undefined && <span className="count">{item.count}</span>}</button>)}</nav>
    {tab === 'overview' && <div className="overview-layout"><section><div className="section-heading"><h2>Çalışma özeti</h2><span className="eyebrow">ÇALIŞMA BRİFİ</span></div><WorkspaceCustomers workspace={matter} onChange={reload} /><div className="objective-block"><h3>Amaç</h3><p>{matter.objective || 'Çalışma amacı belirtilmedi.'}</p></div><dl className="definition-grid"><div><dt>Hukuk alanı</dt><dd>{DOMAIN_LABELS[matter.domain] || matter.domain}</dd></div><div><dt>Temsil edilen taraf</dt><dd>{matter.represented_party || 'Belirtilmedi'}</dd></div><div><dt>Süreç aşaması</dt><dd>{matter.stage || 'Belirtilmedi'}</dd></div><div><dt>İlgili tarih</dt><dd>{formatDate(matter.relevant_date)}</dd></div></dl><Detail title="Hazırlık ve inceleme durumu"><div className="coverage-lines"><div><span>Belgeler</span><strong>{matter.documents?.length || 0}</strong></div><div><span>Kaydedilmiş olgular</span><strong>{matter.facts?.length || 0}</strong></div><div><span>Hazırlık çıktıları</span><strong>{matter.products?.length || 0}</strong></div></div><p className="small muted">Bu sayılar içerik doğruluğunu veya hukuki yeterliliği göstermez. Her çıktının kaynakları ve inceleme durumu ayrı değerlendirilir.</p></Detail></section><aside className="next-step"><p className="eyebrow">SIRADAKİ ADIM</p><h2>{!matter.documents?.length ? 'Dayanakları ekleyin.' : !matter.facts?.length ? 'Olguları netleştirin.' : 'Sorunuzu belirleyin.'}</h2><p>{!matter.documents?.length ? 'Belge yükledikten sonra çıkarılan pasajları inceleyin. Araştırmanız bu kaynaklara dayanacak.' : !matter.facts?.length ? 'Belgelenmiş olguları, beyanları ve varsayımları birbirinden ayırın.' : 'Hazırlamak istediğiniz çıktıyı tarif edin. Kaynaklar, eksik olgular ve inceleme adımları birlikte sunulur.'}</p><button className="button primary" onClick={() => setTab(!matter.documents?.length ? 'documents' : !matter.facts?.length ? 'facts' : 'research')}>{!matter.documents?.length ? 'Belge ekle' : !matter.facts?.length ? 'Olgu ekle' : 'Araştırmaya geç'}<Icon name="arrow" size={17} /></button></aside></div>}
    {tab === 'documents' && <DocumentsPanel matter={matter} onChange={reload} selectedDocumentId={selectedDocumentId} demo={demo} />}
    {tab === 'comments' && <WorkspaceComments workspaceId={matterId} />}
    {tab === 'facts' && <FactsPanel matter={matter} onChange={reload} />}
    {tab === 'practice' && <PracticePanel matter={matter} onChange={reload} userRole={userRole} permissions={permissions} />}
    {tab === 'research' && <ResearchPanel matter={matter} onChange={reload} demo={demo} />}
  </>;
}
