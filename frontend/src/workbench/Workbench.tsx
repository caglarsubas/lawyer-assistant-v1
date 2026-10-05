import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { Icon, Mark } from '../components';
import type { Session } from '../types';
import AssistantPanel from './AssistantPanel';
import PortfolioNavigation from './PortfolioNavigation';
import { DEFAULT_LAYOUT, FRAMES, sanitizeLayout, type Frame, type Layout } from './layout';
const LABELS: Record<Frame, string> = { navigation: 'Gezinme', main: 'Çalışma alanı', assistant: 'Hukuk asistanı' };
const STORAGE_KEY = 'lawyer-assistant:panel-layout:v1';
function readLayout() { try { return sanitizeLayout(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')); } catch { return DEFAULT_LAYOUT; } }
export default function Workbench({ children, session, signingOut, onSignOut, page, workspaceId, section, demo }: { children: ReactNode; session: Session; signingOut: boolean; onSignOut: () => void; page: string; workspaceId: string | null; section: string; demo: boolean }) {
  const [layout, setLayout] = useState<Layout>(readLayout); const [focus, setFocus] = useState<Frame | null>(null); const [mobile, setMobile] = useState<Frame>('main');
  const grid = useRef<HTMLDivElement>(null); const restoreFocus = useRef<HTMLElement | null>(null);
  useEffect(() => { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeLayout(layout))); } catch { /* Layout works when browser storage is disabled. */ } }, [layout]);
  useEffect(() => { const escape = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape' && focus) { setFocus(null); restoreFocus.current?.focus(); } }; window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape); }, [focus]);
  useEffect(() => { setMobile('main'); }, [workspaceId, page, section]);
  useEffect(() => {
    if (!grid.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width;
      if (width <= 960) return;
      setLayout(previous => {
        const available = width - (previous.collapsed.includes('main') ? 46 : 330) - 16;
        const left = previous.collapsed.includes('navigation') ? 46 : previous.left;
        const right = previous.collapsed.includes('assistant') ? 46 : previous.right;
        if (left + right <= available) return previous;
        const nextRight = previous.collapsed.includes('assistant') ? previous.right : Math.max(240, Math.min(previous.right, available - left));
        const nextLeft = previous.collapsed.includes('navigation') ? previous.left : Math.max(240, Math.min(previous.left, available - (previous.collapsed.includes('assistant') ? 46 : nextRight)));
        return nextLeft === previous.left && nextRight === previous.right ? previous : { ...previous, left: nextLeft, right: nextRight };
      });
    });
    observer.observe(grid.current); return () => observer.disconnect();
  }, []);

  function collapse(frame: Frame) { setLayout(previous => ({ ...previous, collapsed: previous.collapsed.includes(frame) ? previous.collapsed.filter(value => value !== frame) : [...previous.collapsed, frame] })); }
  function maximize(frame: Frame) { if (focus === frame) { setFocus(null); restoreFocus.current?.focus(); } else { restoreFocus.current = document.activeElement as HTMLElement; setFocus(frame); setMobile(frame); requestAnimationFrame(() => document.getElementById(`focus-${frame}`)?.focus()); } }
  function resize(side: 'left' | 'right', value: number) {
    const width = grid.current?.clientWidth || 1440;
    setLayout(previous => { const other = side === 'left' ? (previous.collapsed.includes('assistant') ? 46 : previous.right) : (previous.collapsed.includes('navigation') ? 46 : previous.left); const minimumMain = previous.collapsed.includes('main') ? 46 : 330; const maximum = Math.max(240, Math.min(600, width - other - minimumMain - 16)); return { ...previous, [side]: Math.max(240, Math.min(maximum, value)) }; });
  }
  function drag(event: PointerEvent<HTMLDivElement>, side: 'left' | 'right') {
    if (event.button !== 0) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    const start = event.clientX; const initial = layout[side]; const target = event.currentTarget;
    const move = (next: globalThis.PointerEvent) => resize(side, initial + (side === 'left' ? next.clientX - start : start - next.clientX));
    const end = () => { target.removeEventListener('pointermove', move); target.removeEventListener('pointerup', end); target.removeEventListener('pointercancel', end); };
    target.addEventListener('pointermove', move); target.addEventListener('pointerup', end); target.addEventListener('pointercancel', end);
  }
  function resizeKey(event: KeyboardEvent<HTMLDivElement>, side: 'left' | 'right') {
    const direction = side === 'left' ? 1 : -1;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); resize(side, layout[side] + (event.key === 'ArrowRight' ? 24 : -24) * direction); }
    else if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); resize(side, event.key === 'Home' ? 240 : 600); }
  }
  const style = { '--left-size': `${layout.collapsed.includes('navigation') ? 46 : layout.left}px`, '--right-size': `${layout.collapsed.includes('assistant') ? 46 : layout.right}px` } as CSSProperties;
  function frame(frameId: Frame, content: ReactNode) {
    const collapsed = layout.collapsed.includes(frameId) && focus !== frameId;
    return <section id={`frame-${frameId}`} aria-label={LABELS[frameId]} key={frameId} className={`workbench-frame frame-${frameId} ${collapsed ? 'frame-collapsed' : ''} ${focus && focus !== frameId ? 'frame-hidden' : ''} ${mobile === frameId ? 'mobile-active' : ''}`}>
      {collapsed ? <div className="collapsed-rail"><button onClick={() => collapse(frameId)} aria-label={`${LABELS[frameId]} panelini aç`} title={`${LABELS[frameId]} panelini aç`}><Icon name={frameId === 'navigation' ? 'folder' : frameId === 'main' ? 'book' : 'graph'} size={18} /><span>{LABELS[frameId]}</span></button><button className="icon-button" onClick={() => maximize(frameId)} aria-label={`${LABELS[frameId]} tam ekran`} title="Tam ekran">⛶</button></div> : <><header className="frame-heading"><div><span className="frame-index">{frameId === 'navigation' ? '01' : frameId === 'main' ? '02' : '03'}</span><h2>{LABELS[frameId]}</h2></div><div className="frame-controls"><button className="icon-button" id={`focus-${frameId}`} onClick={() => maximize(frameId)} aria-label={`${LABELS[frameId]} ${focus === frameId ? 'normal görünüme dön' : 'tam ekran'}`} title={focus === frameId ? 'Normal görünüm (Esc)' : 'Tam ekran'}>{focus === frameId ? '↙' : '⛶'}</button><button className="icon-button" onClick={() => { if (focus === frameId) setFocus(null); collapse(frameId); }} aria-label={`${LABELS[frameId]} panelini daralt`} title="Paneli daralt">−</button></div></header></> }<div className="frame-content" hidden={collapsed}>{content}</div>
    </section>;
  }
  return <div className="workbench"><a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); setFocus(null); setMobile('main'); setLayout(previous => ({ ...previous, collapsed: previous.collapsed.filter(frame => frame !== 'main') })); requestAnimationFrame(() => document.getElementById('main-content')?.focus()); }}>İçeriğe geç</a><header className="workbench-topbar"><a className="brand" href="#/matters"><Mark /><span>Hukuk<span className="brand-sub">Asistanı</span></span></a><span className="workbench-tagline">Müvekkiller · Çalışma alanları · Dosyalar</span><div className="user-menu"><span className="local-status"><span />Kurum içi</span><span className="user-avatar" aria-hidden="true">{session.user.name?.charAt(0)?.toLocaleUpperCase('tr') || 'A'}</span><span className="user-name">{session.user.name}</span><button className="icon-button" type="button" onClick={onSignOut} disabled={signingOut} aria-label="Oturumu kapat" title="Oturumu kapat"><Icon name="logout" size={17} /></button></div></header>
    {demo && <div className="demo-ribbon"><span className="demo-dot" /><span>Geliştirme önizlemesi · Örnek çıktılar hukuki görüş değildir. Gerçek müvekkil verisi kullanmayın.</span></div>}
    <nav className="mobile-frame-tabs" aria-label="Panel seçimi">{FRAMES.map(frameId => <button key={frameId} className={mobile === frameId ? 'active' : ''} aria-pressed={mobile === frameId} onClick={() => { setMobile(frameId); setFocus(null); setLayout(previous => ({ ...previous, collapsed: previous.collapsed.filter(frame => frame !== frameId) })); }}>{LABELS[frameId]}</button>)}</nav>
    <div ref={grid} className={`workbench-grid ${focus ? 'has-focus' : ''} ${layout.collapsed.includes('main') ? 'main-collapsed' : ''}`} style={style}>
      {frame('navigation', <PortfolioNavigation page={page} workspaceId={workspaceId} />)}
      <div className={`panel-resizer ${focus || layout.collapsed.includes('navigation') ? 'resizer-hidden' : ''}`} role="separator" tabIndex={0} aria-label="Gezinme ve çalışma alanı genişliğini ayarla" aria-orientation="vertical" aria-valuemin={240} aria-valuemax={600} aria-valuenow={layout.left} aria-controls="frame-navigation frame-main" onPointerDown={event => drag(event, 'left')} onKeyDown={event => resizeKey(event, 'left')} />
      {frame('main', <main id="main-content" tabIndex={-1} className="main-content">{children}</main>)}
      <div className={`panel-resizer ${focus || layout.collapsed.includes('assistant') ? 'resizer-hidden' : ''}`} role="separator" tabIndex={0} aria-label="Çalışma alanı ve asistan genişliğini ayarla" aria-orientation="vertical" aria-valuemin={240} aria-valuemax={600} aria-valuenow={layout.right} aria-controls="frame-main frame-assistant" onPointerDown={event => drag(event, 'right')} onKeyDown={event => resizeKey(event, 'right')} />
      {frame('assistant', <AssistantPanel workspaceId={workspaceId} page={page} section={section} />)}
    </div>
  </div>;
}
