# Private source-context renewal and version comparison

In the source-review panel, **Bu kaydın kaynak bağlamını yenile** opens identity
metadata for a selected historical context. Choose freshly inspected research
passages and the current analysis version, explain the replacement map, preview
it and freeze a new record. Earlier contexts and decisions remain immutable;
the new context starts unreviewed.

## Exact sources, targets and history

The optional closed `renewal` object pins a same-matter/same-analysis parent
context, its manifest SHA-256 and its observed review head. Declare every earlier
passage as `retained`, `replaced`, `omitted` or `unresolved`, with an explanation
and explicit successor IDs. Every new selection must be mapped or separately
declared as an addition. Splits/merged maps are nominations, not legal equivalence.

Comparison retains passage, representation, document, quote, physical/text and
locator-map hashes plus Unicode offsets. Selected target IDs and canonical
content hashes are compared: reusing an ID after changing its text does not
report the same target. Analysis content, research capture and release changes
remain separate flags. Editing any mapping invalidates the preview; freeze
binds the complete manifest to its exact hash and nonce.

`retained` requires the same complete evidence identity and its original
whole-release guard before and after the new source operation, sequentially
without nesting. A changed graph pointer cannot silently replace this guard.
Explicit replacement may nominate independently authorized current evidence,
but does not revive the old context, transfer grants, delete dependencies or
expose withheld old text. The current assembly still checks all original sources
and retained grants through its existing whole-release guard.

Old-context metadata contains IDs/hashes but no quote, locator text, target text,
title, purpose or review note. Those remain accessible only through the original
guarded detail route. Private/research changes require a fresh current basis.
Later parent-review-head changes invalidate captured renewal work and block
quotes, notes and exports; earlier decisions remain immutable history.

## Fresh independent review, privacy and recovery

A different currently authorized lawyer must assess all new sources and the
three existing source-review dimensions, plus a separate explained replacement
assessment bound to the comparison SHA-256. Choices start blank. Conditional
completion requires confirmation of both sources and mapping; a change request
can identify a mapping problem. The new review sequence starts at one, with no
inherited decision. These are lawyer declarations, not legal applicability proofs.

Parent access precedes comparison. Mappings, notes and selections remain encrypted
private matter records. Source/privacy failures clear quotes, renewal reasons,
notes, previews and editors. Scope changes retire delayed replies/downloads;
identity-only payloads reject unexpected text fields. There is no browser
persistence, external query, model call, shared graph mutation or cross-matter
cache. Metadata is also withheld after private membership loss.

Ambiguous saves preserve the exact payload/nonce for explicit manual retry.
Post-commit failures remain pending; retries do not finalize historical effects.
JSON retains exact passages, maps and independent assessment. DOCX/PDF retain
comparison/assessment alongside existing evidence identities and limitations.
Exports require a current latest positive independent review and complete guards.

The new API is `GET /api/v1/matters/{matter_id}/analyses/{analysis_id}/source-contexts/{context_id}/renewal-context`.
Existing preview/freeze routes accept optional `renewal`; renewed review writes
require `renewal_assessment`. Existing v1 manifests/idempotency hashes remain
unchanged when renewal is absent. Limits remain eight sources, twelve targets per
source, 128 KiB review inputs and 2 MiB responses, with eight renewal links.
Archived matters allow read-only metadata and prohibit new records.

## Engineering qualification and next packet

Invented-document tests exercise versions/targets, complete maps, pending records,
original guard withdrawal, pointer/head changes and lost matter membership.
The existing actual signed-source/private-ledger fixture includes retained
renewal, independent assessment, export and withdrawal. A real PostgreSQL race
observes the matter row lock and rejects a preview after a competing parent
review. Browser rehearsal covers stale parent withholding, changed targets,
blank review defaults, map-edit invalidation, exact export and wide/narrow layout.
Browser rights and receipt faults are simulated.

Source-review tests share the existing source-publication job. All seven checks,
deadlines, two workers and no-retry policy remain; the complete partition is
checked for omissions/overlap. Local timings do not establish hosted billing
savings. These fixtures do not qualify national coverage, legal accuracy,
professional independence, productivity, production activation or acceptance.
R03/R05 remain partial. Next: authorized source-review readiness and a prioritized
re-review queue with dependency-change evidence, without silently rewriting work.
