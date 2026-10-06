import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ResearchPanel from './ResearchPanel';
import type { Matter } from '../../types';
import { isRunning, statusLabel } from '../../utils';

function render(status: string) {
  const matter = { id: 'synthetic', research_runs: [{ id: 'job', question: 'Synthetic question', status, created_at: '2026-10-06T00:00:00Z' }] } as Matter;
  return renderToStaticMarkup(<ResearchPanel matter={matter} onChange={async () => {}} demo />);
}

describe('research cancellation acknowledgement', () => {
  it('keeps polling and shows a disabled stop control until execution exits', () => {
    expect(isRunning('cancelling')).toBe(true);
    const html = render('cancelling');
    expect(html).toContain('Devam eden işlemin bitmesi bekleniyor');
    expect(html).toContain('disabled="">Durduruluyor…');
    expect(html).not.toContain('İptal edildi');
  });
  it.each(['cancelled', 'timed_out', 'interrupted'])('stops polling %s and labels the result', (status) => {
    expect(isRunning(status)).toBe(false);
    const html = render(status);
    expect(html).toContain(statusLabel(status));
    expect(html).not.toContain('İptal et');
    expect(html).not.toContain('Devam eden işlemin');
  });
});
