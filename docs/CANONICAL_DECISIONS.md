# Canonical decision identity review

This R03 contract follows [accountable occurrence mapping](DECISION_MAPPING.md).
It creates firm-confidential identity assertions, not a qualified national registry
or published Graph B authority. Source packages remain unchanged.

`GET/POST /api/v1/public-sources/{source_id}/decision-identities` reads or proposes;
`POST .../decision-identities/review` records an independent-account opinion. All
routes require current `source.curate` permission and an admin/curator role. Writes
require CSRF and current identity, source-review and mapping revisions. Only the
assigned source owner proposes; an independent reviewer need not own the source.

## Identity boundary

The owner explicitly assigns typed `urn:tr-law:institution:`, `:proceeding:` and
`:decision:` IDs with identity and institution evidence references and SHA256s.
No ID is inferred from a case/application number: one proceeding can contain
several decisions. A deterministic `:decision-version:` ID binds the decision,
source ID/version and exact raw/text hashes. References identify reviewer-supplied
evidence; this software does not authenticate unavailable external registers or
establish national uniqueness. Unknown dates, finality and legal effects remain
unknown. Cited authorities are not canonically resolved by identifying the source's
own decision.

The initial bounded contract supports one own decision per retained source.
Current accepted mappings must have a consistent own decision/proceeding/institution
reference, at least one own identifier number, reviewed extraction coverage and
all four current source reviews. Multiple decisions require explicit segmentation
before this contract can be used. This is the selected mapping scope, not a claim
that every occurrence in every passage has been identified.

## Accountable independent review

Proposals pin the complete source and mapping history prefixes, source artifact
binding and a canonical snapshot SHA256. The contributor set is reconstructed from
all events through those revisions, including prior owners and superseded opinions.
Acceptance, rejection and change requests require evidence and a separate account
outside both the proposer and that contributor set. Separate accounts do not prove
separate natural persons, professional credentials or absence of conflicts.

The encrypted append-only ledger retains every proposal and opinion (maximum 100
events per source). Replayed history must match the encrypted head. Any source or
mapping change makes the current identity stale; reaffirming mappings does not
reuse identity acceptance. A new pinned proposal and independent opinion are needed.
Complete history and original-artifact checks run before mutation and response.
Optimistic revisions and source row locks reject competing or stale writes.

Acceptance reserves identities only inside the firm: a proceeding retains its
institution binding; a decision retains its source, proceeding and institution;
its version retains its source/decision binding. Different decisions may share a
proceeding. Cross-source reuse needs a future explicit equivalence review and is
currently rejected. Reservations are not recycled after rejection or replacement;
reads revalidate accepted historical reservations. No cross-firm equivalence lookup
or private inverse link is created.

## Staged handoff and remaining gates

`canonical_identity_reviewed` and `staged_handoff_ready` mean a current independent
account accepted this private identity assertion. `global_registry_qualified`,
`legal_effect_verified` and `publication_eligible` remain false. The handoff compiler
produces a bounded [private Graph B staging artifact](GRAPH_B_HANDOFF.md), with
exact retained passage evidence and complete review provenance. Arbitrary external
evidence references remain unsupported by that handoff. Existing shared provision
publication tooling does not accept
decision identity ledgers. Legal/privacy/fidelity review, graph identity equivalence,
ontology qualification, publication authorization and serving activation remain
separate work. No actual legal approval is supplied by engineering fixtures.
# Cross-source review successor

[Reviewed equivalence and retained institutional-register evidence](DECISION_EQUIVALENCE.md)
now records a separate, firm-private claim between two accepted decision identities.
An explicit existing canonical candidate is required for a same-decision claim. This
does not relax the original reservation rules, recycle IDs or rewrite source-bound
versions. Consequential shared identity registration and publication remain gated.
