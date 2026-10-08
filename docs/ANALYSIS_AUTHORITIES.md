# Private public-authority context — R05A engineering contract

This packet lets a lawyer explicitly link permitted public research passages to
an exact private analysis version. It preserves source identities, historical dates,
the lawyer's declared relationship and original draft steps. It does not grant
legal approval, infer semantic support or applicability, clear an unqualified
legal-norm blocker, change a draft/review, or dispatch a model. Real use still depends
on the R03–R05 rights, identity, historical and legal-effect reviews.

## Lawyer workflow

In **Work notebook → Structured analyses → Public-authority contexts**, explicitly
open the tools, load retained research, and choose a research record from the same
authorized workspace. The module, research history, source candidates and saved
contexts do not load automatically. Lists have ten items per page; API pages are
bounded to twenty. Legacy or document-only research without a verified, dated
public release cannot supply this context.

Inspect each original passage. Select 1–8 distinct source occurrences from one
research record. For every occurrence, choose a relationship, supply a nonblank
reason and select 1–12 distinct targets from the exact private draft:

- Support candidate, adverse candidate, material distinction, background or unresolved.
- Analysis brief, conclusion, premise, rule, application, alternative or condition.

These roles are **lawyer research declarations**. A supporting-role declaration is
not an endorsement, verified entailment or legal support verdict. An adverse role
does not establish completeness of adverse-authority search. Public conditions and
transitions still need substantive review; copied private rule/condition targets
are preserved exactly without satisfying them automatically.

Supply a title and research purpose, preview the server-generated manifest and
freeze that exact preview digest. Source quotes and metadata cannot be supplied or
overridden by the client. The server revalidates dependencies before commit under
the workspace lock. A per-user nonce makes identical retries idempotent; a changed
payload under the same nonce conflicts. The immutable encrypted context and its
separate admission receipt use the existing matter-record store and audit trail.

## Evidence and time boundaries

Selection identifies the exact **assertion + passage + authority** occurrence.
Different authority occurrences sharing a passage remain distinct. The signed
release regenerates each nomination and requires matching identity, source bytes,
quote, locator and temporal metadata. Ambiguous graph identity, ineligible assertions,
invented metadata and silently substituted references are rejected.

The snapshot includes:

- Graph family, exact subject/predicate/object, source review and recording timestamps.
- Original artifact, extracted-text representation, locator, Unicode code-point
  offsets, raw/text/locator-map hashes and exact quote hash.
- Explicit target provision version, its logical provision identity and resolution
  status where recorded. The source-text representation is a separate identity.
- Assertion validity, open-ended checking horizon/evidence where present, and
  target-version validity. Unknown dates and identities remain unknown.
- Exact research date, private event date and nullable date/interval comparisons.
- Graph release, serving digest, activation sequence, research record digest,
  private content/version/review and live private dependency hashes.

A citation can be recorded during an interval while its cited provision version
belongs to an earlier period. The two intervals are compared separately. Matching
dates do not establish applicability; differing or unknown dates are visible for
review. No current version is silently substituted for an unresolved citation.
No source-backed organizational, procedural or authority relationship is expanded
into an unstated legal-effect rule.

## Current, stale and withheld

Every inspection/export reopens the current publication guard, validates the exact
release pin and regenerates the frozen public evidence. Initial save completion
does not grant continuing publication permission. Current workspace membership and
active account status are checked before use and after guarded output assembly.

| Projection | Content | Export |
|---|---|---|
| **Current** | Frozen private/public manifest; technical dependency checks pass | Private JSON, DOCX or PDF attachment, revalidated before return |
| **Stale** | Frozen prior manifest remains inspectable while public access is permitted; changed private analysis/review/evidence, research or recipe is identified | Blocked; create a new context after reviewing current evidence |
| **Withheld** | Authorized private metadata only; `manifest: null`, no original public passage bytes | Blocked |

Revocation, missing/changed release pins, changed quote/version metadata, unavailable
retained research and publication-integrity failures withhold the public content.
Neither stale nor withheld projections rewrite the original encrypted snapshot.
The normal analysis export and model-proposal prompt remain separate; this packet
is not automatically included in either.

If commit succeeds but the final publication-guard exit or admission completion
fails, the API returns **409 `committed_needs_revalidation`** with the saved ID and
no quotes. The UI recognizes this as a retained record needing inspection, not an
unsaved operation or a successful authorization. Its pending receipt remains
withheld after transient recovery and identical retry. A fresh preview and **new
nonce/record** are required. Records are never silently reopened as approved.

Exports are assembled while authorized, rechecked against current private and
public dependencies, and discarded on render-time changes or final guard failure.
No partial download is returned. Already downloaded files are historical local
copies; later revocation cannot retract those bytes.

## API and bounds

Base: `/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts`.

| Method/path | Operation |
|---|---|
| `GET /research-products` | Paginated, authorized workspace research metadata |
| `GET /candidates?product_id=…&version_id=…` | Regenerated public passages and exact draft-target catalog |
| `POST /preview` | Validate selections and generate a content-bound preview |
| `POST /` | Freeze exact preview + nonce; current private dependencies required |
| `GET /` | Paginated metadata scoped to this analysis |
| `GET /{id}` | Current/stale/withheld projection |
| `GET /{id}/export?format=json\|docx\|pdf` | Revalidated private attachment; Current required |

Research candidates are bounded to forty occurrences. Canonical UTF-8 responses
are bounded to **1 MiB**; previews reserve 2 KiB for the saved response envelope.
Oversized or malformed packets are rejected rather than partially frozen. There
are no arbitrary graph queries, graph mutations, remote retrieval, uploaded source
overrides or automatic cross-workspace joins in this route.

## Confidentiality, retention and qualification

Private draft snapshots, source-selection metadata and linkage reasons remain
encrypted in the authorized workspace. Public graphs gain no inverse link or
private-matter usage count. Generic retention inventories, legal holds and encrypted
backups include both context and admission record kinds; this is not physical
erasure capability. No cloud fallback, provider exception, credentials, model
configuration, shared graph release or deployed application is changed.

Engineering validation covers source/pointer integrity, historical versus citation
intervals, exact targets, nonce conflicts, post-commit receipts, permission loss,
stale immutable snapshots and attachment boundaries. An isolated fixture exercises
actual physical source bytes and an Ed25519-signed release with a **test-only key**
and **simulated permissions**. Its invented text and review-shaped records are not
actual Turkish authority or human legal/rights approval.

The next bounded packet is version/context-bound lawyer findings on applicability,
historical/transition conditions, relationship limits and adverse treatment, with
dependency revalidation. Qualified public synthesis, independent semantic/adverse
assessment, held-out evaluation, measured benefit and calibrated Standard/Deep
workflows remain open. See [roadmap](ROADMAP.md), [evaluation](EVALUATION.md) and
[verification](VALIDATION.md).
