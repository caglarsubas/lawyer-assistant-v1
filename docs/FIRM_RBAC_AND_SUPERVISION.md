# Firm RBAC, explicit responsibility and human supervision

Authorized amendment: 9 October 2026. Canonical scheduling, gates and evidence remain in [ROADMAP.md](ROADMAP.md). This requirements document is subordinate and does not grant deployment, legal approval or an automatic PR merge.

## Delivery status and dependencies

| Packet | State | Ownership | Dependency and gate |
|---|---|---|---|
| W01 | PR #32 merged; exact main CI passed; deployment/field qualification pending | Application/security | Existing private foundation; national backbone gate |
| W02 | Engineering implemented; manual PR merge and deployment/field qualification pending | Application/security | W01; national backbone gate |
| W03 | Planned | Application/product | W02; contract-workflow gate |

All three are mandatory before R08. Pending R05A reviewed source-lineage revalidation and registered same-input model authority trials follow W03. Corpus curation and human legal review can proceed independently. Existing R01–R08 requirements and evidence remain intact.

## Three independent relationships

1. **Organization:** an employee has zero or one same-firm manager. Reject self-reporting, cycles and cross-firm relationships. Reporting confers no content access, supervisory case appointment or legal review authority.
2. **Role/action:** a supported permission catalog defines permitted operations. Firm administrators assign starter or custom roles. Effective action permissions are the union of assigned roles; unsupported or corrupt permissions fail closed. Professional/reviewer eligibility remains separate from action permissions and legal/source approval.
3. **Content scope:** explicit client/case responsibility grants define the records on which those operations may act. An administrator needs a content grant to read client/case data. No firm-wide administrator bypass, hierarchy inheritance or task-generated access is allowed.

The customer ↔ workspace → file taxonomy and stable workspace/case identifiers remain. Descriptive client tags never grant permission by themselves. Existing explicit memberships and credentials survive migration; no supervisors or client-wide grants are inferred. Retain compatibility with existing endpoints.

## W01: firm administration

The customer-designated firm administrator uses an administration page to create/deactivate/reactivate employees, update names, designate organizational managers, create/edit supported custom roles and assign roles. Passwords stay server-side as hashes and never appear in lists, logs or audits. Initial credentials are supplied explicitly; existing passwords are never reset as a side effect. Preserve a recoverable active administrator and protect conflicting edits with revisions and firm-scoped serialization. Inactive accounts cannot act, retain sessions or gain assignments.

Source preparation and playbook administration retain the existing curator/admin professional-identity requirement in addition to their configurable action permissions. Creating a custom role does not confer legal qualification. Starter lawyer/curator capabilities preserve prior actions on already-authorized content. A new administration-only role manages configuration without content permissions; existing administrators retain their former actions only on explicit memberships. The legacy identity role remains a compatibility/professional marker, not a configurable content grant. Every role change and employee/hierarchy change records actor, target, change, timestamp and revision without private case contents. Return supported permissions, current assigned roles and effective action permissions in the administration UI. Display explicitly that organizational supervision grants no case access.

Enforce the catalog server-side across all existing route families, including direct API calls. Navigation visibility is only a convenience. Reads, authoring, reviews, exports, lifecycle, source curation and configuration are distinct supported operations. Revalidate active accounts and permissions; coordinate changes with active requests and background publication checkpoints. Unknown referenced roles do not acquire defaults.

## W02: explicit client and case assignments

Every client assignment expressly chooses **details only** or **details plus all current and future linked cases**. The latter is an explicit prospective grant, not an accidental consequence of client tags. Explain the chosen scope and consequences before saving. An authorized relation to one client on a multi-client case permits that case under the declared scope; expose other related client details only according to the same case-related visibility rules. Revocation and relinking recompute grants from their actual origins. Retain separately identifiable direct case grants so removing a client grant does not remove an independent case grant.

Cases support multiple assigned supervisors and responsible lawyers. Only the firm administrator changes case access teams. Supervisors with explicit case access can inspect case/documents and related clients and assign work to lawyers who already have access. They cannot grant access by creating tasks or opinions. Effective-access explanations identify the action permission and exact assignment origins without disclosing inaccessible content. Organizational managers without assignments receive no case counts, titles, snippets or summaries.

Authorization runs before joins, traversal, search, context selection, summaries, exports and caches. A matter’s public-authority selections remain confidential. Revocation cancels or withholds unauthorized queued/running work and clears disclosure from client caches; repeated requests cannot recover earlier permitted results. Verify races in PostgreSQL, not only sequential synthetic requests. Case team changes, responsibility grants/revocations and scope selection are audited. Migration never broadens access.

## W03: tracked human workflow

- **Deadlines/milestones:** manual dates, responsible people, status and case links; Europe/Istanbul interpretation. No automatic legal deadline calculation.
- **Tasks:** explicit assignee(s), description, due date, progress and completed/cancelled status. Assignees must already be case-authorized. Removing access prevents further task disclosure/action.
- **Opinion requests:** supervisor question, case context, due date and recipient lawyers. Each recipient has a separate submission and review trail. Lawyer submissions are human written; supervisor requests revision or accepts them. Retain previous submissions, revision requests and acceptance history with authors and timestamps. AI cannot silently submit or approve an opinion.
- **Work views:** personal and supervisory upcoming/overdue work, only within current authorization. In-app queues are the default; external notifications are outside v1.

## Acceptance and non-goals

W01: cycles, self-reporting, cross-firm links, unknown permissions, unauthorized role edits, administrator/content separation, migration and retained credentials, session invalidation, concurrent conflicting edits and audit history.

W02: denied unassigned manager, multiple supervisors, both client scopes including future links, direct-grant independence, cross-firm isolation, denied team changes by supervisors, active/concurrent revocation, scoped nav/search/assistant/export and cache clearing.

W03: distinct accounts complete admin setup → supervisor inspection → deadlines/milestones/tasks → each lawyer opinion → revision → acceptance. Preserve recipient history and responsibility; denied recipients and task-based escalation fail closed.

Retain the existing legal, source, graph, privacy and usefulness release thresholds. Administration is not legal approval. Automated filing, authenticated UYAP synchronization, automatic client communication, automatic deadline computation, AI-authored opinions, external notifications and cross-matter learning remain outside this amendment.

## W01 delivered packet and operator notes

The administration UI is at `#/firm-admin` in the existing app. The server returns explicit action permissions in login/session responses. The configuration-only starter role has `firm.manage` and `system.read`; it gains no matter access or content permissions. New employees receive only explicitly selected roles and no memberships. Existing accounts are additively migrated to immutable starter roles; reporting is initially unassigned. Previously migrated empty-role accounts fail closed rather than reacquiring a legacy default. Custom role edits and employee edits use revisions; changes invalidate affected login sessions and preserve one active firm administrator. Change records are encrypted and contain actor/target/configuration history without passwords or private matter content.

PostgreSQL shared/exclusive advisory locks serialize administration changes against admitted HTTP operations, including file bodies. Short worker checkpoint/publication writes share the same lock domain and recheck write permission; inference does not hold those locks. Lock admission waits are bounded at 15 seconds and failed admission does not apply the change. SQLite coordination is a demo-only, in-process equivalent, never a multi-process production guarantee. Existing offline administration participates in the same production lock domain and action permissions; upgrade the API/schema before using the updated CLI. Read-only source-preparation operators recheck curation permission. Each permission lookup reads the managed-account marker and roles together in one fresh query; only query construction is reused, never authorization results.

W01 preserved direct case memberships. W02 below adds separately identified client scope origins and explicit case responsibilities. Deadline/task/opinion workflow and portfolio work views remain W03 work. W01 development fixtures grant no actual firm responsibilities or legal approvals, and no production accounts or documents are changed by engineering verification.


## W02 delivered packet and operator notes

Administrators manage assignments in `#/firm-admin` using a client or case reference supplied by a case-authorized lawyer. The configuration response contains references, employee assignments, flags and an independent access revision; it does not disclose client names, case titles, legal text, source selections or other-case counts. Client references appear in the authorized client register. The case overview offers **Erişimim ve dosya ekibi**, showing direct/client grant origins, action permissions and the assigned supervisors/responsible lawyers.

- Client scopes are `details` and `all_cases`. The latter explicitly covers all existing and future validated same-firm links. A related client on an authorized multi-client case is visible; its other unauthorized cases and their counts remain hidden.
- Direct case grants remain in the existing membership table. Case supervisor/responsible flags accompany explicit direct grants; multiple lawyers can hold both. No legacy member becomes a supervisor by migration. Firm administrators can change active and archived case teams by reference; archived content still requires its separate lifecycle permission.
- Initial case creation retains its existing creator membership as an explicit compatibility grant. Initial client creation records creator details-only access. Later team edits require `firm.manage`. Authorized lawyers may edit client tags under the existing workflow; before saving, the UI explains that an administrator's explicit all-cases assignment also covers later links. Tags alone confer no access.
- Startup adds one migration marker per firm, retains existing credentials/memberships and converts prior client-owner detail visibility into details-only assignments. It imports only valid same-firm client links. Subsequent restarts do not reconstruct revoked grants. Upgrade with a protected database backup and the existing single API coordinator; do not run older writers against this schema after all-cases grants are enabled.
- Client/team updates require the current assignment revision. Linking changes use the existing workspace revision. Same-firm exclusive authorization guards serialize configuration and relinking with active requests/publication checkpoints; losing access blocks later retrieval and publication. Removing the last active scope holder is rejected: assign a replacement explicitly first. This protects recovery and does not imply that a scope holder's action role can perform every operation.
- Only changed assignment recipients lose sessions; unchanged recipients retain sessions. Relinking invalidates affected all-cases recipients. Unauthorized queued/running research receives durable cancellation intent in the same transaction; queued jobs are removed and running calls retain capacity until they actually exit. Original results remain inaccessible after revocation. Inference is not interrupted by pretending the call has finished.
- Authenticated API responses and original/export fetches use `no-store`. Active views recheck sessions every five seconds; hidden/page-resumed/focused views unmount private panels and verify before remounting. Failed/timed-out verification closes the UI session. Portfolio failures clear client/workspace data and aborted responses cannot refill the portfolio. Revocation does not recall already downloaded, printed or independently copied material; suspended browser/OS behavior needs target-host qualification.

The administration CLI still runs in the documented maintenance window. It checks both direct and prospective scope, invalidates changed recipients' sessions, advances the same assignment revision and removes case-role flags with direct revocation. It operates on routing metadata without decrypting legal payloads and does not run live model cancellation during maintenance. Its additional requirement that the operator already have active-case access remains; the UI configuration endpoints can manage references without granting legal-content access.

W03 deadline/task/opinion recording and supervisor delegation are still planned. W02 flags confer no global operation or professional qualification. Local synthetic tests, PostgreSQL races and browser rehearsals establish engineering behavior, not customer rollout, loss-of-connection qualification, legal accuracy, source rights or pilot readiness.
