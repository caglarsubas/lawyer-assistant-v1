import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import OriginalPreview, { previewKind } from './OriginalPreview';
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
