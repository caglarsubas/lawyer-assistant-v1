import { useId, useState, type ReactNode } from 'react';
import { Detail, Icon } from './components';

/** Presentation only: never normalize, trim, truncate or rewrite the saved text. */
export function SourceExcerpt({ name, location, text, label, onOpen, actionLabel = 'Özgün pasajı aç', metadata, metadataTitle = 'Sürüm ve alıntı bilgileri' }: {
  name: string; location: string; text?: string; label?: string; onOpen?: () => void;
  actionLabel?: string; metadata?: ReactNode; metadataTitle?: string;
}) {
  const id = useId();
  const [layout, setLayout] = useState<'flow' | 'original'>('flow');
  return <article className="source-excerpt" aria-labelledby={`${id}-title`}>
    <header className="source-excerpt-header">
      <Icon name="file" size={21} />
      <div><h4 id={`${id}-title`}>{name}</h4><p>{label && <span>{label} · </span>}{location}</p></div>
      {onOpen && <button type="button" className="button secondary" onClick={onOpen}>{actionLabel}<Icon name="external" size={15} /></button>}
    </header>
    {text !== undefined && <>
      <div className="quote-toolbar"><span>Kaydedilen alıntı</span><div role="group" aria-label={`Alıntı görünümü: ${name} · ${location}`}>
        <button type="button" aria-pressed={layout === 'flow'} onClick={() => setLayout('flow')}>Okuma görünümü</button>
        <button type="button" aria-pressed={layout === 'original'} onClick={() => setLayout('original')}>Özgün satırlar</button>
      </div></div>
      <blockquote className={`source-quotation ${layout}`} aria-describedby={`${id}-layout`}>{text}</blockquote>
      <p className="quote-layout-note" id={`${id}-layout`}>{layout === 'flow' ? 'Yalnızca satır düzeni akışa uyarlandı; alıntı metni değiştirilmedi.' : 'Kaydedilen metin, satır sonları ve boşluklarıyla gösteriliyor.'}</p>
    </>}
    {metadata && <Detail title={metadataTitle} variant="technical">{metadata}</Detail>}
  </article>;
}
