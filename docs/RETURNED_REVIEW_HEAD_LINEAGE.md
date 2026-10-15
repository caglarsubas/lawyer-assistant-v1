# Bounded current-head-to-selected review lineage

R03/R05A continuation of [guarded portfolio return](RECONCILED_REVIEW_PORTFOLIO_RETURN.md).
The returned queue now offers an explicit, read-only observation of private review
record continuity. It never treats continuity as legal agreement, reversal,
authority, source permission or readiness.

## Observation contract

1. Explicitly restore the original customer OR and workspace date field/range,
   then observe a bounded queue window with the original source-record dates and
   bucket. Arrival and filter restoration perform no queue or source-context read.
   An absent target cannot nominate a lineage check or trigger a metadata fallback.
2. The target must have a pinned selected event/packet, verified frozen
   context/version/manifest, known current head and current version/revision, and
   complete context/selected/head admission. Pending or unknown metadata withholds
   the action. A newer version or changed private basis may be observed without
   promoting the frozen evidence to current source readiness.
3. Choose **Baştan seçilen incelemeye sınırlı zinciri kontrol et**. Three sequential
   authorized GETs use the existing exact-event navigation endpoint: selected
   event with window 1; captured current head with window 10; selected event with
   window 1 again. Both selected observations also report the current head,
   version and revision. No automatic continuation follows a predecessor pointer.
4. Validate the closed metadata schema, scope, frozen identities, selected and
   head packets, immutable event metadata, complete admissions and unchanged
   current head/version/revision against the captured comparison. Check monotonic
   observation times. Validate every returned member and consecutive predecessor
   ID/sequence. The exact selected member must also match its captured metadata,
   including its packet, manifest, state and predecessor.
5. Report **same event** or a **verified bounded path** only when a complete,
   admitted head window actually contains that exact selected event. Display only
   the verified prefix through the selected event. Truncated windows remain
   **unknown even when the partial prefix contains the selected event**. Missing,
   unavailable or pending members remain unknown, with no inferred absence,
   nonreachability, repair or expansion. A substitution, authorization failure or
   head/version/revision drift clears the captured comparison and path result;
   the lawyer must make a new queue observation.

The observation is not an atomic snapshot and gives no promise about future
changes. Its three times are shown separately. The first head/version baseline,
selected historical event, currently observed head/version and frozen evidence
remain distinct. The result never rebases or rewrites the return intent.

## Confidentiality and lifecycle

All lookups retain the existing explicit active matter-content grants. Customer
tags and administrator privileges give no bypass. Tokens remain bounded,
principal-bound, expiring and session-local; no private paths enter shared Graph
A/B, external search, local storage or URL parameters. The result contains only
review metadata. It carries no notes, quotations, source documents or inference.

A new queue observation, page window, preparation, portfolio revision/filter
change, scope failure, principal change, token expiry or navigation retires the
result and pending requests. After retirement, delayed responses cannot restore
a result or dispatch the next identity read. Denial has no fallback or retry.
Source verification, private-basis checks, renewal, independent review, export and
all writes retain their separate existing authorization. This slice introduces
no backend route/schema, mutation, admission repair, review replay or provider call.

## Qualification and continuation

Pure tests cover exact snapshots and filters, unchanged original baselines,
same-event and consecutive-path cases, true ten-record truncation, missing
selection, pending/unavailable members, packet/predecessor/sequence/scope/window
substitution, current head/version/revision drift, monotonic times, access denial
and retired callbacks. The browser rehearsal uses invented documents and explicit
fixture memberships with simulated rights. It exercises an actual twelve-event
history, a real later opposing head, exact three-request paths, altered responses,
pending/unavailable intermediate records, final revision drift, access denial,
late customer-filter retirement, no content/writes and wide/narrow layout.

[Engineering evidence](evidence/returned-review-head-lineage-2026-10-15.json)
records counts, limits and hashes. The full backend selection reported 3,792
passed and 97 skipped in 1,081.18 seconds, just beyond its existing 18-minute cap;
the prior passing run took 1,041.17 seconds. Move its measured 129.93-second live
runtime authorization integration into the existing PostgreSQL concurrency job,
whose 94 cases measured 162.36 seconds under a five-minute cap. Start the runtime
case first, using the same two workers. Explicitly exclude that file from the
main selection: 3,888 remaining cases plus one relocated runtime case preserve
the complete exclusive 4,521-case partition. No validation verdict, live guard,
signature, assertion or test is removed or cached. Seven jobs, worker counts,
runners, deadlines and no-retry policy stay unchanged; hosted headroom and billing
savings require observation, not inference from the local rehearsal. Exact-head checks, actual
merge/main, deployment and legal acceptance remain separate. R03/R05 stay partial.

Next: guarded exact-event navigation from a verified bounded path, preserving the
original comparison baseline and the explicitly chosen intermediate event packet.
Unknown/truncated results must nominate no event; navigation must re-observe the
exact metadata and require the existing separate source-content guards.
