# Separate-account semantic and adverse observations — R05A

A second lawyer account can inspect one exact retained [authority comparison](AUTHORITY_COMPARISONS.md),
its before/after private drafts, original public passages, historical identities and
findings. The account must differ from the candidate draft author, original authority
reviewer and comparison author. This enforces account separation; it does not certify
professional credentials, actual reading or independence between people.

In **Work notebook → Structured analyses → Public-authority context → Lawyer source
review → retained review → Findings-linked draft comparison**, open a retained comparison
and expand **Separate reviewer: semantic and adverse-authority assessment**. Load inputs
explicitly. No outcome, evidence, target, time or adverse scope starts selected.

Record all six semantic dimensions: passage meaning/entailment; facts, roles, allegations
and negation; premise/application/conclusion consistency; conditions, exceptions,
chronology and missing elements; adverse material and coverage gaps; conclusion strength
and uncertainty. Choose supported, needs change, unresolved or not assessed, and explain
each. Separately agree, disagree, leave unresolved or mark unassessed **every** original
source/dimension disposition. Agreement is with the comparison author's declaration;
it neither closes the original finding nor establishes a repaired legal argument.

Assessed declarations require exact draft targets, private quotation references and
original public-source indices. Supported semantic declarations need candidate-side
targets and quotations. Agreement/disagreement on a finding must include that finding's
own original public source. These bindings cannot prove semantic correctness.

Declare adverse scope as **not searched** or **selected sources inspected**, explicitly
identify inspected sources and explain limitations. Positive adverse declarations must
use inspected selected sources. This packet does not acquire new authorities or run
external searches. Inspection of selected supporting sources is not proof of independent
corpus-wide adverse discovery. Full-corpus coverage and adverse recall remain unknown.

Counts expose declared assessed/total semantic dimensions and original findings, keeping
unresolved/unassessed entries visible. They are not correctness scores. Optional strict
whole-second review time (1–28,800) is a manual observation; blank stays unknown. It does
not measure full preparation time, baseline performance or product benefit.

## Immutability, confidentiality and disagreement

Every encrypted immutable record binds the complete original comparison, source quotes,
private versions, account exclusions, rubric, assessment and SHA-256 seals. Each reviewer
has a separate serialized head: one reviewer revising a judgment makes only their prior
judgment Stale. Other reviewers' latest conflicting judgments can remain Current. History
preserves disagreement without silent consensus, voting, winning verdicts or score export.

Current describes available technical bindings. A changed comparison, draft, evidence,
research/review dependency, rubric or reviewer access makes observations Stale. Original
text is preserved and export is blocked. Revoked public permission, changed pins/bytes,
unavailable ancestor records or pending post-commit admission make content Withheld:
`snapshot: null` hides all potentially quoting notes and draft/source contents. Authorized
account/date/sequence/seal metadata remains available. Known child denial clears cached
comparison, finding and authority-context views. Previously downloaded local copies
cannot be retracted.

Workspace row locking, exact per-account nonce replay and expected reviewer head prevent
competing writes. A changed request under the same nonce or stale head conflicts. Writes
flush/expire and recheck bindings before commit; a separate receipt follows clean exit
from the public guard. A late committed failure returns only a pending ID and HTTP 409.
Identical replay never completes a pending receipt. Fresh inputs/nonce create a new record.

JSON/DOCX/PDF exports require latest Current state for that reviewer and recheck sources,
dependencies, membership and head after rendering and at guard exit. Failure discards all
attachment bytes. New record families use generic private erasure, retention, legal-hold
and encrypted-backup inventories. Notes never enter public graphs, other matters or model
prompts. Drafts, blockers, ordinary review decisions and original findings remain intact.

## API and bounds

Base: `/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews/{review_id}/comparisons/{comparison_id}/adjudications`.

| Method/path | Operation |
|---|---|
| GET `/context` | Exact comparison/rubric/excluded accounts, SHA-256, own head, eligibility |
| POST `/` | Strict complete semantic observations, finding judgments, adverse scope, note, optional time, exact basis/head/nonce |
| GET `/` | All reviewers' paginated private metadata; default 10, maximum 20 |
| GET `/{id}` | Current/Stale/Withheld projection |
| GET `/{id}/export?format=json\|docx\|pdf` | Authenticated revalidated attachment |

Six semantic observations plus up to 8 sources × 6 original finding judgments; at most
24 before/after target references, 20 private quotes and 8 public-source indices per
observation. Notes/limitations are 3–2,000 characters with three nonblank characters.
Duplicate, foreign, boolean/fractional indices, extra fields and partial dimensions fail.
Canonical input is at most 128 KiB; record/response is at most 6 MiB including a 2 KiB
reserve. At most 100 records per comparison across all accounts. Over-limit saves are
rejected atomically. Record kinds fit the existing PostgreSQL schema; no migration is
needed. There are no new provider calls, graph mutations or network permissions.

## Qualification and next packet

Synthetic observations and simulated source rights test engineering behavior only.
Representative lawful source packs, actual independent legal adjudicators, historical
identity/effect review and held-out evaluation remain required. R05A stays partial.
These observations can now be pinned by [registered fixed-evidence human revision
trials](REGISTERED_AUTHORITY_TRIALS.md), with registration before revision and explicit
original/revised work time. No model benchmark, statistical benefit or source-use
permission is inferred. Next: confidential authority-trial cohort reconciliation. See [roadmap](ROADMAP.md), [evaluation](EVALUATION.md)
and [verification](VALIDATION.md).
