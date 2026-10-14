# Exact historical-review navigation and private metadata lineage

In a source context's independent-review history, **Kararın tam kimliğini aç**
opens one exact immutable review event. The local route adds a single `review`
identifier to the existing matter/analysis/context selection. Missing, duplicate,
malformed or mixed targets close the view without opening a broad matter page or
substituting the current review. Direct lookup works beyond initial history pages.

## Bounded metadata contract

`GET /api/v1/matters/{matter}/analyses/{analysis}/source-contexts/{context}/reviews/{review}/navigation-context`
requires the existing current-firm session and explicit matter content grant. All
selected routing identities and the review's context namespace precede decryption.
The existing matter lock serializes private-version and review-head updates.

The closed `private-source-review-lineage-v1` response contains:

- Existing context identity metadata, including frozen/current versions and hash.
- Selected event ID, decision, sequence, recording time, packet/manifest hashes,
  predecessor ID, and separate integrity/admission state when verified.
- The independently observed current head, or explicit unknown when unavailable.
- A bounded predecessor chain starting at the selected event. `window` accepts
  1–10; default ten. Each observed step verifies its record/admission routing,
  packet identity, exact context manifest hash, recipe, review dimensions,
  sequence and predecessor. Cycles, discontinuities and missing/corrupt records
  stop the chain. Missing dates remain unknown; event order comes from verified
  predecessor/sequence declarations, not date sorting.

`head_relationship` distinguishes the same observed identity, a different head,
and an unestablished relation. A different identity does not prove ancestry or
current legal validity. `head_reachability` is explicitly `not_checked`.
Coverage is `selected_predecessors_only`; `total_count` is null. Reaching the first
recorded event completes only this selected predecessor chain, not newer decisions
or every historical record. Truncation exposes an unverified continuation pointer;
following it is an explicit new selection, not an unlimited pagination scan.

The metadata contains no source quotations, review notes, target text, captured
research or reviewer identity. It invokes no source guard, graph lookup, inference,
external request, admission repair or mutation. `source_verification` stays
`not_checked`, `legal_readiness` stays `not_established`, and qualification is false.
Pending admission and broken lineage keep the affected inspection tools closed.
Historical decisions remain visible as historical declarations after rights or
reviewer-access changes; they never become present source permission.

## Explicit inspection and current-work return

The selected event is shown before context details. **Seçilen tarihsel kararın
inceleme araçlarını aç** fetches no passages. **Seçilen tarihsel kararı ve özgün
dayanakları kontrol et** calls the original guarded review-detail route and checks
both the context/manifest/frozen version and selected event/packet hash.

Original source and retained-grant checks, private-basis freshness, reviewer
eligibility, review-head and post-operation checks still control the actual body.
Source withdrawal or a failed check clears the body and metadata; identity must
be freshly observed before reopening tools. No newer event, evidence version,
positive decision or current provision is silently selected.

Historical mode exposes no export, renewal or new-review form, including when the
selected identity equals the observed head. **Güncel bağlamın kimliğine dön** opens a
fresh context observation; current inspection, export and independent review then
use their existing guards. Old assessments, head expectations and request nonces
are not inherited. The explicitly observed head can also be opened as a separate
exact event; a newer head arriving concurrently never rewrites the selected event.

Target/event, customer/date/filter, refresh, actor/session or navigation changes
retire delayed metadata, evidence bodies and downloads and discard protected forms.
The assistant remains guide-only. No browser evidence cache, shared graph update,
private inverse link or review-history rewrite is introduced.

## Qualification and next slice

[Recorded engineering checks](evidence/exact-historical-review-lineage-2026-10-14.json)
include 618 frontend cases, 263 publication cases, nine PostgreSQL races and one
actual signed-runtime withdrawal case. Invented-document checks cover non-latest decisions, later conflicts, pending and
missing admissions, broken/cyclic histories, namespace/content-grant isolation,
reviewer-access loss, bounded windows, invalid targets and late replies. Separate
actual PostgreSQL locking and signed-runtime withdrawal checks exercise concurrency
and evidence authorization. Browser checks include old events beyond the first
history page, guarded reads, typed links, explicit current return, truncation,
filter retirement, withdrawal and narrow layout.

These are engineering checks. Legal corpus coverage, accuracy, professional
independence, productivity, deployment and lawyer acceptance require separate gates.

Next: explicit return to a freshly observed portfolio source-review queue with
bounded customer/workspace/source-date filters and selected-record reconciliation.
