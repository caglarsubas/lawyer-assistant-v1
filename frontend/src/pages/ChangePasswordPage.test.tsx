import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { onUnauthorized, setCsrfToken } from '../api';
import ChangePasswordPage, { passwordProblem, submitPasswordChange } from './ChangePasswordPage';

const fields = { current_password: 'synthetic-current-password', new_password: '  yeni parola Türkçe  ', confirm_password: '  yeni parola Türkçe  ' };
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(''); onUnauthorized(); });

describe('self-service password change', () => {
  it('renders empty password-manager-compatible inputs with a session warning and no account selector', () => {
    const markup = renderToStaticMarkup(<ChangePasswordPage onChanged={() => undefined} />);
    expect(markup.match(/type="password"/g)).toHaveLength(3);
    expect(markup.match(/autoComplete="new-password"/g)).toHaveLength(2);
    expect(markup).toContain('autoComplete="current-password"');
    expect(markup.match(/value=""/g)).toHaveLength(3);
    expect(markup.match(/maxLength="200"/g)).toHaveLength(3);
    expect(markup).toContain('bu oturum dahil');
    expect(markup).toContain('inceleme geçmişiniz korunur');
    expect(markup).toContain('aria-label="Parola değiştirme"');
    expect(markup).not.toContain('name="username"');
    expect(markup).not.toContain('name="user_id"');
  });
  it('sends exact untrimmed credentials only in the authenticated same-origin POST body', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, reauthentication_required: true }), { status: 200 }));
    vi.stubGlobal('fetch', fetch); setCsrfToken('synthetic-csrf');
    await submitPasswordChange(fields);
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe('/api/v1/auth/password');
    expect(options.method).toBe('POST'); expect(options.credentials).toBe('same-origin'); expect(options.cache).toBe('no-store');
    expect(options.headers.get('X-CSRF-Token')).toBe('synthetic-csrf');
    expect(JSON.parse(options.body)).toEqual(fields);
  });
  it('blocks invalid confirmation and weak or unchanged passwords before any request', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    for (const invalid of [
      { ...fields, confirm_password: 'different-long-password' },
      { ...fields, new_password: 'short', confirm_password: 'short' },
      { ...fields, new_password: ' '.repeat(16), confirm_password: ' '.repeat(16) },
      { ...fields, new_password: fields.current_password, confirm_password: fields.current_password },
      { ...fields, current_password: '' },
      { ...fields, new_password: 'x'.repeat(201) },
      { ...fields, current_password: 'secret\ncontrol' },
    ]) { expect(passwordProblem(invalid)).not.toBe(''); await expect(submitPasswordChange(invalid)).rejects.toThrow(); }
    expect(fetch).not.toHaveBeenCalled();
  });
  it('keeps a wrong-current-password response distinct from expired access and demands a verified success', async () => {
    const expired = vi.fn(); onUnauthorized(expired);
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Mevcut parola doğrulanamadı' }), { status: 400 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Oturum geçersiz' }), { status: 401 }));
    vi.stubGlobal('fetch', fetch);
    await expect(submitPasswordChange(fields)).rejects.toThrow('Mevcut parola doğrulanamadı');
    expect(expired).not.toHaveBeenCalled();
    await expect(submitPasswordChange(fields)).rejects.toThrow('İşlem sonucu doğrulanamadı');
    await expect(submitPasswordChange(fields)).rejects.toThrow('Oturum geçersiz');
    expect(expired).toHaveBeenCalledTimes(1);
  });
});
