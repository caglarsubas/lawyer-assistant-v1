# Confidential comparison cohort reconciliation

This R05A development inventory reconciles **explicitly selected registered
comparisons in one authorized workspace**. It freezes the exact retained captures,
reports incompatible settings, reviewer differences and missing measurements, and
keeps later changes separate from the immutable snapshot. It makes no inference
call and produces no legal verdict, qualification row, benefit estimate or held-out
release protocol.

## Select, preview and freeze

In the lawyer work notebook, select between 2 and 12 existing comparison protocols
from the current workspace. Supply a title and purpose. Optionally declare family
labels reserved for a future evaluation; labels are hashed in the same way as the
comparison registration form. An empty reserved inventory means no such reservation
was supplied. It never certifies independence or absence of leakage.

Preview captures every selected protocol, both jobs, source-linked observations and
effort history from the server. It preserves missing, failed, stopped and stale
trials. Selection is explicit and incomplete; it does not claim to cover all trials
or prove unbiased sampling. No import of arbitrary capture JSON is accepted.

Freeze requires the exact preview digest and a client nonce. Changed source,
execution, observations, effort, selection or declaration requires a fresh preview.
The server checks again before commit under the existing workspace lock and locks
selected existing job rows in stable order. Identical
retries return the same immutable cohort; changed payloads under the same nonce
conflict. Creating a new snapshot is explicit and leaves earlier cohorts intact.

## Reconciliation, never automatic adjudication

Profiles partition the selection by exact rubric, provider/configuration/policy,
comparison/review/adjudication recipes, semantic dimension catalog, arm budgets,
feedback policy and real/synthetic origin. Results from different profiles are not
pooled. Credential fingerprints can cause separate profiles even when model names
match. This is conservative reproducibility, not a model-equivalence judgment.

The report retains:

- Selected protocol/input/version/family identities and exact capture hashes.
- Repeated task inputs or source versions; declared family groups; private source
  documents shared across different declared families; selected families that overlap
  the supplied reserved inventory. Families are never silently merged or relabelled.
- Per-arm latest **current** assigned-reviewer outcomes for all six dimensions and
  every original finding. Different outcome labels are flagged for human review;
  differing prose remains in the captures. Neither majority voting nor an inferred
  truth/quality label resolves a disagreement. Unassessed dimensions and unresolved
  findings remain explicit, even when capture records are complete.
- Per-arm execution status, retained passes, measured elapsed/provider round-trip
  time, unknown GPU compute, nullable active effort and separate reviewer-assessment
  time. Unknown is not zero. No preparation-time gain or claim-support metric is
  calculated. Failed total provider work/cost stays unknown.

Counts name their selected-record denominators. Completeness means record coverage,
not positive judgments. Real origin remains a human declaration. Every report and
export keeps approval, production qualification and benefit flags false.

## Private, immutable and revalidated

The cohort is an encrypted matter record. Every read, listing, preview, write and
export requires current membership of its workspace. The initial implementation
has no cross-workspace joins, automatic discovery of client relationships, shared
graph writes or cross-matter learning. Existing retention inventories, legal holds
and backups apply to the cohort and its copied private snapshots.

At read/export, compare live selected capture digests with the frozen ones. Changed
jobs, observations, effort, private evidence, reviews, model/policy or participant
access mark the cohort stale. Missing selected records are disclosed as
unavailable without substituting other trials. The frozen report stays unchanged;
stale snapshots cannot be presented as current findings. Authorization/integrity
failures fail closed. A new cohort is needed for a refreshed snapshot.

Each capture digest also binds a separate live-basis inventory: exact current
dependency-record hashes, review head, relevant contradictions, participant access,
provider/configuration and recipe/dimension digests. This detects another change
even when a trial was already stale and its human-readable reason stays the same.
Live basis hashes never substitute current text for the original protocol's evidence.

The report is bounded to 12 captures and 16 MiB canonical UTF-8 JSON. Oversized
previews/freezes/exports fail without partial output or silent truncation. Existing
per-comparison event and byte limits remain. Listings are paginated with maximum
20 records per page. Private exports use authenticated server attachments with
no-store/nosniff; downloaded copies remain subject to firm handling obligations.

API prefix: `/api/v1/matters/{matter_id}/analysis-cohorts`.

| Route | Purpose |
|---|---|
| `GET /candidates?limit=&offset=` | Bounded comparison protocol metadata from this workspace |
| `POST /preview` | Exact selected captures and deterministic reconciliation; no inference or write |
| `POST /` | Immutable snapshot bound to preview digest and nonce |
| `GET /?limit=&offset=` | Authorized bounded cohort metadata |
| `GET /{id}` | Frozen snapshot and separately computed current/stale projection |
| `GET /{id}/export` | Fresh authorized private JSON attachment; no mutation or inference |

Representative expert adjudication, source/effect approvals, public/adverse gold
evidence, actually held-out protocols and measured benefits remain independent
roadmap gates. This inventory does not grant any of them.
