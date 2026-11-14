import { Badge, Detail } from '../../components';
import type { Product } from '../../types';
import { formatDate } from '../../utils';

export function ResearchOutputPicker({ products, selectedId, onSelect }: {
  products: Product[]; selectedId: string; onSelect: (id: string) => void;
}) {
  if (products.length < 2) return null;
  return <Detail title={`Kayıtlı çıktılar (${products.length})`} open>
    <p className="small muted">Başlığı, sürümü ve inceleme durumunu karşılaştırarak bir çıktı seçin.</p>
    <ul className="research-output-list" aria-label="Kayıtlı hazırlık çıktıları">{products.map(item => <li key={item.id}>
      <button type="button" aria-pressed={item.id === selectedId} onClick={() => onSelect(item.id)}>
        <span><strong>{item.title}</strong><span className="small muted">Sürüm {item.version} · {formatDate(item.created_at, true)}</span></span>
        <span><Badge status={item.status} />{item.id === selectedId && <span className="small">Seçili</span>}</span>
      </button>
    </li>)}</ul>
  </Detail>;
}
