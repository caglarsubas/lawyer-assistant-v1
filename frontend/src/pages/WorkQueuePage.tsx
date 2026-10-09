import { useEffect, useState } from 'react';
import { request } from '../api';
import { Badge, Empty, Loading, Notice, PageHeader } from '../components';
import { messageOf } from '../utils';
import { usePortfolio } from '../workbench/portfolio';
import { KIND_LABELS, WORK_STATUS, workTime, type WorkItem } from './workflowTypes';
export default function WorkQueuePage() {
  const [view, setView] = useState('personal'); const [bucket, setBucket] = useState('all');
  const [items, setItems] = useState<WorkItem[] | null>(null); const [truncated, setTruncated] = useState(false); const [error, setError] = useState('');
  const { workspaces, filters, loading } = usePortfolio();
  useEffect(() => { const controller = new AbortController(); setItems(null); setError(''); setTruncated(false);
    request<{ items: WorkItem[]; truncated: boolean }>(`/work?view=${view}&bucket=${bucket}`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setItems(value.items); setTruncated(value.truncated); } }).catch(cause => { if (!controller.signal.aborted) { setItems(null); setError(messageOf(cause)); } }); return () => controller.abort();
  }, [view, bucket]);
  const filtered = filters.customer_ids.length > 0 || Boolean(filters.date_from || filters.date_to);
  const visible = items?.filter(item => !filtered || workspaces.some(w => w.id === item.matter_id));
  return <><PageHeader eyebrow="İNSAN İŞ AKIŞI" title="İşlerim ve gözetim" description="Kendi işleriniz ve açıkça gözetmen olduğunuz dosyaların işleri. Tarihler İstanbul saatidir; otomatik hukuki süre hesaplanmaz." />
    <div className="form-grid"><label className="compact-field">Görünüm<select value={view} onChange={e => setView(e.target.value)}><option value="personal">Bana atananlar</option><option value="supervisory">Gözetmen olduğum dosyalar</option></select></label><label className="compact-field">İş durumu<select value={bucket} onChange={e => setBucket(e.target.value)}><option value="all">Tümü</option><option value="upcoming">Yaklaşan / henüz geçmemiş</option><option value="overdue">Tarihi geçen</option><option value="closed">Kapalı</option></select></label></div>
    <p className="small muted">Portföy filtreleri çalışma alanının müvekkilleri ve seçilen çalışma alanı tarihine uygulanır. İşin son tarihi yukarıdaki durum filtresiyle ayrı değerlendirilir.</p>
    {error && <Notice error>{error}</Notice>}{truncated && <Notice>Liste sınırına ulaşıldı. En yeni 1.000 yetkili kayıt içinden en fazla 100 iş gösterilir. Eksik eski işleri görmek için ilgili dosyanın İş takibi bölümünü açın.</Notice>}
    {!items || loading ? !error && <Loading /> : !visible?.length ? <Empty title="Bu görünümde iş bulunamadı.">Atamalar ve filtreler yalnızca mevcut erişim kapsamınızda değerlendirilir.</Empty> : <div className="work-register">{visible.map(item => <article key={item.id}><div><p className="small-label">{KIND_LABELS[item.kind]} · {item.matter_title}</p><h3>{item.title}</h3><p className="small">{workTime(item.due_at)} · İstanbul{item.overdue ? ' · tarihi geçti' : ''}</p><Badge>{WORK_STATUS[item.queue_status || item.status]}</Badge></div><a className="button secondary" href={`#/matters/${encodeURIComponent(item.matter_id)}?tab=workflow&work=${encodeURIComponent(item.id)}`}>Çalışmayı aç</a></article>)}</div>}</>;
}
