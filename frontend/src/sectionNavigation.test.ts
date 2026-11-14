import { afterEach, describe, expect, it, vi } from 'vitest';
import { focusSection } from './components';

afterEach(() => vi.unstubAllGlobals());
describe('section navigation preserves surrounding panes', () => {
  it('focuses the section without scrolling the document or changing the route', () => {
    const pane = { scrollTop: 100, getBoundingClientRect: () => ({ top: 120 }), scrollTo: vi.fn() };
    const target = { focus: vi.fn(), closest: vi.fn(() => pane), getBoundingClientRect: () => ({ top: 300 }), scrollIntoView: vi.fn() };
    vi.stubGlobal('document', { getElementById: vi.fn(() => target) });
    focusSection('synthetic-section');
    expect(target.focus).toHaveBeenCalledWith({ preventScroll: true });
    expect(target.closest).toHaveBeenCalledWith('.frame-content');
    expect(pane.scrollTo).toHaveBeenCalledWith({ top: 256, behavior: 'auto' });
    expect(target.scrollIntoView).not.toHaveBeenCalled();
  });
  it('leaves the current view untouched when the target has been removed', () => {
    const lookup = vi.fn(() => null); vi.stubGlobal('document', { getElementById: lookup });
    expect(() => focusSection('removed-section')).not.toThrow();
    expect(lookup).toHaveBeenCalledWith('removed-section');
  });
});
