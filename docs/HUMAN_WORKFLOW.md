# Manual work and human opinion workflow

W03 engineering contract, 9 October 2026. Scheduling and release gates remain in [ROADMAP.md](ROADMAP.md); firm access is governed by [FIRM_RBAC_AND_SUPERVISION.md](FIRM_RBAC_AND_SUPERVISION.md). Merge, deployment and field qualification are separate.

## Lawyer workflow

1. The firm's administrator explicitly assigns case supervisors and responsible lawyers through the existing access workflow. Reporting hierarchy and case supervision are separate.
2. A current case supervisor opens **İş takibi**, selects Son tarih, Aşama / kilometre taşı, Görev or Yazılı görüş isteği, enters a title, description/question and manual Istanbul date/time, and selects already-authorized recipients.
3. Each recipient records their own progress or written opinion. Opinion submission records the exact human-account author, text, time and request version; other recipients' opinions are not disclosed.
4. A different current supervisor reviews the latest opinion submission, requesting revision or accepting it with a reason. Revision and resubmission append history; prior texts remain. Acceptance is workflow review, not legal accuracy or authority approval.
5. A supervisor may edit or cancel with a reason. Question/title/date/recipient changes advance the request version and require fresh work. Complete the request only after all active recipients have completed their progress, or have accepted opinions for the current version.
6. **İşlerim** shows personal and explicitly supervised work, with separate upcoming/overdue/closed filters. Left-panel customer/date filters refer to workspaces; due status refers to this manual deadline.

A changed instruction does not silently change established matter facts or legal-analysis conclusions. Work and opinion records are not automatically promoted to evidence, firm playbooks, model prompts, authority approvals or legal exports. Human-account attribution cannot verify whether pasted text was drafted elsewhere. No AI opinion writer, autonomous approval, automatic legal deadline calculator or external notification is included.

## Authorization and concurrency

- Reads require active same-firm case scope plus `matter.read`, and either active request-recipient routing or explicit current case supervision. There is no general administrator, organizational-manager or case-teammate bypass.
- Creation/editing requires current case supervisor identity and `matter.write`. Recipients must already have case scope and `matter.write`; opinions additionally require the existing lawyer/admin professional marker. Read-only/configuration roles cannot become opinion writers by assignment.
- Recipients act only for themselves. Reviews require current case supervision and `matter.review`, a different author, an active eligible recipient, an open request, the exact latest submitted ID and current request/response revisions.
- Mutations lock the matter, request and affected recipient response. Conflicting revisions return 409; clients clear the failed selection and must refresh rather than retrying acceptance blindly.
- A work edit that removes a recipient takes the exclusive firm guard and invalidates that person's sessions. Admitted reads finish before removal commits. Case access can remain while the old request becomes inaccessible. Readding a recipient retains their response/history; no implicit case grant is created.
- Role, client/team scope, deactivation and case archive remain governed by W01/W02. Removed/ineligible recipients stay visible as historical records to current supervisors, without new review permission. Archive closes reads and queues, retaining encrypted history.

## API

All routes below are under `/api/v1`; cookie authentication, CSRF for mutations and no-store responses use the existing app contract. Unknown payload fields are rejected; clients cannot supply author/reviewer identity.

| Method / route | Operation |
|---|---|
| GET `/work?view=personal\|supervisory&bucket=all\|upcoming\|overdue\|closed&limit=100` | Currently authorized queue; returns `items`, `truncated`, `candidate_window`, `time_zone` |
| GET `/workspaces/{matter_id}/work` | Authorized case register; permitted recipient choices only for managing supervisors |
| POST `/workspaces/{matter_id}/work` | Create manual work, returning the detail and independent recipient records |
| GET `/workspaces/{matter_id}/work/{id}` | Current authorized detail and scoped histories |
| PUT `/workspaces/{matter_id}/work/{id}` | Revision-bound edit/status transition and reason |
| POST `/workspaces/{matter_id}/work/{id}/progress` | Current account's progress and required note |
| POST `/workspaces/{matter_id}/work/{id}/submissions` | Current assigned lawyer's text submission |
| POST `/workspaces/{matter_id}/work/{id}/responses/{recipient}/review` | Different supervisor's exact-submission decision and reason |

Creation fields: `kind` (`deadline`, `milestone`, `task`, `opinion`), `title` (1–200), `description` (up to 20,000; required for opinions), `due_local` (`YYYY-MM-DDTHH:mm`) and unique `assignee_ids` (1–200). Istanbul invalid/nonexistent/ambiguous wall times fail validation. The server records `due_at` as UTC and `time_zone=Europe/Istanbul`; host/browser timezone does not redefine the entered instant.

Edits carry all creation fields plus parent `revision`, `status` (`open`, `completed`, `cancelled`) and `reason` (1–2,000). Kind cannot change. Closed edits cannot change recipients; cancellation is still possible with retained IDs after recipient access loss. Meaningful instruction/date/recipient edits increment `request_version`; old response history stays Stale until fresh progress/submission. Status-only changes retain that version.

Progress carries response `revision`, `status` (`pending`, `in_progress`, `completed`) and `note` (1–4,000). Opinion submissions carry response `revision` and `text` (1–50,000). Reviews carry response `revision`, exact `submission_id`, `decision` (`accepted`, `revision_requested`) and `note` (1–4,000). Submitted/accepted opinions cannot be overwritten with another submission until revision is requested or the request changes. A supervisor cannot accept their own opinion, including when also a recipient.

Parent request status and each recipient's status are independent. Personal queues use the recipient's completion/acceptance, so finished work does not become overdue while others remain open. Supervisory queues use the parent status. Queue predicates authorize before joins/decryption/counts; due sorting is within the newest 1,000 authorized candidate requests, default return limit 100 and maximum 500. `truncated` reports either bound. Older omissions and absence of work must not be treated as established; open the authorized case register to inspect it. There are no queue-delivery guarantees.

## Persistence and qualification

`human_work` and per-recipient `human_response` payloads/history use existing encrypted records with independent optimistic revisions. `work_participants` holds private same-firm/case/user routing, response identifiers and active flags; it grants no case scope. Global audits record actor/action/target metadata without raw opinion/question content. Preserve all these tables and encryption keys together in protected backups and legal holds. Archive is reversible hiding, not deletion. Physical erasure, export of workflow histories and external notifications remain unqualified/outside this packet.

Read-only display, accepted opinion and retained history do not establish legal correctness. SQLite is a single-process demo equivalent; production uses the existing PostgreSQL firm guard and row locks. [Validation](VALIDATION.md) records synthetic API, actual PostgreSQL race, offline Linux and distinct-account production-build browser results. Customer migration, target-host suspended/disconnected behavior, restore and field acceptance remain required before rollout.
