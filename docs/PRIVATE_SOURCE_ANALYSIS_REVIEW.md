# Private source-to-analysis review

R03/R05A now provide a private API workflow for linking independently retrieved
source passages to exact analysis steps and recording an independent lawyer's
decision. This release adds the backend contract; the lawyer-facing selection
and review panel is the next finite packet.

## Frozen evidence and private basis

A nomination selects one of a saved research product's actual `source_candidates`.
It names the exact passage, source representation and quote SHA-256, plus the
expected release and serving SHA-256. No authority/assertion alias, pasted quote,
similar-version substitution or client-supplied source metadata is accepted.

The frozen manifest retains the analysis version, content, author and revision;
the existing private analysis-review pin; fact/document/contradiction basis;
research product hash/revision; source snapshot; scan coverage/limitations;
and the exact selected target snapshots. Original UTF-8 quote hashes, Unicode
codepoint offsets, locator maps and physical/text representation hashes remain
distinct. Research date and event date remain separate; unknown applicability,
legal effects and finality stay unassessed/unknown.

Selections declare `support_candidate`, `adverse_candidate`,
`material_distinction`, `background` or `unresolved`, with an explanation.
These are matter-specific lawyer annotations. They create no public graph
assertions, authority identities, binding effects or legal approval. They never
modify the analysis's text, structural blockers or existing human review.

## Independent, accountable decisions

The reviewer must currently have matter access, `matter.review`, and the lawyer
or administrator working role. The account must differ from the exact version's
author, the original analysis owner and the person freezing the source selection.
This enforces separation
of accounts; it does not establish professional credentials or social independence.

Every selected exact source and target set must be assessed. Three separate
dimensions require explained observations: quote identity, target alignment and
temporal/coverage limits. A conditional positive review requires all observations
to be confirmed; a change request requires an explicit `needs_change` finding.
The reviewer records their own relationship interpretation and note, which may
differ from the nominator's. Both declarations remain visible and immutable.
Confirming a dimension is the reviewer's declaration, not machine-verified legal
truth or a negligible-error guarantee.

Decisions are immutable encrypted matter records with reviewer identity,
timestamp, sequence, previous-decision pin, manifest hash, full input and packet
hash. Idempotent requests cannot change content or advance an unexpected head.
A later correction appends a new decision; earlier decisions remain inspectable
while their source/private basis remains authorized. Historical decisions cannot
replace the latest decision's export eligibility.

## Authorization, freshness and exports

All original release sources and retained grants are checked within the current
whole-release guard. Exact source projection uses that held guard directly.
Existing authority-dependent analyses are checked sequentially before/after it,
so their guard is never nested inside the new source review guard. Matter row
locks serialize sanctioned private mutations and competing review writes;
fresh private/product checks bracket result construction and guard exit.

Source, quote, pointer, private basis, analysis-review pin, recipe or reviewer
permission changes withhold the complete source context and free-text review
notes, and block export. Metadata-only histories retain record IDs and timestamps,
without potentially quoted titles or notes. Fresh explicit review or a newly
frozen context is required; no reviewed work is silently rewritten.

JSON retains exact quotes and reviewed targets. DOCX/PDF retain evidence IDs,
quote/representation hashes, original offsets, coverage and the two lawyers'
distinct declarations. Document layout may normalize line endings: JSON and
original passages remain the exact text references. Exports require a current
independent `reviewed_conditional` decision and recheck the entire basis after
rendering, before release. Responses use `no-store` through the existing private
API middleware. No inference, external query, shared index/graph update or
cross-matter promotion occurs.

Saves commit a pending admission with the immutable packet. Only a clean source
guard exit and complete private check can finalize it. A post-commit failure
returns `committed_needs_revalidation`; the pending record stays withheld even
if a later check becomes available. It is never replayed as an authorized save.

## API and bounds

Under `/api/v1/matters/{matter_id}/analyses/{analysis_id}/source-contexts`:

- `GET /candidates`: inspect saved source nominations and analysis targets.
- `POST /preview`, `POST /`: preview and freeze an exact private source context.
- `GET /`, `GET /{context_id}`: bounded history and current guarded inspection.
- `GET /{context_id}/reviews/context`: current basis for an independent reviewer.
- `POST /{context_id}/reviews`: append an exact-head independent decision.
- `GET /{context_id}/reviews`, `GET /{context_id}/reviews/{review_id}`: history and
  guarded inspection of a selected decision.
- `GET /{context_id}/export?format=json|docx|pdf`: guarded reviewed work product.

Closed inputs allow eight distinct sources, twelve targets per source, three
distinct review dimensions, 128 KiB review inputs, a 2 MiB complete response,
and at most 100 decisions per context. Preview reserves room for a full review.
Lists are paginated at twenty records. Missing mandatory evidence and authorization
checks fail closed; oversized records are not silently truncated.

## Engineering evidence and remaining qualification

Invented-document fixtures test exact source/version/hash/target rejection,
separate author/selector/reviewer roles, opposing interpretations, immutable
history, unexpected heads, stale private sources, review policy/access changes,
source withdrawal/guard-exit failure, and JSON/DOCX/PDF export boundaries.
The existing actual signed-release/private-ledger fixture exercises nomination,
independent review and withdrawal end-to-end. A real PostgreSQL race observes the
matter row lock and proves one of two competing exact-head decisions succeeds.

These tests are synthetic engineering evidence. They do not qualify a national
corpus, legal accuracy, independent legal expertise, preparation-time benefit,
production activation or user acceptance. R03/R05 remain partial. Next: the
lawyer-facing source-selection/review panel; independent evaluation strata/gold
remain separate, protected qualification work.
