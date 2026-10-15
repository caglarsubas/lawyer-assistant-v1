# Guarded arrival-preserving exact-event handoff

R03/R05A continuation of [arrival return reconciliation](ARRIVAL_RETURN_RECONCILIATION.md).
A lawyer can explicitly prepare the exact historical event from a freshly
reconciled arrival-return queue. Original receipt, queue, preparation and arrival
remain separate historical observations; no current head replaces the selection.

## Preparation and purpose token

Offer **Varışı koruyarak tam karar geçişini doğrula** only after the selected
context actually occurs in an authorized bounded queue window and its fresh
exact-event metadata passes arrival reconciliation. Require a known current
version/head and complete current context, selected-event and head admissions.
Historical unknowns and pending admissions remain historical; they do not grant
current access. Omitted, unknown, pending or unavailable current observations
withhold preparation.

Perform exactly two sequential authorized GETs for the same pinned event with
`window=1`. Require stable frozen evidence, chosen packet and immutable event
metadata, current head packet, version/revision, admissions and tools availability
against the fresh queue observation. Enforce monotonic timestamps and current
request fences before/after each read and before allocating a token. A changed,
denied or retired read stops without retry, repair or a further request. A
truncated one-record predecessor window never establishes a path from the head.

`private-arrival-event-handoff-v1` retains exactly:

- The original `ArrivalReturn` unchanged.
- A separate fresh queue comparison against that retained arrival.
- A separate preparation snapshot and two preparation timestamps.

Strict schemas keep depth fixed and reject extra or recursively nested histories.
No source bodies, quotations, comments, matter titles or predecessor windows are
retained. Customer OR, workspace date field/range, source dates, bucket,
matter/analysis/context, frozen version/manifest, selected event/packet and
original unknown baselines remain unchanged. The principal-bound memory-only book
keeps its eight-entry/thirty-minute bounds, cloning, eviction and reload loss.
Tokens grant no permission and carry no private data in their opaque value.

A separate **Varışı koruyan doğrulanmış tam kararı aç** link requires an explicit
click. It cannot select another review, context-only route or write preparation.
Reject those redirects before any metadata read. New tokens for the same event
remount and require another authorized observation. Alternative history links
remain hidden on this purpose-bound destination.

## Destination and return

Use the existing fresh exact-event metadata GET. Validate fixed evidence, chosen
packet and all known retained same-head identities; reject substitutions and
regressive observation/revision. Compare destination head/version/revision with
new preparation and retained arrival separately. Later or different heads never
replace the selected event or establish a path. Unknown identities stay unknown,
and pending admissions stay pending. Details remain in a disclosure.

A verified explicit return restores the **original ArrivalReturn unchanged**.
The onward destination is an observation for comparison, not an implicitly saved
new historical arrival or a recursively appended chain. If current metadata is
missing, failed, loading, blocked or retired, return only the exact selection.
Do not revive a receipt, transfer approval, repair an admission or replay a write.
The restored queue must be prepared and freshly authorized again.

Require current explicit matter-content grants on every read. Customer tags and
administrator status grant no content access. Source tools remain separate,
explicit and currently guarded; metadata matches confer no legal qualification.
Filter/revision, scope/principal, token/target, expiry, new observation/preparation
and navigation retire views, links and delayed replies. No automatic body read,
form, review/renewal/export write, provider call or public graph mutation is added.
Backend schemas, review records, credentials and deployment are unchanged.

## Qualification

See [engineering evidence](evidence/arrival-event-handoff-2026-10-15.json).
Unit cases cover two bounded reads, changed observations, forged retained payloads,
unknown/pending identities, substitutions, redirection, unavailable returns and
session bounds. Isolated invented-document browser rehearsals cover the full
prior flow and a focused onward flow, including actual later opposing review and
private version edits, fresh authorization, exact filters and wide/narrow layout.
Rights are simulated; engineering checks do not establish corpus, legal or
lawyer acceptance.

All seven CI jobs, two workers, deadlines and the complete exclusive 4,521-case
backend partition remain unchanged. Exact-head hosted checks, merge, main CI,
deployment and legal qualification stay separate. R03/R05 remain partial.

Next: bounded reconciliation of an onward destination against the retained
arrival on return, using a separately reviewed fixed-depth observation contract
without replacing the original receipt or accumulating recursive histories.
