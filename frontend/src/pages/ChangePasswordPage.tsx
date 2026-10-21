import { useState, type FormEvent } from 'react';
import { ApiError, post } from '../api';
import { Field, Notice, PageHeader } from '../components';

export type PasswordFields = { current_password: string; new_password: string; confirm_password: string };
export const EMPTY_PASSWORDS: PasswordFields = { current_password: '', new_password: '', confirm_password: '' };

export function passwordProblem(fields: PasswordFields): string {
  if (!fields.current_password) return 'Mevcut parolanızı girin.';
  if (Object.values(fields).some(value => value.length > 200 || /[\u0000-\u001f\u007f]/u.test(value))) return 'Parola en fazla 200 karakter olmalı ve kontrol karakteri içermemeli.';
  if (fields.new_password.length < 16 || !fields.new_password.trim()) return 'Yeni parola en az 16 karakter olmalı; yalnızca boşluk olamaz.';
  if (fields.new_password !== fields.confirm_password) return 'Yeni parola ve tekrarı eşleşmiyor.';
  if (fields.new_password === fields.current_password) return 'Yeni parola mevcut paroladan farklı olmalı.';
  return '';
}

export async function submitPasswordChange(fields: PasswordFields): Promise<void> {
  const problem = passwordProblem(fields);
  if (problem) throw new ApiError(problem, 400);
  const result = await post<{ ok: boolean; reauthentication_required: boolean }>('/auth/password', fields);
  if (result.ok !== true || result.reauthentication_required !== true) throw new ApiError('İşlem sonucu doğrulanamadı. Yeniden giriş yapıp kontrol edin.', 503);
}

export default function ChangePasswordPage({ onChanged }: { onChanged: () => void }) {
  const [fields, setFields] = useState<PasswordFields>(EMPTY_PASSWORDS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try { await submitPasswordChange(fields); setFields(EMPTY_PASSWORDS); onChanged(); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Parola değiştirilemedi. Lütfen yeniden deneyin.'); }
    finally { setFields(EMPTY_PASSWORDS); setBusy(false); }
  }
  return <>
    <PageHeader eyebrow="HESAP GÜVENLİĞİ" title="Parolayı değiştir" description="Bu işlem yalnızca kendi hesabınızın giriş parolasını değiştirir." />
    <div className="password-settings">
      <Notice>Değişiklik tamamlandığında bu oturum dahil tüm cihazlardaki oturumlarınız kapatılır. Yeni parolanızla yeniden giriş yapmanız gerekir.</Notice>
      <p className="muted">Belgeleriniz, kanıt sürümleri ve inceleme geçmişiniz korunur. Kurulum dosyasındaki başlangıç parolası bu işlemle değiştirilmez.</p>
      <form onSubmit={submit} className="inline-form" aria-label="Parola değiştirme" aria-busy={busy}>
        {error && <Notice error>{error}</Notice>}
        <Field label="Mevcut parola">{id => <input id={id} name="current_password" type="password" autoComplete="current-password" required maxLength={200} disabled={busy} value={fields.current_password} onChange={event => setFields(previous => ({ ...previous, current_password: event.target.value }))} />}</Field>
        <Field label="Yeni parola" hint="16–200 karakter. Boşluklar ve Türkçe karakterler olduğu gibi korunur.">{id => <input id={id} name="new_password" type="password" autoComplete="new-password" required minLength={16} maxLength={200} disabled={busy} value={fields.new_password} onChange={event => setFields(previous => ({ ...previous, new_password: event.target.value }))} />}</Field>
        <Field label="Yeni parola (tekrar)">{id => <input id={id} name="confirm_password" type="password" autoComplete="new-password" required minLength={16} maxLength={200} disabled={busy} value={fields.confirm_password} onChange={event => setFields(previous => ({ ...previous, confirm_password: event.target.value }))} />}</Field>
        <div className="form-actions"><button className="button primary" disabled={busy} type="submit">{busy ? 'Parola değiştiriliyor…' : 'Parolayı değiştir ve oturumları kapat'}</button><a className="button" href="#/matters" aria-disabled={busy} onClick={event => { if (busy) event.preventDefault(); }}>Vazgeç</a></div>
      </form>
    </div>
  </>;
}
