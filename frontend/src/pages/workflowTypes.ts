export type WorkKind = 'deadline' | 'milestone' | 'task' | 'opinion';
export interface WorkEvent { id: string; action: string; actor_id: string; actor_name: string; recorded_at: string; text?: string; note?: string; decision?: string; status?: string; reason?: string; request_version?: number; snapshot?: { title: string; description: string; due_local: string; assignee_ids: string[]; status: string } }
export interface WorkResponse { id: string; revision: number; user_id: string; recipient_name: string; status: string; active: boolean; currently_eligible: boolean; history?: WorkEvent[] }
export interface WorkItem { id: string; revision: number; kind: WorkKind; title: string; description?: string; due_local: string; due_at: string; time_zone: string; status: string; queue_status?: string; overdue: boolean; assignee_ids: string[]; matter_id: string; matter_title?: string; viewer_id: string; request_version: number; can_manage: boolean; can_review: boolean; can_act: boolean; responses: WorkResponse[]; history?: WorkEvent[] }
export interface WorkDraft { kind: WorkKind; title: string; description: string; due_local: string; assignee_ids: string[] }
export interface WorkPerson { id: string; name: string; can_opine: boolean }
export interface WorkList { items: WorkItem[]; can_manage: boolean; people: WorkPerson[]; time_zone: string }
export const KIND_LABELS: Record<WorkKind, string> = { deadline: 'Son tarih', milestone: 'Aşama / kilometre taşı', task: 'Görev', opinion: 'Yazılı görüş isteği' };
export const WORK_STATUS: Record<string, string> = { open: 'Açık', pending: 'Bekliyor', in_progress: 'Çalışılıyor', completed: 'Tamamlandı', cancelled: 'İptal edildi', submitted: 'İnceleme bekliyor', revision_requested: 'Değişiklik istendi', accepted: 'Gözetmen kabul etti', stale: 'İstek değişti · yeniden çalışma gerekir' };
export function workTime(value: string) { return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Istanbul' }).format(new Date(value)); }
export function latestSubmission(response: WorkResponse) { return response.history?.filter(e => e.action === 'submitted').at(-1); }
