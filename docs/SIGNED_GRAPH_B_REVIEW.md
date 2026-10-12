# Signed Graph B identity, institution and temporal review

This private protocol follows the three-source equivalence handoff. It does not
publish a graph or replace a professional legal editor. The operator must have
accepted storage, local-processing, internal-display and export rights for all
three original public sources. Their exact source/mapping/identity heads and the
complete accepted same-decision equivalence history are bound to the review.

## Independent trust and appointment

Configure `LA_GRAPH_B_REVIEW_TRUSTED_KEY` with the path to an independently vetted
Ed25519 **public** key. Compose passes this variable to the API and worker services;
use the existing read-only `/graph-trust` mount, for example
`/graph-trust/graph-b-reviewer.pem`. This trust is separate from
`LA_GRAPH_TRUSTED_REVIEW_KEY`, which verifies public release attestations. The
application never generates signing keys or issues reviewer qualifications.

An active same-firm admin/curator account with `source.curate` must own all three
source reviews to request signing inputs. The signer must be a different active
same-firm account, absent from every pinned source, mapping, identity and prior
equivalence contribution. Separate accounts are necessary engineering evidence;
independence of actual people and professional competence require external vetting.

The signature binds an organizational appointment: explicit scope
`TR_decision_identity_institution_temporal_review`, start/end-exclusive dates,
a statement and SHA256 of retained opaque appointment evidence. It is not an
application-issued licence. Bytes are limited to 256 KiB, encrypted in the
private ledger, never parsed as instructions and never returned in responses.
A signature proves possession of the vetted key over the exact payload; it does
not independently prove legal truth or the credential's authenticity.

## Evidence and temporal boundaries

The review explicitly selects the decision date, with accepted passages from
both decision representations. A separate institutional-register assessment must
match the equivalence's institution/name/record and cover that decision date.
Its scope is **historical identity only**. It does not establish operational
activation, establishment, abolition, competence, territorial jurisdiction,
appellate effect or finality.

Each of the six source-specific `decidedIn`, `issuedBy` and `hasDecisionVersion`
relationships gets its own assessment. Unknown applicability has no bounds.
Closed intervals require a start and a strictly later end-exclusive date. Open
intervals require a start and explicit nonfuture checked-through horizon. Known
relations require exact accepted evidence from their own decision source; known
`issuedBy` additionally requires register evidence and coverage of the decision
date. No institution interval is automatically copied to any relationship.
Rationales and appointment statements remain private. Human reviewers must inspect
the actual passages: hash resolution checks engineering integrity, not semantics.

## Canonical external signing protocol

All endpoints require an authenticated authorized account; POSTs require CSRF.
Select three source IDs with
`/api/v1/public-sources/{source}/graph-b-review?peer_source_id={peer}&register_source_id={register}`.

1. GET the complete current state. Unconfigured trust can display history, but
   cannot accept new signatures. Configure trust outside the application.
2. The source owner POSTs to `/graph-b-review/request` with exact review and
   equivalence revisions, all pins, the independent reviewer account/public label,
   timezone-aware review timestamp, qualifications, appointment and base64 evidence.
   The response contains canonical `body_json` and `body_sha256`; it writes no review.
3. The vetted editor verifies every field and signs the exact UTF-8 `body_json`
   bytes externally with Ed25519. `decision` may be `approve`, `reject`, or
   `needs_changes`; if changed, reserialize the closed `SignedBody` with the shared
   `release_preparation.canonical` protocol before signing. No local signing API exists.
4. That reviewer account POSTs `/graph-b-review/accept` with
   `{envelope: {algorithm: "Ed25519", body: <canonical object>, signature: <base64>}, credential_data: <same base64 bytes>}`.
   The API verifies against the configured public key, all evidence, current roles,
   ownership, dates, revisions, ontology and source bytes before committing.
5. The curator screen refreshes signed-review state/history. It retains every
   accepted approval, rejection and change request. A later negative review blocks
   the earlier approval. An older payload cannot overwrite a newer revision.

The timestamp must follow all bound evidence reviews and the acceptance of the
preceding signed opinion. Appointment scope must cover the UTC review date and
remain unexpired for current approval. Key rotation, missing trust, ontology/source/
equivalence changes, ownership transfer or reviewer/operator deactivation withhold
current approval. Historical signatures and disagreements remain retained with
their original accepted-key snapshot; that snapshot never authorizes current use.

## Integrity, concurrency and release boundary

The complete encrypted append-only ledger and its projection must agree, with
contiguous revisions. Limits: 50 events, 8 MiB encrypted ledger, 256 KiB appointment
evidence. PostgreSQL source-head locks, active-account locks and CAS serialize
acceptance against source changes and competing signatures. Final source, key and
ontology checks withhold mixed output; failed acceptance rolls back its own event.

All responses remain firm-confidential. `publication_eligible`, `graph_updated`,
`legal_truth_verified`, `institutional_competence_verified` and `finality_verified`
remain false. Actual editor vetting, decision-specific public signing inputs,
separate audience publication permission and installation/activation qualification
are subsequent gates. Generic provision publication must not accept this ledger
or the earlier staged Graph B preparation marker.
