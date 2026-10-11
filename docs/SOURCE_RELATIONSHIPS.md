# Human review of source relationships

After comparing two retained packages, use **Kaynaklar arasındaki insan incelemesi**
to record an accountable opinion about their work/version relationship. The record
belongs to the authenticated firm. It does not merge public identifiers, publish
an assertion, grant source use, establish current authority or qualify independent
study originals. No relationship is inferred from filenames, statute numbers,
similarity, matching bytes or a comparison highlight.

The four classifications are **unresolved**, **same work and version**, **same work
with different versions**, and **different works**. Resolved opinions require:

- Current ownership of both individual source reviews by the submitting curator.
- Accepted source-identity assessments in both dossiers.
- Explicit work and version references for each exact source, internally consistent
  with the classification. These are human declarations, not a national identity registry.
- A supporting reference/hash distinct from the comparison receipt. The server
  does not acquire that document or attest its authenticity/independence.

Unresolved opinions still require both owners and an exact comparison but need not
invent identities or a positive identity assessment. Independent publication,
rights, legal-effect, fidelity, privacy and study reviewers must separately inspect
actual evidence. `resolved_for_handoff` describes this bounded opinion only.

## Evidence and history

One canonical unordered pair ID exists per firm, regardless of selection direction.
Each new opinion binds both full immutable artifact sets, both source-review
revisions and historical owner/identity events, the exact regenerated 2,000-code-point
comparison receipt and hash, the authenticated reviewer, server timestamp,
classification, rationale, references and optional declared effort. Clients cannot
provide an actor, recording time, raw comparison text or a digest override.

Unknown effort remains null; explicit zero remains a declaration. The duration
describes only the relationship assessment, excluding source-review work already
declared elsewhere. Neither viewing nor saving starts a timer. Effort cannot grant
rights, affect classification or demonstrate productivity.

Encrypted append-only events retain disagreements and superseded opinions. Reads
verify every event, reconstruct the latest projection and verify historical pins
against both complete source ledgers. Missing/corrupt records fail closed. Any
change to either source dossier makes the retained latest opinion Stale; its prior
content remains unchanged. Renewal requires another explicit opinion against fresh
versions and evidence. There is no transitive identity closure, automatic mapping
change, release modification or silent study deduplication.

## API and boundaries

Prefix `/api/v1/public-sources/{source_id}/relationship`, with required query
`other_source_id=<exact package SHA256>`:

- `GET`: virtual revision 0 if absent; no write/backfill. Returns current source
  pins, latest opinion, last 50 events, explicit truncation, stale/readiness flags.
- `POST`: strict input with `expected_revision`, `expected_source_revisions`
  (exact source ID → revision map), `classification`, `rationale`, `identities`,
  `comparison`, `evidence_refs` and optional `effort`.
- `GET /export`: freshly authorized unsigned, firm-confidential JSON containing
  the same bounded state/history and exact retained comparisons. Stale state stays
  explicit. The browser never falls back to a previously loaded export.

Comparison input contains `passage_id`, `other_passage_id`, passage-relative
`offset`/`other_offset` (0–20,000) and the viewed `evidence_sha256`. Both complete
packages and the selected actual passages are verified locally; a mismatched hash
fails. A resolved identity list contains exactly two `{source_id, work_ref,
version_ref}` entries. Evidence references use the existing strict reference/SHA256
contract. Effort uses the existing declaration basis and 0–86,400 strict seconds.

Existing curator/admin, live `source.curate`, firm isolation, CSRF and authorization
locks apply. Writes lock the account/session and both source heads in canonical
order, compare revisions, use a pair-head compare-and-swap and recheck identity and
source pins before commit. Duplicate/conflicting requests return 409 without a
second event; callers manually refresh after conflicts or unknown outcomes. Each
pair is bounded to 200 events. There is no background retry or overwrite.

Refresh, selection/window change, unmount and observed access denial abort/discard
browser work. Reads, saves and exports have a 30-second client cancellation deadline;
a timed-out write has an unknown outcome and must be read before resubmission.
Untrusted opinions and references render as escaped text. The record and downloads
are confidential even though the underlying originals are public. Disconnected
clients/downloads cannot be retroactively erased; normal firm retention, encrypted
backup and handling rules apply. No inference, network fetch, parser, public graph
or private matter participates.

The two additive SQL tables use the existing initialization and encrypted store;
they neither rewrite old review events nor change old source/preparation manifests.
Qualification and publication tools do not consume these opinions automatically.

## Qualification boundary

The engineering suite and disposable browser use invented identity, support and
effort declarations on synthetic sources only. Real PostgreSQL races demonstrate
one winning pair revision and rejection after a changed source pin. They do not
adjudicate 6101 manifestations, establish independent originals or approve a corpus.
Actual qualified curator review, independent reference intake, registered witnessed
paired studies and target-host/pilot acceptance remain outstanding.
