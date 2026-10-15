# Read-only renewal reconciliation and verified successor lineage

The [comparison-to-renewal handoff](COMPARISON_RENEWAL_HANDOFF.md) now retains a
bounded request receipt after a normal response, a reported post-commit failure or
an unknown network outcome. The receipt contains the original nonce, canonical
request/preview hashes, frozen parent context/hash/version/review identity and
target analysis version. It contains no scenario, source passage, selection note,
reason, request body or approval. Receipt and results remain component-local to
the principal-scoped, expiring handoff; refresh, changed filters, session changes,
navigation or reload retire them. A lost receipt is not recreated from history.

## Explicit read-only observation

An explicit action calls the local authenticated `GET .../source-contexts/renewal-reconciliation`.
Its closed, bounded query accepts one copy of each receipt field. Invalid,
duplicate or additional fields fail without echoing their values. The lookup
derives one exact record ID from the current submitting actor and nonce. An
authorized colleague cannot use another actor's nonce to reconcile that request.
Active same-firm matter content access remains mandatory; customer tags and
administrator status do not grant access.

The read takes the existing matter lock and authenticates the saved packet,
request digest, exact preview/manifest hash, source-context scope and target
version. It authenticates the original parent and the specifically captured
historical review event, then reconstructs the entire saved renewal comparison
from those immutable packets. Matching parent packet/manifest/version/review
hashes and comparison digest establish **one historical link**. The parent's
current review head and the rest of its ancestry remain unchecked. A later head
does not rewrite or invalidate the recorded historical relationship.

The response returns bounded identities, hashes, link depth and separate successor,
parent and historical-review admission states. It returns no quotations, review
notes, replacement explanations, private analysis steps or research content. It
neither invokes inference nor reads/authorizes the public source corpus. Source
verification stays `not_checked`, legal readiness `not_established`, review
inheritance `none` and legal equivalence `not_assessed`. There are no graph writes,
new records, audit effects, admission finalization, request replay or repair.

An exact record that is not observed remains `not_observed`; this is not proof of
absence or authority to retry. An unavailable, mismatched or corrupt request/link
returns no successor identity, lineage or admission metadata. A pending admission
can coexist with a verified structural link; it remains pending and withholds
successor tools. Repeated explicit GET observation never upgrades or completes it.

## Guarded successor navigation

After complete admissions, another explicit action freshly observes the same
receipt/link/admission metadata, then independently requests the successor's exact
navigation metadata. Substituted version/hash, changed admission or failed access
closes progress and clears partial results. These separately guarded observations
do not establish an atomic snapshot or durable permission lease.

The successor receives a distinct return intent with freshly observed baselines,
the exact original customer OR filters, workspace date field/range, separate
source-record date range and review bucket. The original context and selected
historical event remain unchanged. No old review ID, packet hash or approval is
copied to the new selection. Source inspection, source/retained-grant and private
basis checks, review-head controls and new independent review remain separate.

Filter changes, refresh, expiry, principal/session changes and navigation retire
late replies and hide receipt/results, source forms and quotations. The assistant
remains guide-only. This slice leaves the three-panel layout, credentials,
deployment and public graphs unchanged.

## Qualification and next slice

[Engineering evidence](evidence/renewal-reconciliation-lineage-2026-10-15.json)
records 720 frontend cases/build, 255 focused source cases, 275 publication cases,
ten real PostgreSQL races, an actual signed-runtime withdrawal case and 42
deployment contracts. Browser tests use invented accounts/documents and simulated
source rights, with actual fixture records for renewal and a fresh sequence-one
independent review. They cover lost/truncated/gateway responses after commit, a request lost before
dispatch, pending admission, exact receipt reconciliation, no extra POST, verified
lineage, filter retirement, withdrawal, expiry/reload and wide/narrow layouts.
Actual signed-runtime and PostgreSQL evidence remain separate from simulation.

The complete 4,496-case backend CI partition has no omissions, overlaps or extra
subjects. Seven hosted jobs, two workers and all existing deadlines/resource caps
remain unchanged; hosted exact-head checks and actual merge are verified
separately. Engineering results establish no national corpus coverage, legal
correctness, professional independence, productivity, deployment or lawyer
acceptance. R03/R05 remain partial.

Next: guarded navigation from verified lineage to the exact historical parent and
separate successor review, retaining filters and fresh authorization without
inheriting decisions or promoting pending states.
