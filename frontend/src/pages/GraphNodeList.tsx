import { Badge, Empty, Icon } from '../components';
import type { GraphNode } from '../types';
import { statusLabel } from '../utils';

export function GraphNodeList({ nodes, selected, onSelect }: { nodes: GraphNode[]; selected?: string; onSelect: (node: GraphNode) => void }) {
  return <div className="graph-record-list"><p className="small muted">Haritadaki aynı kayıtlar gösterilir. Ayrıntılar için bir kayıt seçin; liste görünümü kapsamı genişletmez.</p><ul>{nodes.map(node => <li key={node.id}><button type="button" aria-pressed={selected === node.id} onClick={() => onSelect(node)}><span><strong>{node.label}</strong><span className="graph-record-kind">{statusLabel(node.type)}</span></span><Badge status={node.review_status} /><Icon name="arrow" size={16} /></button></li>)}</ul></div>;
}

export function GraphEmpty({ graph, unavailable, onRetry }: { graph: 'structure' | 'jurisprudence'; unavailable: boolean; onRetry: () => void }) {
  return <Empty title={unavailable ? 'Graf kayıtları şu anda okunamıyor.' : graph === 'jurisprudence' ? 'Bu kapsamda karar bağlantısı yok.' : 'Bu aramada bağlantı bulunamadı.'} action={unavailable ? <button className="button secondary" onClick={onRetry}>Yeniden dene</button> : undefined}>
    {unavailable ? 'Hizmet veya sürüm doğrulaması tamamlanamadı. Bu durum, kayıt ya da emsal bulunmadığı anlamına gelmez. Sistem durumu ekranından bağlantıyı denetleyebilirsiniz.' : graph === 'jurisprudence' ? 'Yayımlanmış kararlar ve incelenmiş ilişkiler eklendiğinde burada görünür. Boş görünüm, emsal olmadığı anlamına gelmez.' : 'Aramayı genişletin veya başka bir hukuk dalı seçin. Katalog kapsamı ile hukuki geçerlilik farklı değerlendirilir.'}
  </Empty>;
}
