# Read-only independent-review outcome reconciliation

Engineering scope: R03/R05A, private source review. This extends the separate
[successor review](PARENT_LINEAGE_AND_SUCCESSOR_REVIEW.md); it does not qualify
the corpus, establish current legal applicability or grant source access.

## Lawyer workflow

1. Independently select the frozen context through the authorized portfolio.
   Restore the captured customer OR selection, workspace date field/range,
   source-record date range and review bucket. Observe exact identities and
   explicitly request new review content. Roles, observations and notes start blank.
2. On submission, keep only a bounded request receipt in the current component:
   nonce, canonical request digest, frozen manifest/version and expected previous
   review ID. A response is followed by explicit read-only observation. Ambiguous,
   truncated, gateway and pending responses use the same observation path.
   Clear source passages, form data and decision notes; never retain a replay body.
3. Explicitly observe the original submitting actor's exact request. Display
   context, review and predecessor admission separately. An unobserved result
   establishes neither absence nor retry permission. Pending records stay pending.
4. For a completely admitted outcome, separately verify the exact historical
   event against fresh authorized metadata, with matching request observations on
   both sides. A new opaque session token carries a cloned filter selection and
   the selected event's packet hash. A later head or newer analysis version is
   displayed separately and cannot replace the selected decision or frozen evidence.

No observation opens source content, creates another review, finalizes admission,
repairs history or confers legal approval. Source inspection/export and every
future independent review retain their existing current rights/private-basis guards.

## API and identity contract

`GET /api/v1/matters/{matter}/analyses/{analysis}/source-contexts/{context}/reviews/reconciliation`

Accept exactly one of each declared receipt field: `request_id`,
`expected_request_sha256`, `expected_manifest_sha256`, `version_id`, and optional
`expected_review_id` (omitted for no predecessor). Reject extras, duplicate keys
and malformed identifiers. Responses use `Cache-Control: no-store`.

The review key is derived from context + authenticated submitting user + nonce,
as in the existing write path. Require active explicit matter content access and
scope before decryption; verify the stored event owner before decrypting its
packet. Administrator status/customer tags do not bypass these checks. Another
lawyer's session cannot resolve the original actor's request.

Verify the context manifest and immutable packet, review recipe/dimensions,
canonical submitted input and nonce/digest, exact manifest/version, predecessor
identity/packet, consecutive sequence, source-selection completeness and typed
admission proofs. Recheck the original reviewer's current independent-review
permission. Lock the matter consistently with existing review/version operations.
No current-head scan, source retrieval, inference, publication or mutation occurs.

The closed response has `verified`, `not_observed` or `unavailable` outcome.
Only verified observations contain context/event metadata and admission states.
`current_head` and `source_verification` remain `not_checked`;
`legal_readiness` remains `not_established`; qualification/replay flags remain false.

## Confidentiality and uncertainty

Receipts and a matter's selection of public authorities are confidential metadata.
Keep them in the authorized matter/session boundary, outside shared Graph A/B,
external queries, assistant context, browser persistence and portable URLs. URLs
carry existing opaque session tokens and authorized record IDs only. Reload,
principal change, expiry or loss of scope closes the handoff. Scope/filter changes
retire in-flight responses and clear forms, result metadata and follow-up links.

A completed record observation does not prove current source rights, current
private facts, reviewer agreement, legal effect or absence of a competing later
decision. A pending admission is never completed by GET. An unavailable lookup
does not authorize replay; any later independent task starts through a new explicit
authorized selection and fresh review context.

## Qualification and continuation

Automated cases cover exact-actor isolation, explicit membership, cross-context
routing before decryption, request/manifest/version/predecessor substitutions,
resealed inconsistent sequences, malformed admission proofs, pending finalization,
source withdrawal and absence of source/head/write effects. Real PostgreSQL checks
serialize observation with a later opposing review. Browser rehearsal uses invented
documents and separate accounts with explicitly granted memberships; source rights
are simulated. It covers successful/truncated/gateway/pending and non-dispatched
writes, exact-event navigation after an opposing head, two customers/both date
ranges, late replies, reload and wide/narrow layout. These are engineering results.

[Evidence](evidence/independent-review-outcome-reconciliation-2026-10-15.json)
records final counts and code hashes. Existing seven CI jobs, two-worker limits,
deadlines, exclusive complete backend partition and no automatic retry remain.
Exact-head hosted checks, merge/main, deployment and legal qualification are
separate evidence states. R03/R05 remain partial.

Continuation: [guarded direct portfolio return](RECONCILED_REVIEW_PORTFOLIO_RETURN.md)
retains the selected historical event and original comparison baseline, with fresh
selected-versus-current observations and no replay or source content.
