# Guarded exact-event navigation from verified review paths

R03/R05A continuation of [bounded returned-queue lineage](RETURNED_REVIEW_HEAD_LINEAGE.md).
A lawyer can explicitly select one event actually observed in a verified private
review path and prepare a separate packet-pinned metadata destination. The action
preserves the original customer/date filters, comparison baseline and frozen evidence.

## Guarded preparation and destination

1. Explicitly observe the returned queue and its bounded current-head path. Only
   a complete admitted path or complete same-event result offers member controls.
   Unknown, truncated, unavailable or pending results offer no event handoff.
2. Choose **N. kaydın tam kimlik geçişini doğrula** in the path disclosure. This
   clears the previous prepared link and performs at most five sequential
   authorized metadata GETs: original selected event (window 1), chosen member
   (window 1), captured current head (window 10), chosen member (window 1), and
   original selected event (window 1). No predecessor pointer is followed.
3. Every observation retains the exact matter/analysis/context, frozen
   version/manifest, current head packet, current version/revision, admissions and
   immutable review metadata. The chosen member must match its captured packet,
   state, sequence and predecessor. Require monotonic observation times and the
   same complete verified prefix, including the original selected event. Changed
   membership, packets, head/version/revision, admission, scope or access withholds
   the link. A partial history cannot substitute for the previously verified path.
4. Clone the original return intent and change only the explicitly chosen review
   ID and packet hash. Preserve customer OR, workspace date field/range,
   source-record date range, bucket, original head/version observation times,
   unknown baselines and frozen evidence. No previous selection is overwritten.
5. Create a separate path-marked token in the existing bounded principal-bound
   session book (eight entries, thirty minutes). Follow **Doğrulanan zincir
   kaydının tam kimliğini aç** separately. The token can select only that exact
   event in that exact context; redirecting it to another event, a context-only
   route or a write preparation is rejected before metadata retrieval. Existing
   route parsing also rejects incompatible preparation/event parameters.
6. Destination arrival makes a fresh exact-event metadata lookup and verifies
   the chosen packet against the intent. A different token for the same event
   remounts the selection and cannot reuse an earlier page's tools or metadata.
   Current head/version observations remain separately visible; a later head is
   never substituted for the chosen historical event. Alternative event controls
   are withheld on this path-bound destination; another choice starts at the queue.

The five observations are not an atomic snapshot or a future-stability promise.
They establish private record continuity, not legal agreement, reversal, authority,
source rights, applicability, approval or completeness of the legal corpus.

## Return, confidentiality and retirement

Returning from the destination clones its exact intent. If fresh metadata was
withheld, the selection-only return still retains the original event/packet and
baseline; it does not erase the pin or claim current access. The queue requires a
new explicit authorized observation. If metadata is present it must match the
same frozen context and selected packet before return. Ordinary first departures
can still establish a previously unobserved version baseline; an already selected
historical event retains even an explicitly unknown original baseline.

A new choice, queue observation/window, lineage observation, filter/revision,
scope/principal change, expiry or navigation clears prepared links and pending
requests. Late replies cannot dispatch the next read or recreate a link. Tokens
carry selection only. Explicit active matter-content grants remain mandatory;
customer tags and administrator status confer no access. No path is persisted to
browser storage or shared Graph A/B. Filters are carried by opaque tokens.

Preparation and arrival read metadata only. Source text, quotations, notes,
independent-review forms, export and renewal retain their separate explicit
current guards. No provider call, backend route/schema, mutation, admission
repair, review replay, source-body retrieval or public graph update is introduced.

## Qualification and continuation

Pure tests cover intermediate and endpoint selection, same-event paths, original
and unknown baselines, forged/missing members, packet/state/sequence/predecessor
substitution, all five revision-change points, head/version/manifest/admission
changes, denied access, retired callbacks, token expiry/eviction/principal
isolation, destination redirection and pin-preserving return after failed metadata.
The isolated browser uses invented documents, explicit fixture memberships and
simulated rights. It exercises real event1/event2/head3 history, five exact GETs,
packet substitutions, a late fourth reply, same-event new-token refresh, redirect
denial before reads, packet-pinned arrival, exact queue return and narrow layout.

[Engineering evidence](evidence/verified-review-path-navigation-2026-10-15.json)
records the checks. Seven CI jobs, two workers, existing deadlines and the complete
exclusive backend partition remain unchanged. Hosted exact-head checks, merge,
deployment and legal acceptance remain separate; R03/R05 stay partial.

Next: an explicit read-only comparison between the navigation handoff's observed
head/version and the destination's fresh metadata, preserving the original queue
baseline and selected event without inheriting source approval or replaying work.
