export type Frame = 'navigation' | 'main' | 'assistant';
export interface Layout { left: number; right: number; collapsed: Frame[] }
export const DEFAULT_LAYOUT: Layout = { left: 286, right: 350, collapsed: [] };
export const FRAMES: Frame[] = ['navigation', 'main', 'assistant'];
export function sanitizeLayout(value: unknown): Layout {
  if (!value || typeof value !== 'object') return { ...DEFAULT_LAYOUT, collapsed: [] };
  const input = value as Partial<Layout>;
  const clamp = (number: unknown, fallback: number) => typeof number === 'number' && Number.isFinite(number) ? Math.max(240, Math.min(600, number)) : fallback;
  return { left: clamp(input.left, DEFAULT_LAYOUT.left), right: clamp(input.right, DEFAULT_LAYOUT.right), collapsed: Array.isArray(input.collapsed) ? [...new Set(input.collapsed.filter(frame => FRAMES.includes(frame)))] : [] };
}
