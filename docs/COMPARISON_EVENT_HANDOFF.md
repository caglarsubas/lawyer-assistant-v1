# Guarded comparison-to-event handoff

R03/R05A continuation of [comparison return and fresh queue reconciliation](COMPARISON_RETURN_RECONCILIATION.md).
A lawyer can explicitly prepare a separate destination for the exact historical
review event in an authorized, freshly reconciled queue comparison. It never
substitutes the current head for the chosen event or transfers source approval.

## Preparation and retained observations

Offer **Karşılaştırmadaki tam karar geçişini ayrıca doğrula** only after the
selected context is actually observed in the bounded queue, its exact-event
metadata is verified, the current analysis version and head are known, and all
required current context/selected/head admissions are complete. Historical
receipt admissions are observations, not current grants. Unknown, out-of-window,
failed or currently pending selections offer no prepared destination.

Preparation performs exactly two sequential authorized GETs for the same exact
review event with `window=1`. Require the same frozen context/version/manifest,
chosen event packet and immutable metadata, current head packet, analysis
version/revision, admission states and tools availability as the fresh comparison.
Require monotonic observation times. A changed response or retired request closes
the action without retry, repair, fallback or further reads.

These are one-record selected-event windows, not a traversal from the head.
Truncation of that predecessor window can coexist with a verified selected event;
it supplies no head-to-event reachability, legal effect or history completeness.

`private-comparison-event-handoff-v1` separately retains:

- The original exact return intent and historical comparison receipt.
- The newly reconciled queue observation and its observation times.
- The last fresh preparation metadata and both preparation timestamps.

Original customer OR, workspace date field/range, source-record date range,
bucket, frozen evidence, event pin, original head/version baselines and explicit
unknowns remain unchanged. The payload contains only bounded identity metadata;
no source bodies, quotations, notes, matter titles or provider input are retained.

A separate **Karşılaştırmadan doğrulanan tam kararı aç** link uses the existing
principal-bound in-memory book. Its eight-entry/thirty-minute bounds, cloned
reads, eviction, principal transitions and reload loss remain. The token grants
no data permission. Current explicit matter-content authorization is mandatory
on every request; customer tags and administrator status grant none.

## Exact destination and arrival

The new purpose-bound token can select only its exact matter/analysis/context/
review ID and packet. Reject alternate events, context-only routes and write
preparations before metadata retrieval. Existing parsing also rejects incompatible
prepare/review query combinations. Alternative event/history controls remain
hidden on this destination. A different token for the same event remounts and
performs another fresh metadata read.

Arrival uses the existing fresh exact-event metadata request. Validate the chosen
packet, fixed evidence and scope, and reject regressive observations/revisions or
immutable substitutions for the same known handoff, receipt or prepared head.
Compare the current head/version/revision with the preparation separately. A
later/different head does not change the selected event; missing identities stay
unknown, and pending admissions remain pending. No path to a new head is inferred.

The lawyer can inspect original, historical receipt, queue, preparation and
arrival identities in a disclosure. Source tools remain separately explicit and
currently guarded. The comparison reads no source body and opens no review form.

## Return, retirement and qualification

An explicit verified return preserves the original historical receipt and exact
intent; arrival observations never overwrite it or create a newer receipt. When
metadata was unavailable, blocked, loading or retired, the return keeps only the
exact event selection. It does not invent an observation, erase the packet, infer
access or repair an admission. Fresh queue preparation and authorization remain
mandatory.

New preparation/observation/window, filter/revision, scope/principal, target/token,
expiry or navigation retires links and pending replies. A late first response
cannot dispatch the second request or recreate a destination. Public graphs,
provider settings, backend schemas, review history and deployment are unchanged.

See [engineering evidence](evidence/comparison-event-handoff-2026-10-15.json).
Tests and an isolated invented-document browser rehearsal cover two exact reads,
immutable substitutions, second-read drift, missing/pending metadata, redirects,
late replies, denied access, new-token refresh, actual later head/version edits,
selection-only return, exact filters and narrow layouts. Engineering checks,
hosted CI, merge, main CI, deployment and legal acceptance remain distinct.
R03/R05 stay partial. CI jobs, workers, caps and the complete exclusive backend
partition remain unchanged.

Next: a separately typed read-only arrival observation carried through explicit
return and fresh queue reconciliation, retaining prior observations without
rebasing the original receipt or transferring approval.
