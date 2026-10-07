# Source-linked private revision adjudication

This R05A packet adds optional human observations to the existing exact-version
[lawyer review](ANALYSIS_REVIEWS.md). A lawyer can compare an immutable draft with
its immediate predecessor, inspect their selected quotations, and record what
happened to **every finding** in the predecessor's latest review. Manual and
AI-assisted revisions use the same workflow. No additional inference is performed.

## Lawyer workflow

Open **Çalışma notları → Yapılandırılmış analiz taslakları**, load the current
draft's review form, and expand **Önceki sürümle kaynak bağlı değerlendirme**.
The first version has no comparison. Later versions show actual changed typed
steps, added/removed nodes, the earlier findings, and both versions' exact selected
quotes and Unicode spans. Source buttons open the current original document;
the stored quotes remain visible for comparison. Unchanged steps remain in the
draft/version views. Review the complete argument and document context too.

Explicitly choose **Bu incelemeye sürüm değerlendirmesini ekle**. Nothing is
pre-attested. Record a reason, inspected steps and source references for each of:

- Passage meaning and inference support.
- Fact/actor roles, allegations, assumptions and negation.
- Conditions, exceptions and missing elements.
- Chronology, dates and amount thresholds.
- Counterevidence and material distinctions **within selected private documents**.
- Conclusion strength and uncertainty.

Outcomes are assessed with evidence, needs change, or not assessed. Each affirmative
observation requires at least one selected quotation from the candidate version.
Missing assessment remains visible; it does not count as successful qualification.
Private counterevidence never establishes independent public adverse-authority
search, temporal applicability, jurisdiction or authority treatment.

For each earlier finding, separately declare repaired, withheld or unresolved:

- **Repaired** requires a surviving, actually changed typed step and a candidate
  quotation, plus affirmative meaning/entailment and conclusion-strength observations
  on that same changed step. An unassessed or different step, unchanged wording or
  deletion alone cannot supply this declaration.
  These bindings do not prove that the edit addresses the finding; that remains
  the lawyer's accountable semantic judgment.
- **Withheld** requires the saved candidate's effective structural disposition to
  be withheld. Selecting a change-request review alone does not establish this.
- **Unresolved** preserves the defect. Critical or major unresolved findings, or
  any needs-change semantic observation, prohibit a positive conditional review.

Earlier findings are immutable and are not globally closed. Dispositions belong
to this exact pair. A new draft has no inherited review or assessment. The lawyer
still supplies the existing decision, criteria and current findings. Conditional
review retains its limited private-draft scope and grants no machine legal approval.

Optionally record **1–28,800 seconds** spent on this source/verification/correction
review. Missing time stays unknown. This is a declared observation, not a timer,
total preparation time, model compute measurement, paired baseline or demonstrated
time saving. No quality gain or statistical benefit is automatically calculated.

## Exact bindings and API

The existing review context endpoint adds nullable `revision_comparison`; the
existing review POST accepts optional `revision_assessment` with:

| Field | Contract |
|---|---|
| `comparison_sha256` | The exact server-issued comparison digest |
| `observations` | Six distinct typed semantic observations |
| `finding_dispositions` | Exactly one typed disposition per earlier finding |
| `review_seconds` | A bounded strict integer, or null when unmeasured |

Exported OpenAPI defines the strict nested objects:
`dimension`/`finding_index`, `outcome`, `note`, `target_ids`, `source_refs`.
Quotes are referenced as `before:<evidence_id>` or `after:<evidence_id>` to distinguish
different selected ranges from the same passage. Notes are 3–2,000 characters;
each observation has 1–20 distinct targets and up to 20 distinct source references.
Finding indices and timing are strict integers; booleans, duplicate entries,
foreign references, extra fields and incomplete dimensions/dispositions are rejected.
The existing 100,000-byte review-input limit also applies.

The server resolves the authorized immediate predecessor, checks analysis identity
and consecutive version numbers, and binds both full-content hashes, the exact
earlier review/head/hash, both source selections and the comparison/review recipes.
Caller-supplied draft, quote or finding text cannot replace these inputs. The
encrypted review stores the complete comparison snapshot and human observations.
No database migration, new record family or new provider permission is introduced.

Matter locking serializes review and revision writes. Existing request receipts
bind the complete optional assessment; retries return one immutable record.
Without an assessment, pre-upgrade canonical receipt hashes are unchanged,
including explicit null, and the absent field consumes none of the existing
100,000-byte request allowance. Changing a time or verdict under the same nonce conflicts.
The separate adjudication recipe allows invalidating comparisons without upgrading
ordinary private review semantics or asserting that old reviews assessed this rubric.

Private dependencies from **both** drafts are rechecked before recording and at
review projection/export. Changed predecessor evidence can invalidate an assessment
even if the candidate's own sources remain current. Changed recipes, review data
or comparison snapshots project Stale and withhold the effective assessment.
Stored text, findings and observations remain unchanged. Proposals pinned to such
a review recheck its comparison at admission, execution checkpoints, inspection
and adoption, including when no review prose was selected. Stale comparisons block
new calls and retained candidates; ordinary legacy reviews need no new field.
Assessment prose/timing is not automatically added to model prompts. A change during
export rejects the response. Re-evaluation requires a current pair; an old stale pair
cannot be made current by merely choosing an affirmative outcome.

All reads, joins, history, writes and exports use existing firm/matter/session
authorization. Comparisons remain encrypted private metadata. They are not sent
to models automatically, inserted into public graphs, promoted across matters or
used to grant public-source access. DOCX/PDF includes observations, prior findings,
assessed changes, exact supporting quotes and the limited scope.

## Evaluation boundary

This is an authenticated, source-linked observation workflow. Synthetic tests and
browser declarations do not establish that a lawyer actually read the sources,
that findings were semantically repaired, or that a model improved the product.
It does not infer adverse recall or populate missing jurisprudence.

Representative lawful samples, independently qualified adjudicators, registered
comparison protocols, held-out families, real model runs, full preparation/review
time accounting, sample minima and statistical reporting remain open. The separate
[release scorer](EVALUATION.md) requires these supplied observations and protocols;
one review is not automatically converted to a release score. R01, R03–R05A and
R08 remain partial/pending as recorded in the [roadmap](ROADMAP.md).
