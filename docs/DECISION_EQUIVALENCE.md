# Reviewed decision equivalence and institutional-register evidence

This R03 workflow records an explicit claim between **two retained decision sources**
and one separate retained institutional-register source. It never merges stored
identities, changes identity reservations, establishes institutional competence,
publishes RDF or calls an inference provider. Public source acquisition remains the
existing controlled intake process; an online URL or an official-looking domain is
not physical evidence or automatic approval.

## Review contract

`GET /api/v1/public-sources/{source_id}/decision-equivalence` selects
`peer_source_id` and `register_source_id` as query parameters. All three source IDs
must differ. Reversing the two decision sources addresses the same confidential
context; changing the retained register selects a separate evidence context. No
context becomes a global identity resolver and no transitive equivalence is inferred.
Parallel register contexts may disagree; they remain distinct and unqualified.

`POST` on the same route proposes; `POST .../decision-equivalence/review` records
an independent opinion. Closed, typed inputs require the current aggregate revision,
all three source/mapping revisions and both identity revisions. The proposer must be
the current review owner of the selected decision source. The reviewer must have
current curator/admin role, `source.curate`, a valid session/CSRF and a different
account from the proposer and **every contributor in the complete pinned histories**:
three source reviews, three mapping ledgers and both canonical identity ledgers.
Ownership transfers cannot erase contributors. Separate accounts do not establish
separate people, professional qualifications or freedom from conflicts of interest.

Both decision identities must have current independent acceptance. All three sources
need accepted rights, source-identity, extraction and legal review, including local
processing/display rights. Every old identity/institution/reviewer reference must
resolve to an exact retained passage among these sources, with its SHA256 and accepted
extraction coverage. Unresolved URLs, external registers and free-text references are
withheld until explicitly rebound to retained evidence. The chosen register is a
reviewer-declared **institutional identity record**, not a court-competence register.

## Claims and uncertainty

The proposal records `same_decision`, `different_decision` or `undetermined`, a typed
historical institution ID, its reviewer-declared registered name and register record
reference. Proposal and review each need physical evidence from **all three sources**;
there is no hash-only, partial or inferred register evidence. A SHA/offset match proves
the retained text, not whether a human correctly interpreted that text.

For `same_decision`, the two accepted identities must have the same proceeding and
historical institution IDs. The proposer explicitly chooses `canonical_decision_id`
from the two already reviewed decision IDs; a new third ID cannot be minted by this
workflow. Different/unknown claims require a null candidate. Matching docket numbers,
names, dates or text never supplies this choice automatically. Both original decision
IDs and source-bound version IDs remain unchanged. This reviewed choice nominates an
anchor for a later candidate handoff, not an authoritative national alias registration.

The screen exposes both distinct identity/version tuples, exact revision pins, the
proposed anchor and complete preserved opinions. Rejection, requested changes and new
proposals do not overwrite earlier agreement or disagreement. Any source, mapping or
identity revision change makes prior acceptance stale; reaccepting a source/identity
does not silently revalidate the equivalence claim. No effective interval, succession,
territorial/subject competence, finality or binding force is inferred from the register.

## Confidentiality, integrity and bounds

Heads and immutable events are encrypted and firm-scoped. Source selection, curator
names, rationales, opinions and comparison claims remain private. Original artifacts
are verified again before response/commit. Complete bounded ledger replay validates
event sequences, historical input snapshots, contributor sets, pinned identity tuples
and current projections. Old acceptance cannot replace a later rejection.

All mutations lock actor/session and source rows in deterministic source-ID order,
use a unique context plus an optimistic aggregate revision, and recheck roles, complete
captures and originals before committing. Reads recheck captures and ledgers before
return. Scope changes abort requests and clear the selected UI; denied access clears
private state. A stale/conflicting response clears the displayed comparison until it
can be refreshed against the selected identity revisions.

Engineering bounds: 50 equivalence events, 30 distinct proof passages per proposal or
opinion, 4 MiB for complete input histories and 2 MiB for the encrypted equivalence
ledger. Original source, mapping and identity limits still apply. Oversized/corrupt
histories withhold the complete action; there is no silent truncation or automatic
retry. These bounds may require a separately designed archival/versioning workflow.

`identity_reservations_changed`, `global_registry_qualified`, `legal_effect_verified`,
`institutional_competence_verified` and `publication_eligible` stay false. Institutional
identity equivalence, new register versions, multi-decision segmentation, national alias
governance and decision-specific publication qualification remain separate work.

## Successor handoff

The next packet carries all three original source packages, complete private histories,
the reviewed canonical-anchor choice and exact register evidence into a deterministic
private Graph B preparation artifact. Its RDF relationships must remain unreviewed,
with unknown validity and a publication-blocking marker. It must not promote reviewer
identities, opinions, source-selection links or an unqualified equivalence to shared
graphs, and must not manufacture ontology/assertion approval or signing credentials.
