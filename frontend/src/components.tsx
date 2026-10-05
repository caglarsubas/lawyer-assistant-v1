import { useId, type ReactNode } from 'react';
import { statusLabel } from './utils';

type IconName = 'folder' | 'graph' | 'layers' | 'settings' | 'arrow' | 'plus' | 'upload' | 'file' | 'check' | 'close' | 'search' | 'download' | 'chevron' | 'logout' | 'shield' | 'clock' | 'edit' | 'external' | 'book';
const paths: Record<IconName, ReactNode> = {
  folder: <path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" />,
  graph: <><circle cx="5" cy="6" r="2" /><circle cx="19" cy="5" r="2" /><circle cx="12" cy="18" r="2" /><path d="m7 6 10-1M6 8l5 8m7-9-5 9" /></>,
  layers: <><path d="m12 3 10 5-10 5L2 8l10-5Zm-9 9 9 5 9-5M3 16l9 5 9-5" /></>,
  settings: <><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="8" cy="6" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="10" cy="18" r="2" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" /></>,
  file: <><path d="M14 2H5v20h14V7l-5-5Zm0 0v6h5M8 12h8m-8 4h6" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  search: <><circle cx="10" cy="10" r="6" /><path d="m15 15 6 6" /></>,
  download: <><path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4" /></>,
  chevron: <path d="m9 5 7 7-7 7" />,
  logout: <><path d="M9 3H4v18h5M9 12h12m-5-5 5 5-5 5" /></>,
  shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 6v6l4 2" /></>,
  edit: <><path d="m15 3 6 6M3 21l5-1L21 7l-4-4L4 16l-1 5Z" /></>,
  external: <><path d="M14 3h7v7M21 3 10 14M10 4H3v17h17v-7" /></>,
  book: <><path d="M12 5v16M3 3c4 0 7 0 9 3 2-3 5-3 9-3v16c-4 0-7 0-9 2-2-2-5-2-9-2V3Z" /></>,
};
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
export function Mark({ large = false }: { large?: boolean }) { return <span className={`brand-mark ${large ? 'large' : ''}`} aria-hidden="true"><svg viewBox="0 0 40 40"><path d="M12 10v20m16-20v20M12 20h16M17 7h6m-6 26h6" /></svg></span>; }
export function Badge({ status, children }: { status?: string; children?: ReactNode }) {
  const tone = ['approved', 'reviewed', 'completed', 'ready', 'extracted', 'documented'].includes(status || '') ? 'positive' : ['rejected', 'failed', 'stale', 'invalidated', 'disputed'].includes(status || '') ? 'warning' : '';
  return <span className={`badge ${tone}`}>{children || statusLabel(status)}</span>;
}
export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) { return <div className={`notice ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>; }
export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-drawing" aria-hidden="true"><Icon name="book" size={32} /></span><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>;
}
export function Loading({ label = 'Yükleniyor…' }: { label?: string }) { return <div className="loading" role="status"><span className="spinner" />{label}</div>; }
export function Detail({ title = 'Ayrıntılar', children, open }: { title?: string; children: ReactNode; open?: boolean }) { return <details className="details" open={open}><summary>{title}<Icon name="chevron" size={16} /></summary><div className="details-content">{children}</div></details>; }
export function JsonDetails({ value, title = 'Teknik ayrıntılar' }: { value: unknown; title?: string }) { return <Detail title={title}><pre className="data-pre">{JSON.stringify(value, null, 2)}</pre></Detail>; }
export function Field({ label, hint, children, className = '' }: { label: string; hint?: string; children: (id: string) => ReactNode; className?: string }) {
  const id = useId(); return <div className={`field ${className}`}><label htmlFor={id}>{label}</label>{children(id)}{hint && <span className="field-hint">{hint}</span>}</div>;
}
export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <div className="page-action">{action}</div>}</header>;
}
