import PortfolioNavigation from './PortfolioNavigation';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { DEFAULT_LAYOUT, sanitizeLayout } from './layout';
import { EMPTY_FILTERS, PortfolioProvider, safeAppHref, workspaceQuery } from './portfolio';
import Workbench from './Workbench';
import { formatDate } from '../utils';

describe('workbench boundaries', () => {
  it('keeps all selected customers in one OR query, with explicit date semantics', () => {
    const query = new URLSearchParams(workspaceQuery({ customer_ids: ['c1', 'c2', 'c1'], date_field: 'updated_at', date_from: '2026-10-01', date_to: '2026-10-04' }));
    expect(query.get('customer_ids')).toBe('c1,c2');
    expect(query.get('date_field')).toBe('updated_at');
    expect(query.get('date_from')).toBe('2026-10-01');
    expect(query.get('date_to')).toBe('2026-10-04');
    expect(new URLSearchParams(workspaceQuery(EMPTY_FILTERS)).has('customer_ids')).toBe(false);
  });
  it('persists only bounded layout data even if saved storage contains private fields', () => {
    expect(sanitizeLayout({ left: 9000, right: -10, collapsed: ['main', 'main', 'unknown'], customer_ids: ['private-client'], question: 'secret' })).toEqual({ left: 600, right: 240, collapsed: ['main'] });
    expect(sanitizeLayout(null)).toEqual(DEFAULT_LAYOUT);
    expect(sanitizeLayout({ left: NaN, right: Infinity })).toEqual(DEFAULT_LAYOUT);
  });
  it('permits only local application links from assistant output', () => {
    expect(safeAppHref('/matters/w1?tab=comments')).toBe('#/matters/w1?tab=comments');
    expect(safeAppHref('#/customers')).toBe('#/customers');
    for (const unsafe of ['javascript:alert(1)', 'https://external.invalid', '//external.invalid', '/api/v1/secrets', '/matters\\evil', '/matters\n', '/matters-invalid']) expect(safeAppHref(unsafe)).toBeNull();
  });
  it('aligns displayed timestamps with Turkey calendar filtering, preserving date-only values', () => {
    expect(formatDate('2026-10-03T22:30:00Z')).toBe(formatDate('2026-10-04'));
    expect(formatDate('2026-10-03T20:30:00Z')).toBe(formatDate('2026-10-03'));
    expect(formatDate('2026-01-01')).toContain('2026');
  });
  it('renders three independent panels, accessible horizontal splitters, restore controls and narrow-screen navigation', () => {
    const markup = renderToStaticMarkup(<PortfolioProvider><Workbench session={{ user: { id: 'u1', name: 'Avukat', role: 'lawyer', firm_id: 'f1' }, csrf_token: '', demo_mode: false }} signingOut={false} onSignOut={() => undefined} page="matters" workspaceId={null} section="overview" demo={false}><p>Çalışma içeriği</p></Workbench></PortfolioProvider>);
    for (const frame of ['navigation', 'main', 'assistant']) expect(markup).toContain(`id="frame-${frame}"`);
    expect(markup.match(/role="separator"/g)).toHaveLength(2);
    expect(markup.match(/aria-orientation="vertical"/g)).toHaveLength(2);
    expect(markup).toContain('aria-label="Panel seçimi"');
    expect(markup).toContain('aria-label="Hukuk asistanı tam ekran"');
    expect(markup).toContain('aria-label="Çalışma alanı panelini daralt"');
    expect(markup).toContain('maxLength="2000"');
  });
});


describe('configuration-only portfolio navigation', () => {
  it('offers administration without private portfolio filters or creation links', () => {
    const markup = renderToStaticMarkup(<PortfolioProvider enabled={false}><PortfolioNavigation page="firm-admin" workspaceId={null} permissions={['firm.manage', 'system.read']} /></PortfolioProvider>);
    expect(markup).toContain('Büro yönetimi');
    expect(markup).not.toContain('Portföy filtresi');
    expect(markup).not.toContain('Yeni çalışma alanı');
    expect(markup).not.toContain('Müvekkil ekle');
  });
});
