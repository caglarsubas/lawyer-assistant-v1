import { lazy, Suspense, useEffect, useState, type FormEvent } from 'react';
import { onUnauthorized, post, request, setCsrfToken } from './api';
import { Icon, Loading, Mark, Notice } from './components';
import type { Bootstrap, Session, SystemStatus } from './types';
import { messageOf } from './utils';
const FirmAdminPage = lazy(() => import('./pages/FirmAdminPage'));
import MattersPage from './pages/MattersPage';
import MatterPage from './pages/MatterPage';
import GraphPage from './pages/GraphPage';
import CoveragePage from './pages/CoveragePage';
import SystemPage from './pages/SystemPage';
import CustomersPage from './pages/CustomersPage';
import SourceReviewPage from './pages/SourceReviewPage';
import ProvisionMappingPage from './pages/ProvisionMappingPage';
import { PortfolioProvider } from './workbench/portfolio';
import Workbench from './workbench/Workbench';

function currentRoute() { return window.location.hash.slice(1) || '/matters'; }
export function navigate(path: string) { window.location.hash = path; }

export default function App() {
  const [route, setRoute] = useState(currentRoute);
  const [session, setSession] = useState<Session | null>(null);
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState('');
  const [signingOut, setSigningOut] = useState(false);
  useEffect(() => { const update = () => { setRoute(currentRoute()); window.scrollTo(0, 0); }; window.addEventListener('hashchange', update); return () => window.removeEventListener('hashchange', update); }, []);
  useEffect(() => {
    let alive = true;
    onUnauthorized(() => { setSession(null); setStatus(null); setCsrfToken(''); setError('Oturumunuz sona erdi. Lütfen yeniden giriş yapın.'); });
    Promise.allSettled([request<Bootstrap>('/bootstrap'), request<Session>('/auth/me')]).then(([statusResult, sessionResult]) => {
      if (!alive) return;
      if (statusResult.status === 'fulfilled') setBootstrap(statusResult.value);
      if (sessionResult.status === 'fulfilled') { setSession(sessionResult.value); setCsrfToken(sessionResult.value.csrf_token); }
      setBooting(false);
    });
    return () => { alive = false; onUnauthorized(); };
  }, []);
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    request<SystemStatus>('/status', { signal: controller.signal }).then(setStatus).catch((cause) => { if (cause.name !== 'AbortError') setError(messageOf(cause)); });
    return () => controller.abort();
  }, [session]);
  async function signOut() {
    setSigningOut(true); setError('');
    try { await post('/auth/logout', {}); setSession(null); setStatus(null); setCsrfToken(''); } catch (cause) { setError(messageOf(cause)); } finally { setSigningOut(false); }
  }
  if (booting) return <div className="boot"><Mark large /><Loading label="Çalışma alanı hazırlanıyor…" /></div>;
  if (!session) return <Login demo={Boolean(bootstrap?.demo_mode)} initialError={error} onLogin={(value) => { setSession(value); setCsrfToken(value.csrf_token); setError(''); if (value.user.permissions?.includes('firm.manage') && !value.user.permissions.includes('matter.read')) navigate('/firm-admin'); }} />;
  const [pathname, query = ''] = route.split('?');
  const page = pathname.split('/')[1];
  const matterId = ['matters', 'workspaces'].includes(page) && pathname.split('/')[2] ? decodeURIComponent(pathname.split('/')[2]) : null;
  const params = new URLSearchParams(query);
  const section = params.get('tab') || 'overview';
  return <PortfolioProvider key={session.user.id} enabled={!session.user.permissions || session.user.permissions.includes('portfolio.read')}><Workbench session={session} signingOut={signingOut} onSignOut={signOut} page={page} workspaceId={matterId} section={section} demo={Boolean(status?.demo_mode || session.demo_mode)}>
    {error && <Notice error>{error}</Notice>}
    {matterId ? <MatterPage key={matterId} matterId={matterId} tab={section} selectedDocumentId={params.get('document')} userRole={session.user.role} permissions={session.user.permissions} demo={Boolean(status?.demo_mode || session.demo_mode)} /> : page === 'sources' ? pathname.split('/')[3] === 'provisions' ? <ProvisionMappingPage sourceId={pathname.split('/')[2] || ''} user={session.user} /> : <SourceReviewPage sourceId={pathname.split('/')[2] || ''} user={session.user} /> : page === 'firm-admin' ? <Suspense fallback={<Loading label="Büro yönetimi yükleniyor…" />}><FirmAdminPage /></Suspense> : page === 'customers' ? <CustomersPage /> : page === 'graphs' ? <GraphPage /> : page === 'coverage' ? <CoveragePage /> : page === 'system' ? <SystemPage status={status} onStatus={setStatus} /> : <MattersPage newRequested={params.get('new') === '1'} />}
  </Workbench></PortfolioProvider>;

}

function Login({ demo, initialError, onLogin }: { demo: boolean; initialError: string; onLogin: (session: Session) => void }) {
  const [username, setUsername] = useState(''); const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(initialError);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { onLogin(await post<Session>('/auth/login', { username, password })); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  }
  return <div className="login-page"><div className="login-editorial"><a className="brand light" href="#/matters"><Mark /><span>Hukuk<span className="brand-sub">Asistanı</span></span></a><div className="login-statement"><p className="eyebrow">HUKUKİ HAZIRLIK İÇİN</p><h1>Güçlü hazırlık,<br /><em>sağlam dayanak.</em></h1><p>Belgelerinizden hukuki araştırmaya; her adımı izlenebilir, her yorumu denetlenebilir bir çalışma alanı.</p><div className="editorial-rule" /><span>Dosyanız kurum içinde.<br />Değerlendirme sizin elinizde.</span></div><div className="login-edition">TÜRKİYE <span>İLK SÜRÜM · 0.1</span></div></div><div className="login-content"><form className="login-form" onSubmit={submit}><p className="eyebrow">ÇALIŞMA ALANINIZ</p><h2>Hoş geldiniz.</h2><p className="muted">Dosyalarınıza devam etmek için giriş yapın.</p>{error && <Notice error>{error}</Notice>}<div className="field"><label htmlFor="username">Kullanıcı adı</label><input id="username" name="username" autoComplete="username" required autoFocus value={username} onChange={(event) => setUsername(event.target.value)} /></div><div className="field"><label htmlFor="password">Parola</label><input id="password" name="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></div><button className="button primary full" disabled={busy}>{busy ? 'Giriş yapılıyor…' : 'Çalışma alanına gir'}<Icon name="arrow" size={18} /></button>{demo && <details className="demo-login"><summary>Demo erişim bilgileri</summary><p>Bu kurulum geliştirme modundadır.</p><dl><div><dt>Kullanıcı adı</dt><dd>demo</dd></div><div><dt>Parola</dt><dd>demo-local-only</dd></div></dl><button className="text-button" type="button" onClick={() => { setUsername('demo'); setPassword('demo-local-only'); }}>Demo bilgilerini doldur<Icon name="arrow" size={16} /></button></details>}<div className="login-security"><Icon name="shield" size={17} /><span>Kurum içi hizmet · Oturum koruması</span></div></form></div></div>;
}
