# Exact reader retirement and independently reviewed rollback/renewal

This is an unregistered qualification adapter using invented SQLite identities,
not a production route, private-case migration or provider installation. The
original canonical journal remains the writer and withdrawal authority. The
previous staged-reader implementation, qualification reports and source pins
remain intact.

## Retire an exact selection

The currently assigned preparer or independent reviewer can retire only the last
unretired selection, with its exact proposal/selection hashes and freshly observed
control head, canonical withdrawal head and source context. Retirement remains
possible when the proposal has expired. Current actor authentication, assignment,
role and session checks still apply. An expired or revoked actor cannot retire.

Retirement appends an anchored, admitted event; it does not delete a proposal,
decision, selection, document, encrypted backup or key. That exact selection can
never become active again. Reads and old selection/approval replays fail closed.
A concurrent retirement has one winner. Lost replies are reconciled by observing
then pinning retained history, without replay. An admitted but unanchored tail
blocks ordinary reads until explicit exact head/tip recovery. Missing independent
admission evidence is never recreated by recovery.

## Fresh succession

Each proposal explicitly declares one mode:

- **Initial:** only before the first selection; it cannot bypass a retirement.
- **Renewal:** names the exact preceding selection and any retirement event.
- **Rollback:** also names a different historical selected target. The newly
  checked stage must retain the target's exact canonical journal and snapshot,
  and must still agree with today's canonical withdrawal head and source context.

Renewal and rollback create a new proposal, require a fresh decision from a
separate current assigned reviewer, and produce a new one-time selection. They
never reactivate a historical selection or reuse its approval. Source changes,
stage damage, changed predecessor/retirement pins, competing selections, changed
roles/sessions and expiry invalidate pending work. New review is required.

The proposal is bound to its exact stage, intent, receipt, physical namespace,
source snapshot, reviewer identity and current preparer session. Its lifetime
remains at most 300 seconds. Every page rechecks the canonical fence before and
after assembly and is limited to eight metadata rows. Cursors cannot cross
selections or log changes. A fresh post-withdrawal review may expose current
withdrawal metadata; it cannot restore the withdrawn ordinary reader's authority.

Status is read-only metadata, explicitly showing mode, predecessor and retirement
pins. It never renews authority. No fallback or automatic stage/source refresh
exists. Writes continue through the original service.

## Scope and qualification

The extension uses a separate versioned control namespace and schema. It does not
adopt or rewrite an existing reader-control namespace. Production transition from
older namespaces, genuine operator appointments and key custody, PostgreSQL/IdP
fencing, off-host recovery, signed live provider/context/five-job qualification
and legal acceptance remain separate gates. Owner review of focused private
analysis version 3 remains pending.

The frozen matrix passes 22 scenarios through 44 actual loopback servers and 615
HTTP requests in 123.8 seconds. Native qualification uses actual loopback
servers, real application session/RBAC/origin/CSRF enforcement with disposable
identities, four separate fresh ext4 volumes, two CPUs, 768 MiB, a 96-PID limit,
cleared environment and no external networking. Campaign limit stays 180 seconds.
The manifest-bound CI inventory must execute every deployment method once across
six disjoint assignments within the existing nine jobs. The original authenticated groups retain their existing backend phase. The new
lifecycle group uses three disjoint, sequential phases in the existing graph
runtime, graph candidate and retained-withdrawal jobs, sized using measured
reserve and deterministic source-ID hash rank. No existing job/test cap,
concurrent-worker budget or frontend file coverage is increased or reduced.

Merge requires nine exact-head checks, five timing reserves of at least 30 seconds,
a pinned-head merge and independently fetched-main tree equality. These are
engineering gates and do not establish legal acceptance or runtime deployment.

Two preparation failures before any campaign case remain retained. The first
read-only owner probe used the image default user; the corrected probe matches
the actual root preparation posture. A fresh candidate binds that exact mounted
owner without weakening ownership checks or changing cases. All newly owned
resources from rejected preparations and the accepted campaign were removed.

See the [dated evidence](evidence/reader-lifecycle-2026-10-26.json).

The first CI profile passed frontend tests but had only 24 seconds of reserve
and is rejected for merge. Its 65-second lifecycle group is redistributed without
changing any scenario or expected result. Current exact-head checks and reserves
must all pass; a green test count alone is insufficient.
