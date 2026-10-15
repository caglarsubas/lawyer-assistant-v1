# Guarded comparison return and fresh queue reconciliation

R03/R05A continuation of [handoff/destination identity comparison](HANDOFF_DESTINATION_IDENTITY_COMPARISON.md).
An explicit return can retain the exact comparison the lawyer observed, then
reconcile it against a new authorized bounded queue and exact-event observation.
Original customer/date filters, frozen evidence and review history stay separate.

## Return receipt

`private-comparison-return-receipt-v1` contains only:

- The exact original return intent, including filters, event/packet, frozen
  version/manifest and original head/version observations and unknown values.
- The independently captured path-handoff observation.
- The observed destination's strict navigation metadata, chosen event metadata
  and head metadata or explicit unknown. No predecessor window is retained.

The return action verifies the exact destination and available comparison again.
It captures no receipt while the view is loading, blocked or from an older
portfolio revision. Missing/failed metadata permits only the existing selection-
only return: the event pin and original baseline survive, with no inferred
comparison, access, completed admission or approval.

Both intent and receipt are cloned into the existing principal-bound in-memory
book. The eight-entry/thirty-minute bounds, expiry, eviction, principal transitions
and reload loss apply together. URLs carry only an opaque token. No source text,
quotes, notes, matter titles, credentials or provider input enter the receipt.
It is a historical observation, not a capability or a new path-navigation grant.

## Fresh queue observation

Arrival and explicit filter preparation do not read queue or source records.
Receipt details remain hidden until a fresh authorized queue window actually
contains the selected context and a separate current exact-event metadata read
passes. Customer tags and administrator status never grant matter-content access.

Reuse the existing bounded queue and selected-event GETs; no extra request,
automatic scan, traversal, retry, source read or write is introduced. A target
outside the window stays unobserved, with retained private comparison details
withheld. Another window requires the existing explicit action.

Require the exact filters, matter/analysis/context, frozen version/manifest and
chosen event/packet. Queue and metadata head observations must agree. The queue
cannot predate the retained destination; its subsequent exact-event metadata
cannot predate the queue or regress the destination's analysis revision.

Reject immutable chosen-event substitution and changed immutable metadata for a
known handoff or destination head that retains the same ID. A different current
head/version is **different**, not an inferred successor, reversal or verified
path. Missing identities remain **unknown**, even if the other observation is
known. Changed revisions remain visible when version IDs stay the same. Pending
admissions stay pending and never become source permission or review approval.

## Lawyer-facing behavior and confidentiality

The disclosure distinguishes the original baseline, frozen chosen event, retained
handoff, retained destination and newly observed queue identities and admissions.
Previous values are never rebased or overwritten. Current source tools, renewal,
exports and independent decisions retain their separate explicit current guards.

New observations/windows, filter/revision changes, scope/principal loss, expiry
and navigation retire views and pending replies. Late responses cannot recreate a
comparison. A denied current target read clears the queue and receipt view rather
than displaying historical private metadata as a fallback. No public graph,
provider, backend schema, review history or deployed service is modified.

## Qualification and continuation

Tests cover exact intent/filter binding, stable/later/unknown identities, changed
revisions, historical pending admissions, selected and same-head substitutions,
time/revision regression, strict content-free payloads, bounded cloned retention,
selection-only return and out-of-window confidentiality. The isolated browser
uses invented documents, separate test actors, explicit grants and simulated
rights. Real later review/version edits, denied access, delayed filter replies,
exact filter restoration and wide/narrow layouts are exercised.

See [engineering evidence](evidence/comparison-return-reconciliation-2026-10-15.json).
The seven CI jobs, two workers, deadlines and complete backend partition stay
unchanged. Engineering checks, merge, main CI, deployment, legal qualification and
lawyer acceptance remain distinct. R03/R05 stay partial.

Next: a guarded explicit handoff from a fresh queue comparison to the exact
chosen historical event, preserving the receipt's separate observations without
transferring approval or automatically opening source tools.
