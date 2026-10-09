import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { request } from '../api';
import type { Customer, Matter, PortfolioFilters } from '../types';
import { messageOf } from '../utils';

export const EMPTY_FILTERS: PortfolioFilters = { customer_ids: [], date_from: '', date_to: '', date_field: 'created_at' };
export function workspaceQuery(filters: PortfolioFilters) {
  const query = new URLSearchParams({ date_field: filters.date_field });
  if (filters.customer_ids.length) query.set('customer_ids', [...new Set(filters.customer_ids)].join(','));
  if (filters.date_from) query.set('date_from', filters.date_from);
  if (filters.date_to) query.set('date_to', filters.date_to);
  return query.toString();
}
interface PortfolioState {
  customers: Customer[]; workspaces: Matter[]; filters: PortfolioFilters; loading: boolean; error: string; revision: number;
  setFilters: (filters: PortfolioFilters | ((previous: PortfolioFilters) => PortfolioFilters)) => void;
  refresh: () => void;
}
const PortfolioContext = createContext<PortfolioState | null>(null);
export function PortfolioProvider({ children, enabled = true }: { children: ReactNode; enabled?: boolean }) {
  const [customers, setCustomers] = useState<Customer[]>([]); const [workspaces, setWorkspaces] = useState<Matter[]>([]);
  const [filters, setFilters] = useState<PortfolioFilters>(EMPTY_FILTERS); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => { window.addEventListener('portfolio-updated', refresh); return () => window.removeEventListener('portfolio-updated', refresh); }, [refresh]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    if (!enabled) { setCustomers([]); setWorkspaces([]); setLoading(false); return; }
    if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) { setError('Başlangıç tarihi bitiş tarihinden sonra olamaz.'); setWorkspaces([]); setLoading(false); return; }
    Promise.all([request<Customer[]>('/customers', { signal: controller.signal }), request<Matter[]>(`/workspaces?${workspaceQuery(filters)}`, { signal: controller.signal })])
      .then(([customerData, workspaceData]) => { if (!controller.signal.aborted) { setCustomers(customerData); setWorkspaces(workspaceData); } })
      .catch(cause => { if (!controller.signal.aborted) { setError(messageOf(cause)); setCustomers([]); setWorkspaces([]); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filters, revision, enabled]);
  const value = useMemo(() => ({ customers, workspaces, filters, setFilters, loading, error, revision, refresh }), [customers, workspaces, filters, loading, error, revision, refresh]);
  return <PortfolioContext.Provider value={value}>{children}</PortfolioContext.Provider>;
}
export function usePortfolio() { const value = useContext(PortfolioContext); if (!value) throw new Error('Portfolio provider required'); return value; }
export function safeAppHref(value: string | undefined): string | null {
  if (!value || !/^#?\/(matters|workspaces|customers|graphs|coverage|system)(?:[/?]|$)/.test(value) || /[\r\n\\]/.test(value)) return null;
  return value.startsWith('#') ? value : `#${value}`;
}
