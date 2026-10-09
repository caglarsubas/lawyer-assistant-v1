import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { latestSubmission, workTime, type WorkResponse } from './workflowTypes';
import HumanWorkPanel from './HumanWorkPanel';
import WorkQueuePage from './WorkQueuePage';
import { PortfolioProvider, safeAppHref } from '../workbench/portfolio';

describe('human work boundaries', () => {
  it('displays explicit Istanbul wall time across a UTC day boundary', () => {
    expect(workTime('2026-10-09T21:30:00Z')).toContain('10 Eki 2026');
    expect(workTime('2026-10-09T21:30:00Z')).toContain('00:30');
  });
  it('selects the latest submission independently of later review events', () => {
    const response = { history: [
      { id: 'first', action: 'submitted' }, { id: 'review', action: 'reviewed' },
      { id: 'second', action: 'submitted' }, { id: 'accepted', action: 'reviewed' },
    ] } as WorkResponse;
    expect(latestSubmission(response)?.id).toBe('second');
    expect(latestSubmission({ history: [] } as unknown as WorkResponse)).toBeUndefined();
  });
  it('renders human/manual boundaries before any private work response arrives', () => {
    const markup = renderToStaticMarkup(<HumanWorkPanel matterId="synthetic" />);
    expect(markup).toContain('İş ve görüş takibi');
    expect(markup).toContain('hukuki süre hesabı');
    expect(markup).not.toContain('Görüşümü incelemeye gönder');
    expect(markup).not.toContain('İş kaydını aç');
  });
  it('separates personal and supervisory queues and explains date filtering', () => {
    const markup = renderToStaticMarkup(<PortfolioProvider><WorkQueuePage /></PortfolioProvider>);
    expect(markup).toContain('Bana atananlar');
    expect(markup).toContain('Gözetmen olduğum dosyalar');
    expect(markup).toContain('çalışma alanı tarihine');
    expect(safeAppHref('#/work')).toBe('#/work');
    expect(safeAppHref('#/work-not-permitted')).toBeNull();
  });
});
