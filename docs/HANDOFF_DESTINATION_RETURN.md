# Guarded handoff-destination return reconciliation

An explicit return from the destination-arrival-preserving exact-event handoff
captures its actual destination separately. The original saved arrival, every
previous receipt, queue, preparation and independent review observation stay
unchanged. This is private metadata, not a source-content verification or legal
approval. R03/R05 remain partial.

## Fixed contract and capture

`private-arrival-handoff-destination-return-v1` contains exactly `recipe`, the
complete validated `CarriedDestinationArrivalEventHandoff`, and one reduced
`destination` (metadata, selected event and current head). It cannot contain a
recursive return, arbitrary history window, title, note or source body.

Capture reuses the destination view's current verified metadata and lineage. It
performs no additional request or write. Exact original customer OR selection,
workspace date field/range, source-date range and bucket remain bound, as do
matter/analysis/context, frozen evidence version and manifest, selected event and
packet. Every known same-ID historical head packet is checked, including heads
known only to saved arrivals, the latest queue/preparation or this new destination.
Clocks/revisions cannot regress. Strict key checks include undefined extra keys.

Both unavailable inputs produce selection only. Partial, conflicting or redirected
inputs fail closed. Loading, failure, denial and retired observations never reuse
an earlier success. Unknown identities and pending admissions stay explicit and
confer no permission, path, readiness, legal effect or review approval.

Validation precedes nonce allocation and eviction. One row contains the new
observation plus all unchanged earlier return projections. Inputs and outputs are
cloned. Eight principal-local entries, thirty-minute expiry, opaque URL tokens,
reload/session closure and no browser persistence remain unchanged. A new return
never overwrites another saved observation.

## Fresh queue and display

The lawyer explicitly restores the exact filters and requests a fresh authorized
bounded portfolio window. Only a containing window triggers the existing single
exact-event metadata GET. An omitted window shows only a generic result, without
saved details, target reads, scans, hidden retries or fallback. Customer tags grant
no access: active same-firm explicit matter content membership is still required.

The existing saved-arrival reconciliation is reused, preserving its comparisons.
The new purpose and separately saved destination are checked independently against
fresh head/version/revision identities and all retained pins. No long-lived verdict
or checker is shared across public operations. A consistent unknown remains
unknown; queue/event disagreement, packet substitution or regression closes.

All old and new panels commit together under current principal, token, scope,
filter, revision and request fences. Invalidations and failures clear the new
panel too. Late/denied replies cannot restore it. The additional disclosure is
metadata only. The earlier arrival-preserving preparation is withheld because it
cannot carry the additional destination; a successor needs its own purpose
contract and qualification.

No backend endpoint, source body request, review/renewal/export write, provider
call, public graph mutation, credential change or deployment is introduced.

## Engineering qualification

New cases use independently cloned complete baselines; existing tests, fixtures
and assertions remain unchanged. Qualification includes strict schema, all filters
and immutable pins, unknown/pending values, regressions, omissions, denial,
principal/expiry/eviction bounds and independent projections. A fresh two-session
synthetic browser rehearsal checks exact request counts, real later independent
review/private edits, destination-only packet pins, atomic failure, customer/date
response retirement, reload closure and wide/narrow layouts. Both sessions monitor
external requests. Invented documents and simulated rights establish engineering
behavior, not national corpus, real-law, source-rights or lawyer acceptance.

Frontend CI capacity is addressed first as recorded in
[CI headroom qualification](CI_FRONTEND_HEADROOM.md). All eight exact-head checks
and measured frontend/backend job/backend test-step/graph margins of at least
thirty seconds remain mandatory before ordinary merge. Main CI and deployment
are separate states.
