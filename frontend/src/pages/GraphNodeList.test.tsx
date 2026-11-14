import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { GraphEmpty, GraphNodeList } from './GraphNodeList';
import type { GraphNode } from '../types';

describe('graph reading and unavailable observations', () => {
  const nodes: GraphNode[] = [
    { id: 'first', label: 'Aynı ada sahip çok uzun sentetik hukuk kavramı', type: 'Concept', graph: 'structure', review_status: 'unreviewed' },
    { id: 'second', label: 'Aynı ada sahip çok uzun sentetik hukuk kavramı', type: 'Concept', graph: 'structure', review_status: 'disputed' },
  ];
  it('retains full labels and selects by identity despite duplicate names', () => {
    const html = renderToStaticMarkup(<GraphNodeList nodes={nodes} selected="second" onSelect={() => {}} />);
    expect(html.split(nodes[0].label)).toHaveLength(3);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('liste görünümü kapsamı genişletmez');
    expect(html).not.toContain('…');
  });
  it('escapes source-supplied labels instead of rendering markup', () => {
    const html = renderToStaticMarkup(<GraphNodeList nodes={[{...nodes[0],label:'<script>sample</script>'}]} onSelect={() => {}} />);
    expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>');
  });
  it.each(['structure', 'jurisprudence'] as const)('distinguishes failed %s access from an empty search', graph => {
    const unavailable = renderToStaticMarkup(<GraphEmpty graph={graph} unavailable onRetry={() => {}} />);
    expect(unavailable).toContain('Graf kayıtları şu anda okunamıyor.');
    expect(unavailable).toContain('Yeniden dene');
    expect(unavailable).not.toContain('Bu aramada bağlantı bulunamadı.');
    const empty = renderToStaticMarkup(<GraphEmpty graph={graph} unavailable={false} onRetry={() => {}} />);
    expect(empty).not.toContain('Yeniden dene');
    expect(empty).toContain(graph === 'structure' ? 'Katalog kapsamı ile hukuki geçerlilik farklı' : 'Boş görünüm, emsal olmadığı anlamına gelmez');
  });
});
