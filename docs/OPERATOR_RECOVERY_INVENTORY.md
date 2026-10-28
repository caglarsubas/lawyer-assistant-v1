# Private read-only operator recovery inventory

This F00-06 engineering slice adds a callable collector over explicitly selected
controller contexts. It does not register an application route or install a
controller. Trusted operator wiring supplies each opaque context ID, scope digest,
fresh session-authorizer and read callback. URLs, paths, directory discovery,
credentials, signers and mutations are not request parameters.

Selections contain only `context_id`, `change_id` and
`expected_context_sha256`. The current session's actor digest is separately
bound. Validate the complete selection before reading any context. At most eight
distinct selections produce sixteen sequential reads, with a two-second read
timeout and a twenty-second cooperative collection deadline. Adapters must honor
cancellation and preserve the controller's real authentication and no-store
response policy. No automatic retry, expansion or repair occurs.

For each available prebound context:

1. Reauthorize the actor before `joint_observe`.
2. Verify the closed response, actor/change/scope, source/context and history
   digests, pending heads, exact plan and exact view hashes.
3. Reauthorize and call `joint_finish_observe`, pinning the first plan, view and
   finish identifiers. Reauthorize once more before returning metadata.
4. Retain matching or differing observations explicitly. Failed authorization,
   conflict, malformed evidence or adapter error returns no cached body.

Results distinguish reconciled metadata, pending anchors, changed source,
changed requested context, changed observations, denial, conflict, unavailable
context, unverifiable evidence, partial observation and exhausted budget. Counts
cover only requested selections. Errors expose no raw response, exception,
credential, path or private content. Aggregate results and authority selections
remain confidential; they are not suitable for shared caches or public graphs.

The two reads are not an atomic snapshot, either within a context or across
contexts. A reconciled history does not establish current review validity,
readability, legal effect or execution authority. Current authority and review
validity remain explicitly unassessed. Every enrollment, installation, execution
and legal-qualification flag remains false. Observations do not renew approvals.

## Disposable qualification and limits

Ten focused tests with seventeen negative-input subtests include sixteen
authenticated ASGI inventory collections and twenty-eight collector read
requests. Fresh retirement and rollback cases preserve all four histories byte
for byte around ordinary reads. Two intentionally external anchor advances prove
the second read rejects a stale view without another write. Unrelated operators
and revoked sessions are denied; retained reviewer history stays unassessed;
expiry and source withdrawal report changed source. Missing contexts, malformed
responses, budget exhaustion, cancellation and final reauthorization also have
explicit tests.

This is in-process disposable ASGI qualification, not a new multi-process,
loopback HTTP or production qualification. All 103 existing qualified recovery
source pins, their 96 preceding dependencies, the 1,018-method deployment
inventory and the frontend inventory remain exact. Ten CI jobs and their current
deadlines/worker bounds remain. The first PR run exposed only 29 seconds of
final-release job reserve. Move the complete eight-case read-only release
inspection file into the backend remainder, using its measured reserve; retain
the heavy lifecycle and actual PostgreSQL tests in their existing job. Keep the
superseded run as evidence. Require exact-head checks, all-job/backend test
reserves of thirty seconds and the existing internal-phase reserves before a
pinned merge; verify the full main-push run and preservation audit afterwards.

Next qualify an explicit source-to-destination handoff of these exact private
inventory receipts, with fresh destination authorization and independently
bound actor/scope/context. No import, repair, history rewrite or authority
transfer follows from this inventory. Genuine operator appointments/key custody,
native/provider qualification, production activation and owner legal review stay
open.
