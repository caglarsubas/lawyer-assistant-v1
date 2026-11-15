import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import OriginalPreview, { previewKind } from './OriginalPreview';
import { ExtractedDocumentText } from './DocumentsPanel';
import type { DocumentRecord } from '../../types';

describe('original source formats', () => {
  it('uses the actual final extension for PDF names containing an Office extension', () => {
    expect(previewKind({ name: 'Çağlar Geçiş.docx (1).PDF' })).toBe('pdf');
    expect(previewKind({ name: 'sözleşme.docx' })).toBe('docx');
    expect(previewKind({ name: 'imza.PNG' })).toBe('image');
    expect(previewKind({ name: 'kaynak.html' })).toBe('text');
    expect(previewKind({ name: 'hesap.xlsx' })).toBe('unsupported');
  });

  it('explains unavailable previews without substituting extracted text for the original', () => {
    const document = { id: 'd1', name: 'hesap.xlsx', passages: [{ id: 'p1', text: 'extracted-only', locator: {} }] } as DocumentRecord;
    const markup = renderToStaticMarkup(<OriginalPreview matterId="m1" document={document} />);
    expect(markup).toContain('Özgün dosyayı indirerek');
    expect(markup).not.toContain('extracted-only');
  });
});

describe('extracted DOCX passage warnings', () => {
  it('binds only the exact locator and retains an unmatched warning', () => {
    const warning = 'İzlenen değişiklik var; özgün pasajı inceleyin.';
    const unbound = `Paragraf 11: ${warning}`;
    const document = {
      id: 'docx',
      name: 'sentetik.DOCX',
      passages: [
        { id: 'first', locator: 'Paragraf 1', text: 'Ödeme metni.' },
        { id: 'tenth', locator: 'Paragraf 10', text: 'Teslim metni.' },
      ],
      extraction_warnings: ['İzlenen değişiklikler var.', `Paragraf 1: ${warning}`, unbound],
    } as DocumentRecord;
    const markup = renderToStaticMarkup(<ExtractedDocumentText document={document} highlightPassageId="first" />);
    const first = markup.match(/<article id="passage-first"[^>]*>.*?<\/article>/)?.[0];
    const tenth = markup.match(/<article id="passage-tenth"[^>]*>.*?<\/article>/)?.[0];
    expect(first).toContain(`class="passage-warning">${warning}`);
    expect(first).toContain('Ödeme metni.');
    expect(first).toContain('Seçili dayanak');
    expect(tenth).toContain('Teslim metni.');
    expect(tenth).not.toContain('passage-warning');
    expect(markup).toContain(`<li>${unbound}</li>`);
    expect(markup).toContain('<li>İzlenen değişiklikler var.</li>');
    expect(markup).not.toContain(`<li>Paragraf 1: ${warning}</li>`);
  });
});
