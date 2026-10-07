# Review-informed private proposal contract

This R05A engineering packet lets a lawyer explicitly select immutable findings
for a bounded local-model proposal. It connects a change request to reviewable
candidate edits; it does not determine whether the finding is legally repaired.
Human review, fixed-input editing and public/historical qualification remain
separate. The [proposal workflow](ANALYSIS_SUGGESTIONS.md) retains its original
queue, provider/transport/access controls, maximum two passes and token/time caps.

## Selection and confidentiality

The optional `review_feedback` field on the existing suggestion POST is:

```json
{"review_id":"<latest immutable change request>","finding_indices":[0,2]}
```

Indices refer to the immutable finding array; they are unique zero-based integers,
not booleans or coerced numbers. Select one to five of the review's maximum twenty
findings. The selected review must be the current text version's latest **current
changes_requested** decision. Old/foreign/missing reviews, stale dependencies,
changed review recipes, invalid indices and caller-supplied feedback prose fail
before queue reservation or inference. No selection means no review prose is
sent. Request receipts bind the selection along with version, revision and mode;
retries of the same payload never start another call.

Under the matter lock, the server resolves authorized findings and captures exact
review ID, version, full-content SHA-256, review recipe, original indices and
selected finding text/severity/target/change suggestion/evidence links. The
encrypted job stores a canonical snapshot digest. Only the selected findings and
their local `finding:<index>` identifiers enter the measured model envelope.
Reviewer identities, review/version IDs, the overall review note, unselected
findings and review criteria remain outside that envelope. Selected prose can
contain confidential matter information and uses the same local-provider boundary
as the original draft. It grants no external/BYOK inference permission. The exact
previously approved laptop-tunnel exception remains separately disclosed.

## Permitted edits and response contract

Findings nominate editable steps through the draft's **declared** dependencies:

| Finding target | Editable candidates |
|---|---|
| Whole analysis | Existing applications and conclusion |
| Conclusion | Conclusion |
| Application | That application; conclusion if linked |
| Premise | Applications referencing it; conclusion if linked |
| Rule/condition | Applications using the rule; conclusion if linked |
| Alternative | Conclusion only if it depends on that alternative |

An absent declared path remains absent. These paths do not establish semantic
causality or legal applicability. The model cannot edit premises, evidence,
rules/conditions, alternatives, dates/roles, identifiers or dependency links.
Those changes require the manual editor and a new version.

Every pass must return exactly one `feedback_responses` entry per selected ID:

```json
{
  "finding_id":"finding:0",
  "outcome":"proposed_change",
  "edited_targets":["application:a1"],
  "text":"A concise, unverified explanation for lawyer review.",
  "evidence_ids":["<existing selected passage>"]
}
```

Allowed outcomes are `proposed_change`, `requires_manual_work` and `unresolved`.
The first must point to actual changed, permitted application/conclusion steps
in **that pass**. All actual edits require at least one such response. Manual or
unresolved responses require no edit targets and retain their explanation.
Missing/extra/duplicate responses, invented/repeated source IDs, invented/repeated
targets, no-op edit claims, unlinked changes, fixed-input updates and approval or
resolution outcomes are rejected. A same-target edit may address multiple selected
findings, but each needs its own response. Structural linking does not verify the
explanation's meaning, source entailment or repair adequacy.

All draft/document/finding text is untrusted data. Structured parsing, field/list/
byte limits, complete-message accounting and existing no-tool transport controls
apply. No silent truncation, new destination, model fallback or automatic retry is
added. Feedback counts toward the existing context limit and 1,000-token output
budget; excessive input fails rather than dropping selected findings.

## Revalidation and adoption

Execution checkpoints, publication, inspection and adoption re-resolve the current
review/version/content/recipe snapshot and verify its digest. The retained
candidate's responses must match its accepted iteration. A rejected repair pass
retains its responses in history without replacing the accepted candidate's
responses. Changed source facts/documents/review heads, recipes or provider pins
make work stale and ineligible; cancellation blocks publication/adoption.

The lawyer must compare original evidence and candidate edits, then explicitly
adopt with a change reason. Adoption appends a **Needs review**, unreviewed version
with selected-feedback provenance and response-pass lineage. Prior findings,
reviews and text remain immutable. A notes-only/manual/unresolved response with no
text change cannot be adopted. Later manual revisions preserve AI provenance and
require fresh review. UI and exact-version DOCX/PDF expose original selected
findings, unverified responses, linked edits and limitations.

This packet uses invented evidence and mocked inference for verification. It adds
no dependency, database migration, CI job, worker or timeout. Representative
source-linked semantic/adverse adjudication, reviewed public/historical synthesis,
broader correction, calibrated Standard/Deep and measured lawyer benefit remain
open. See [review semantics](ANALYSIS_REVIEWS.md), [roadmap](ROADMAP.md) and
[verification](VALIDATION.md).
