# Guarded arrival return and fresh queue reconciliation

R03/R05A continuation of [comparison-to-event handoff](COMPARISON_EVENT_HANDOFF.md).
An explicit return can retain the exact arrival actually observed at that
purpose-bound event destination. The original receipt, queue and preparation
remain historical observations; the new arrival never replaces their values.

## Return contract

`private-arrival-return-v1` has exactly three fields: recipe, original comparison
handoff, and reduced arrival metadata. It retains no predecessor windows or
recursive prior returns. Scope, frozen version/manifest, selected event/packet,
original customer OR, workspace date field/range, source dates, bucket and
original unknown baselines remain unchanged. All fields are cloned.

Capture requires the currently available authorized exact-event metadata and its
matching lineage response. Revalidate both, the exact selected target and each
prior observation. Reject changed immutable selected or same-known-head metadata,
filter/evidence drift and regressive time or revision. Missing, failed, loading,
blocked or retired metadata produces a selection-only return. It cannot invent
an arrival, resurrect a receipt, repair an admission or transfer approval.

Use the existing principal-bound memory-only book: at most eight entries for
thirty minutes, with cloned reads and loss on eviction, reload or principal
change. The token carries no private metadata in its URL and grants no access.
No new storage, backend API, schema or provider operation is added.

## Fresh reconciliation and confidentiality

Arrival alone and explicit filter preparation reveal no retained arrival details.
Reuse the existing authorized bounded queue GET and, only when the selected
context occurs in that window, a fresh authorized exact-event metadata GET.
Current explicit matter-content grants remain mandatory. Customer tags and
administrator status grant no content access.

An omitted target stays unobserved; no retained identity details, old metadata,
automatic window scan, hidden retry or inferred access loss follows. Require
exact restored filters, fixed evidence and event pin, matching queue/head
observations, and monotonic queue/event time and analysis revision. Validate
same-known-head packets against the original handoff, receipt, preparation and
arrival. A mismatch clears both receipt and arrival views.

Compare fresh head/version/revision against arrival separately from the older
receipt and preparation. Show same, different and unknown relationships; pending
admissions remain pending. Changed heads are observations, not verified paths or
replacement selections. Historical details stay in disclosures and never imply
source access, legal effect or current approval.

The arrival-return queue is read-only. Its older receipt preparation control is
withheld so it cannot silently discard arrival history. An arrival-preserving
onward handoff is a separate next slice. Existing explicitly separate ordinary
queue navigation, bounded lineage checks and current source-tool guards remain.

New observations/windows, filter/revision, scope/principal, token/target, expiry
and navigation retire views, links and delayed responses. No automatic body,
quotation, comment, review/renewal/export write, replay, admission repair,
external request or public graph mutation is added. Review records are unchanged.

## Engineering evidence and remaining qualification

See [engineering evidence](evidence/arrival-return-reconciliation-2026-10-15.json).
Unit cases and an isolated invented-document browser rehearsal cover fixed-depth
capture, unavailable return, all exact filter dimensions, distinct observations,
actual subsequent version edits, opposing heads, unknown/pending metadata,
immutable substitutions, queue omissions, access denial, delayed replies, bounds,
principal transitions, reload and narrow layout. Simulated source rights do not
establish corpus, security deployment or legal qualification.

All seven CI jobs, two workers, deadlines and exclusive 4,521-case backend
partition remain unchanged. Local checks, exact-head hosted CI, merge, main CI,
deployment and lawyer acceptance remain separate. R03/R05 remain partial.

Next: an explicit arrival-preserving exact-event handoff from fresh queue
reconciliation, retaining these fixed observations without recursively accumulating
returns or rebasing any historical receipt.
