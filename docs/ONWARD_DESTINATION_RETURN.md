# Guarded onward-destination return reconciliation

An explicit return from an arrival-preserving exact-event destination can retain
that destination separately. The original arrival, receipt, intervening queues
and preparations remain unchanged. This is an engineering increment in the
private source-review workflow; R03/R05 remain partial.

## Capture and storage

`private-onward-return-v1` has three fields: recipe, the existing validated
`ArrivalEventHandoff`, and a reduced destination observation. The observation
contains only exact navigation metadata, the selected review packet metadata and
current-head metadata. No predecessor windows, source text, party information,
review notes or arbitrary previous-return objects are retained.

Capture runs only on explicit return with currently verified matching metadata
and exact-event history. It validates the purpose-bound target and all original
scope, frozen evidence and selected-event pins. Both unavailable inputs produce
selection only. One missing input, an alternate event, context-only redirection,
write preparation or inconsistent metadata fails closed. Loading, denied,
failed or retired views cannot reuse an earlier successful destination.

The original customer OR selection, workspace date field and range, source
record date range, queue bucket, frozen version/manifest and original unknown
identities remain exact. Capture never changes the selected event to the current
head, rebases an earlier observation or transfers review approval.

The existing principal-bound in-memory book holds at most eight entries for
thirty minutes. Inputs and outputs are cloned. Validation precedes allocation
and eviction. A new opaque token stores the original intent and the separately
typed destination, plus unchanged original arrival/receipt projections for their
existing panels. No payload is added to URLs or persistent browser storage;
reload, principal change, eviction and expiry remove access to it.

## Fresh queue reconciliation

Retained destination details stay hidden until the lawyer explicitly restores
all filters and requests a fresh authorized bounded queue. Reuse its existing
exact-event GET only when the target is in that window. Customer tags never
confer content access. A target outside the window remains unobserved; no older
metadata fallback, automatic next-window scan or hidden retry is performed.

Validate queue filters, window, scope and target against the exact intent and
fresh navigation/history against frozen evidence and the selected event. Reject
regressive queue/event times or analysis revisions and immutable selected or
same-known-head packet substitution against every retained observation.

Compare fresh head, current analysis version and revision separately against:

- The newly retained onward destination.
- The original arrival and onward preparation.
- The earlier receipt and preparation through their existing comparisons.

An actually different head is a different identity observation, not proof of a
path, legal effect or replacement selection. Unknown head/version remains
unknown in either direction; pending admissions remain pending. Observation
timestamps remain separate and do not imply an atomic snapshot.

All panels commit together only after all comparisons succeed and the token and
request fence remain current. A new observation, window, preparation, filter,
portfolio revision, scope/principal, token, navigation or expiry retires prior
views and replies. A late response cannot restore a private panel or trigger a
second request. Denial clears all comparisons with no retained-detail fallback.

## Interaction boundary

The new panel is metadata only and contains no actions, forms or source bodies.
The older arrival-preserving preparation is withheld for these entries because
it cannot carry the additional retained destination. A further handoff needs its
own fixed-depth contract; it must not silently drop this history. Existing
separate source actions retain their independent current authorization checks.

No new backend endpoint/schema, automatic source-body retrieval, quotation,
review/renewal/export write, replay, repair, provider request, public graph update
or deployment is introduced. Original append-only review history is untouched.

## Qualification

Forty focused cases cover capture, strict payloads, immutable pins across prior
snapshots, exact filters, omitted windows, changed/unknown/pending identities,
time/revision regressions, memory limits, cloning and read-only rendering.
A fresh isolated browser rehearsal exercises actual independent review events
and analysis versions, separate destination/arrival comparisons, denied and
late responses, known-head packet substitution, exact filter restoration,
reload loss and wide/narrow layouts. Documents/accounts and rights are synthetic;
these checks establish no legal, corpus, production or lawyer acceptance.

See [engineering evidence](evidence/onward-destination-return-2026-10-15.json).
All seven CI jobs, two workers, existing deadlines and the exclusive complete
4,521-case backend selection remain unchanged. Exact-head hosted checks, merge,
main CI and deployment must be verified separately.

Next: guarded exact-event handoff retaining the onward-return destination and
all earlier observations within an explicitly bounded fixed-depth contract.
