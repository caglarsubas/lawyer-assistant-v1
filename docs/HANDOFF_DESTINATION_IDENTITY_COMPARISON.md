# Guarded handoff-versus-destination identity comparison

R03/R05A continuation of [verified review-path navigation](VERIFIED_REVIEW_PATH_NAVIGATION.md).
A lawyer arriving through a verified path token sees a metadata comparison between
that handoff's freshly observed head/version and the destination's new authorized
observation. Original queue observations and frozen evidence remain separate.

## Four distinct identities

- **Original queue baseline:** original head/state, current-version observation
  and timestamps, including explicitly unknown values. Never rebased by navigation.
- **Chosen historical event:** exact event ID, packet, state, sequence,
  predecessor, recorded date and frozen evidence manifest/version.
- **Handoff observation:** the chosen event and observed head metadata, current
  analysis version/revision, and timestamps of the five fresh preparation reads.
- **Destination observation:** a fresh authorized exact-event metadata read with
  the current head, version/revision and context/selected/head admission states.

The handoff uses `private-review-path-handoff-v1` in the existing principal-bound
in-memory book. Only two bounded event metadata records and five timestamps are
retained, alongside the original return intent. No source text, private notes,
quotes, arguments or inferred rights enter this payload. The eight-entry,
thirty-minute limit, cloned reads, eviction, principal isolation and reload loss
apply to both pieces together. Tokens and URLs carry no customer/date values.

## Verification and behavior

The existing five-read preparation budget and exact-target restrictions remain.
The new handoff is captured from those actual fresh reads, not the older original
baseline. Strict schema validation rejects extra fields, missing/changed evidence,
unbound events, incomplete admissions and non-monotonic preparation observations.

Arrival makes the existing fresh metadata request; this comparison adds no GETs.
Validate the exact chosen event and every immutable metadata field, frozen
version/manifest, context and scope. A changed packet or metadata for the same
immutable chosen event or known handoff head closes the comparison and tools.
Regressive analysis revisions and observations older than the handoff also close.

A different current head/version is displayed as **different**, without assuming
legal reversal, chronological succession or a verified path to the new head.
Missing or unavailable identities stay **unknown**. A changed revision remains
visible even if the current version ID is unchanged. Destination pending admissions
are reported explicitly; neither comparison nor navigation completes them.

The comparison disclosure shows original, chosen, handoff and destination
identities. The existing explicit return takes the lawyer back to the same filter
intent for fresh preparation and authorized queue observation. It keeps customer
OR, workspace date field/range, source-record date range, bucket, original head
and version observations, unknown baselines, event/packet and frozen evidence.
It restores no old queue result, source approval or review form.

## Confidentiality and lifecycle

Every metadata/body action retains current explicit matter-content authorization.
Customer tags and administrator status confer no grant. Source tools, exports,
renewal and new independent decisions retain their separate explicit current
checks. There is no automatic body read, review write, replay, admission repair,
provider call or public graph update.

New tokens for the same event remount and refresh metadata. Target/token/filter,
revision, principal/scope, expiry, revalidation and navigation retire old views and
pending requests. An observation from an earlier portfolio revision cannot render
its comparison or tools. Late responses cannot restore retired metadata.

## Engineering qualification and remaining work

Pure tests cover same/different/unknown identities, changed revisions, unknown
original baselines, selected and head metadata substitution, pending admissions,
strict payloads, timestamp/revision regression, cloned bounded retention and
read-only rendering. The isolated browser uses invented documents, separate test
accounts, explicit memberships and simulated source rights. It tests actual later
review/version edits, uncertainty, packet changes, denied access, delayed filter
responses, exact filter return and narrow layout.

See [engineering evidence](evidence/handoff-destination-comparison-2026-10-15.json).
The seven CI jobs, two workers, test partitions and deadlines remain unchanged.
These checks establish synthetic software behavior, not reviewed corpus coverage,
legal accuracy, pilot acceptance or deployment. R03/R05 remain partial.

Next: preserve a separately typed destination-comparison observation through an
explicit queue return and reconcile it against fresh bounded queue metadata,
without rebasing the original baseline or inheriting approval.
