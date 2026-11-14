import type { ReactNode } from 'react';
import { ApiError } from '../api';
import { Notice } from '../components';

const revisionMessages = {
  employee: 'Çalışan değişti; yenileyin',
  role: 'Rol değişti; yenileyin',
  customers: 'Atamalar değişti; yeniden yükleyin',
  workspaces: 'Ekip değişti; yeniden yükleyin',
};

export function isAdminRevisionConflict(cause: unknown, target: keyof typeof revisionMessages) {
  // The API also returns 409 for rejected business rules that leave the revision current.
  return cause instanceof ApiError && cause.status === 409 && cause.message === revisionMessages[target];
}

export function isAdminAccessDenied(cause: unknown) {
  return cause instanceof ApiError && [401, 403].includes(cause.status);
}

export function AdminRevisionConflict({ draftRevision, currentRevision, busy, checked, onRefresh, onRestart, children }: {
  draftRevision: number;
  currentRevision?: number;
  busy: boolean;
  checked?: boolean;
  onRefresh: () => void;
  onRestart: () => void;
  children?: ReactNode;
}) {
  return <aside className="conflict-state" aria-label="Sürüm uyuşmazlığı">
    <Notice error><strong>Kayıt değişti. Taslak kaydedilmedi.</strong><p>Güncel kaydı taslağınızla karşılaştırın. Düzenlemeye devam etmek için güncel kaydı açın ve değişiklikleri yeniden girin.</p></Notice>
    <p className="small muted">Taslağın dayandığı sürüm: {draftRevision}</p>
    {currentRevision === undefined
      ? <p className="small muted">{checked ? 'Bu kaydın daha yeni bir sürümü doğrulanamadı.' : 'Karşılaştırmak için güncel kaydı kontrol edin.'}</p>
      : <><p><strong>Kaydedilen güncel sürüm {currentRevision}</strong></p>{children}</>}
    <div className="form-actions">
      <button className="button secondary" type="button" disabled={busy} onClick={onRefresh}>Güncel kaydı kontrol et</button>
      {currentRevision !== undefined && <button className="button secondary" type="button" disabled={busy} onClick={onRestart}>Taslağı bırak ve güncel kaydı aç</button>}
    </div>
  </aside>;
}
