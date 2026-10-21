# Model assessment premise-state guard

R05A-10 adds a declared-state precondition to private model proposal validation.
A model could previously propose `met` or `not_met` from an unknown or assumed
premise. Existing structural checks exposed unsettled inputs, but did not reject
that particular edit. A synthetic regression reproduced the accepted transition.

A **new or changed** definite condition assessment now requires a nonempty list
of fixed application premises. Every listed premise must reference exactly one
frozen fact snapshot, match its revision, have the declared role `documented`,
and point to evidence selected in the exact source draft. Unknowns, assumptions,
allegations, disputed facts, inferences, absent/ambiguous snapshots and unselected
source links cannot supply that precondition. One documented premise cannot
launder another unsettled premise in the same assessment.

The check runs after existing typed, fixed-target, feedback, authority and reference
validation. Failure rejects the whole proposed patch with the safe code
`proposal_unsettled_assessment`; there is no partial application, text repair,
automatic extra pass or adoption. The saved draft, originals, review history and
prior attempts stay unchanged. Both single-pass and bounded-repair jobs use this
check. Diagnostics contain no premise identifiers, source text or exception details.

An explicit `unknown` assessment remains allowed, including a reduction in claimed
certainty. A literal unchanged assessment is retained without re-endorsing it.
Lawyer-authored source assessments and manual editing are not rewritten by this
model-only rule. Scenario assumptions remain visible and may be discussed
conditionally; they do not become documented events through a generated status.

`documented` is a frozen human ledger classification, not an independently verified
fact or judicial finding. Passing the check does not establish that a quotation
supports a fact, that a premise satisfies the condition, that an exception is absent,
or that a rule/version applies. Rationale and conclusion prose still require
substantive review. The guard is not a semantic critic, legal approval, argument
quality score, adverse-authority evaluation or a held-out benchmark result.

Proposal recipe `private-analysis-proposals-v12` pins this additional validation
policy. Prompt messages and the four versioned response schemas are unchanged;
complete-envelope accounting, model/route pins, context/completion/time allowances,
queue controls and the five CI reserve gates remain unchanged. Earlier proposal
receipts retain their original recipes and outcomes. Existing adopted draft versions
remain available for exact-version human review; no private case is rerun merely
to qualify this engineering guard.

R05A-04 still needs independently adjudicated semantic, temporal, contradiction,
exception and unsupported-application trials with representative sources and
single-pass comparisons. R03-17 remains waiting for owner review. See the
[response contract](LOCAL_MODEL_OUTPUT_CONTRACT.md),
[review handoff](MILESTONE_REVIEW_2026-10-20.md) and
[release evaluation boundaries](EVALUATION.md).
