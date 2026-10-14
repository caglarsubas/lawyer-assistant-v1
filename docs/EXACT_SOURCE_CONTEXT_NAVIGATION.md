# Exact private source-context navigation

From **İşlerim → Portföy kaynak incelemeleri**, **Tam kaynak bağlamını aç** opens
one exact matter, analysis and immutable source context. Its URL is local:
`#/matters/{matter}?tab=source-review&analysis={analysis}&source_context={context}`.
It resolves the selected identities directly, even beyond the first twenty analyses
or ten history entries. It never searches successive pages, selects a neighboring
analysis, chooses the latest positive decision or replaces the frozen evidence version.
Ordinary matter browsing remains available through its existing navigation.

## Metadata handoff

`GET /api/v1/matters/{matter}/analyses/{analysis}/source-contexts/{context}/navigation-context`
requires the current firm session and an explicit matter content grant. The context
ID's analysis/matter namespace and every routed private record are checked before
use. The matter lock serializes private-version and independent-review updates.

The closed response contains exact IDs, frozen/current version IDs when verified,
manifest hash, record/observation times, revision, immutable historical review ID
and decision state, and separate context/review admission states. Missing or corrupt
context admissions produce unavailable identity metadata, without a substitute hash
or version. An incomplete admission remains pending. Navigation does not complete
admissions or replay mutations. Missing/corrupt review heads remain unknown.

`source_verification` is always `not_checked`, `legal_readiness` always
`not_established`, and `qualification_granted` false. Metadata has no quotations,
target content, selection/review notes, titles or captured research content. It
performs no public-source validation, graph traversal, inference or rich workspace
fetch. Sidebar branches do not expand automatically in this view. Explicit ordinary
file browsing remains under its existing matter controls. The assistant provides
only an access-checked product guide; it does not read portfolio or source content
or invoke inference. Period summaries are disabled in this handoff view.

## Explicit guarded work

After identity verification, **Seçilen kaydın inceleme araçlarını aç** opens tools
pinned to the exact context ID, manifest hash and frozen version. It still fetches
no passages. Inspection, independent review inputs, review history and export
remain explicit actions under their original source, retained grant, private basis,
actor, exact head/hash, request nonce and post-commit guards. A changed private
version does not update the frozen context. Inaccessible or stale evidence clears
passages, forms, downloads and the handoff metadata; fresh identity verification is
required to reopen tools. Historical positive decisions never authorize current reads.

Renewal starts from the pinned parent and retains its original dependency checks.
A successful renewal exposes a link to the new exact context; it does not change
the selected parent silently. The new record requires its own independent review.
Read-only previews do not trigger a portfolio refresh. Confirmed saves and committed
pending receipts retain only their opaque record ID while a fresh metadata observation
discards passages and forms; the renewal link remains explicit.
Ambiguous transport outcomes preserve the same request in current panel memory for
manual inspection only. Committed pending receipts are not repaired by navigation.

Missing, duplicate, malformed or mixed selection parameters open a closed error
view without falling back to a broad matter page. Exact target, matter, customer,
date, portfolio refresh and actor/session changes retire in-flight responses and
downloads and discard protected buffers. No browser evidence storage, cross-matter
cache, inverse public links or review-history rewrites are introduced.

## Qualification boundary

[Recorded engineering checks](evidence/exact-source-context-navigation-2026-10-14.json)
include 597 frontend cases, 242 publication cases, eight PostgreSQL races and one
actual signed-source withdrawal case. Tests use invented documents plus real PostgreSQL review-lock serialization and
real signed-release rights withdrawal. Browser checks cover targets beyond initial
pages, metadata-only arrival, explicit original evidence, self-review denial,
fresh independent decisions/history, navigation/filter races, retired downloads,
withdrawal, malformed routing and narrow viewports. These establish engineering
behavior; national legal coverage, legal accuracy, productivity, deployment and
lawyer acceptance require their separate qualification gates.

Next: exact historical-review selection and metadata-only review lineage, with
explicit guarded access to the selected event and preservation of the current head.
