# Registered private analysis comparisons

This R05A development workflow runs **single-pass** and **bounded structural
correction** proposals from the same private draft. It freezes inputs before calls,
retains source-linked human observations and records declared active effort.
`capture_complete` means the required records are present. It never grants legal
approval, proves reviewer expertise/independence or establishes model benefit.

The scope is selected private evidence. Public/historical law, adverse-authority
recall, semantic correctness and Standard/Deep analysis remain unqualified. This
protocol does not replace the held-out release protocol in [EVALUATION.md](EVALUATION.md).

## Register before running

In **Çalışma notları → Yapılandırılmış analiz taslakları → Protokole bağlı özel
karşılaştırmalar**, prepare a protocol against a current draft with selected original
passages and an application step. Supply a title, question, human rubric, declared
example family, real/synthetic origin and two existing authorized matter members.
No sample type or reviewer is selected automatically. Demo/synthetic matters cannot
be declared real. Real origin is a declaration, not source consent or qualification.

The server returns a registration-context digest. Registration must match that exact
preview; a changed model, review, source version, recipe, budget or reviewer inventory
requires reopening it. The encrypted immutable protocol freezes:

- Exact analysis/version/revision and full input/content hashes; selected quote,
  source document/revision/span hashes and fact snapshots are already part of those
  inputs. The latest lawyer review is retained with its findings and content.
- Rubric text/hash, declared family digest, sample origin and two assigned identities.
  The operator, source-version author and previous reviewer cannot be assigned.
  The system does not discover near-duplicate families or certify expertise.
- Local model, tenant/configuration/credential fingerprints, provider/transport and
  proposal-policy pins, review/comparison recipes, semantic-dimension digest and
  research budget. Credentials themselves are never returned or sent to the browser.
- Server registration time and permanent request IDs for both arms. Creation of
  each job must follow registration. The protocol is not editable or resealable
  through an API; changing a protocol requires a new registration.

The selected-finding feedback contract is available through the typed registration
API. When explicitly selected, the same immutable findings and checksum accompany
both arms and every permitted repair pass. The initial browser form runs without
selected feedback; ordinary draft feedback selection remains available separately.
The rubric/reviewer metadata is not added to the model prompt.

## Run the existing bounded jobs

Only the registering operator can dispatch an arm. Both start from the frozen
private draft through the existing research queue, source/provider checks and
cooperative cancellation. Defaults are at most one pass/120 seconds for single-pass
and two passes/240 seconds for correction, each further capped by the configured
research budget. An extra pass occurs only when existing critical structural checks
remain. The maximum is three provider calls across the pair, not a deeper legal
research workflow.

Separate reservations may admit one arm and reject the other. The accepted job stays
visible. Repeating the run uses the permanent receipts and starts only a missing
arm. Failed, canceled, timed-out or restarted/stopped jobs are not silently rerun.
There is no remote-provider override, automatic retry, extra worker or new fallback.
This retains the already agreed exact laptop-tunnel exception without expanding it.

Candidates stay unadopted and cannot be applied by the normal adoption API. The draft,
its lawyer review and immutable version history remain unchanged. A candidate is
labelled **kaydedilmemiş model adayı**, not an invented saved revision. Actual
before/candidate changes, original quote spans, baseline findings, patches, prompt
measurements, rejected structural changes and job outcomes remain inspectable.

Measured job wall time includes the queue. Provider round-trip time sums retained
completed-call timings; it is **not GPU compute time**. GPU time stays unknown.
Interrupted/failed jobs retain partial passes, with total provider work/cost unknown:
a lost response is not evidence that no call occurred. No quality, time-savings,
cost-saving or Deep-mode gain is computed from these fields.

## Observe and account for effort

Each assigned reviewer signs in separately. Both arms require the existing six
semantic dimensions and all original finding dispositions, bound to the exact
execution and before/candidate comparison digests. Positive and repaired declarations
reuse [source-linked adjudication](ANALYSIS_ADJUDICATION.md): exact current sources,
actual changed steps and targeted meaning/strength observations are required.
Unresolved/unassessed observations can be recorded and remain explicit. Recording
an observation does not change the draft's lawyer-review decision.

This interface is **not blinded**: authorized matter members can inspect both arms
and recorded observations. Distinct accounts prevent one account from writing both
assigned judgments; they do not prove actual independence or expertise. The operator
and source author/previous reviewer are excluded, but reviewer selection itself does
not constitute legal signoff or benchmark adjudication.

Only the operator records active workflow effort. Each arm separately declares
non-overlapping preparation, verification/lawyer review and correction seconds.
Blank is unknown; explicit zero is allowed for a phase where no work occurred. All
three phases must be known with a positive total, and the operator must explicitly
confirm that shared setup is included consistently and full verification/correction
is counted. Waiting for inference is not active effort. Independent evaluation-review
seconds belong to each human observation and are separate from workflow preparation.
There is no automatic timer or inferred measurement.

Changes append immutable history using a client nonce, an expected **own** previous
record and an exact execution digest. Retries with the same payload return the same
record; changed payloads or competing updates conflict. PostgreSQL matter locks
serialize writes. Checks immediately before commit reject and roll back a changed
basis. Changes to facts, documents, draft/review, provider/policy/recipe/budget or
participant access retain prior evidence while withholding current completion.

## Inspect and download confidential evidence

The browser lists at most ten protocols per page, loads a selected capture explicitly
and polls active jobs every 2.5 seconds; three consecutive errors stop polling until
explicit refresh. Details are collapsed initially. The authorized JSON download is
a private evidence packet, not a public graph update or a scored qualification row.
It contains protocol, both job records, exact comparisons, immutable observation
snapshots, timing history, status, unknowns and false approval/benefit flags.
The attachment comes from a fresh authorized server capture with `no-store` and
`nosniff` headers; its canonical UTF-8 JSON retains the same 8 MiB bound.

History is capped at 60 observation events and 60 effort events per protocol; capture
JSON is limited to 8 MiB. An oversized append is rejected before commit without
truncating prior evidence. Protocol lists and all reads/joins/writes require current
matter access and the correct parent analysis. Shared graph datasets and production
source approvals are not modified. Existing encryption, retention and legal-hold
policies apply to these private matter records; a downloaded copy remains subject
to the firm's handling and retention obligations.

API prefix: `/api/v1/matters/{matter_id}/analyses/{analysis_id}/comparisons`.

| Route | Contract |
|---|---|
| `GET /registration-context` | Authorized current preview, eligible existing reviewers, context digest and eligibility |
| `POST /` | Typed registration with exact context/revision/version, nonce, rubric/family/origin and two reviewers; no inference |
| `GET /?limit=&offset=` | Bounded protocol metadata; maximum page size 20 |
| `GET /{id}` | Bounded confidential capture and role-specific current capabilities |
| `GET /{id}/export` | Fresh canonical private JSON attachment, authorized under a matter lock; no inference or publication |
| `POST /{id}/run` | Empty optional body; permanent arm receipts, operator only; unknown override fields rejected |
| `POST /{id}/observations` | Two source-linked arm assessments, assigned authenticated reviewer, nonce and own head/execution pins |
| `POST /{id}/effort` | Nullable strict integer phase times, strict inclusion booleans, operator only, nonce and own head/execution pins |

No arbitrary graph queries, source publication, outbound context, credential setup,
reviewer-account provisioning or automatic scorer conversion is added. Representative
lawyer adjudication, public/adverse gold evidence, actual provider evaluation and
full source/release/privacy qualification remain required before product claims.
