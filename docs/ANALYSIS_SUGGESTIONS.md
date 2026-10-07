# Bounded private-analysis proposals

This R05A slice adds local-model editing proposals to a saved
[private rationale](ANALYSIS_WORKBENCH.md). A proposal is a separate, encrypted,
matter-authorized job. The lawyer inspects it and the original passages before
explicitly adopting it as a new **Needs review** version. Completion and adoption
grant no legal approval. No existing version or fact-ledger entry is overwritten.

## Workflow and fixed inputs

In **Çalışma notları → Yapılandırılmış analiz taslakları**, open
**Yerel modelden düzenleme önerisi** on a current saved version. Choose a budget,
request a proposal, compare its application/conclusion changes and notes against
the selected passages, then provide a change reason to adopt. History is loaded
on request; creating or visiting a draft never starts inference automatically.

The model may propose application rationale, assessments of existing conditions,
conclusion text, additional uncertainty, next action and review notes. Issue,
posture/date, premises and ledger roles, original source selections and ranges,
rule candidates, conditions/exceptions and required polarity, application premise
links, alternatives, conclusion dependencies and requested disposition stay fixed.
Existing assessments cannot be deleted; uncertainty cannot be removed. Review-note
targets and source IDs must already exist in the pinned draft. No model output can
change permissions, graph assertions, provider configuration or review state.

Private facts and exact selected quotes are necessary inference inputs. The fixed
envelope excludes filenames, acquisition paths, matter/owner/tenant metadata and
credentials. It retains opaque fact and evidence IDs to bind proposed edits.
Documents and draft text are untrusted data. The deterministic critic validates
declared references and conditions; it cannot establish semantic entailment,
identify all omitted issues or qualify Turkish legal reasoning.

## Inference, budgets and correction

| Option | Maximum calls | Total job budget | Additional call |
|---|---:|---:|---|
| Single proposal | 1 | 120 seconds | None |
| Structural repair | 2 | 240 seconds | Only when critical structural checks remain after the first proposal |

The configured shared research budget may reduce these limits. Every call has a
remaining-time bound of at most 120 seconds and **1,000 completion tokens**; it
uses the existing guarded relay. The complete canonical message envelope is
measured before transport: serialized UTF-8 bytes plus framing and completion
reserve are conservatively compared with the configured context limit. Oversized
input fails; the service never silently truncates it. The measurement is not a
tokenizer count. The provider response is bounded to 64 KiB, and model patch text
to 32 KiB, with strict field/list/text limits and duplicate-JSON-key rejection.

Authenticated local-model metadata, configured tenant binding, model identity,
context capacity, transport and disabled cloud fallback use existing provider
checks. A valid configured provider still requires runtime readiness for each call.
No fallback, tools, redirects or automatic retry are admitted. The existing exact
approved laptop tunnel remains an optional exception, disclosed as using the
internet; it does not constitute disconnected air-gapped operation.

Each candidate is re-resolved against current private sources and run through
`private-rationale-checks-v1`. A patch introducing a new critical check ID is
rejected and the earlier candidate retained. Existing critical defects can remain;
their dependent conclusion stays withheld. Removing a structural defect is not
proof of legally correct self-correction. A notes-only or unchanged proposal cannot
be adopted as an analysis revision. The repair pass is the same local model, not
independent legal adjudication or qualified Standard/Deep research.

## Jobs, integrity and human adoption

The shared queue retains its five workers, ten admission slots, coordinator lease,
deadlines, cancellation checkpoints and recovery behavior. Records store IDs in
the queue and encrypted private content in the matter store. Provider exceptions
are represented by safe error codes, without raw upstream errors or secrets.

| Method relative to `/api/v1/matters/{matter_id}/analyses/{analysis_id}/suggestions` | Purpose |
|---|---|
| `POST` | Start against exact `expected_revision`, `version_id`, a 32-hex `request_id`, and `mode: single/repair` |
| `GET` | Authorized history, default 10 and maximum 20 per page, with offset |
| `GET /{job_id}` | Retained status, candidate, freshness, iterations and notes |
| `POST /{job_id}/cancel` | Record cooperative stop intent; no guarantee that upstream compute stops immediately |
| `POST /{job_id}/adopt` | Append a version using exact candidate SHA-256, expected revision and change note |

Request receipts bind user, analysis and exact request content. Repeating the same
request ID returns the original job, including a terminal job; it never starts
duplicate inference. Reusing it for different content returns 409. A new request
ID is required for an intentional rerun. The UI retains its pending ID after a
network error to make a retry safe. After a page reload, inspect history to recover
the recorded outcome rather than assume a lost response means no job exists.

Authorization, archive state, analysis version, selected fact/document/passage/
contradiction dependencies, the source version's latest human review ID, recipes and provider model/policy/route pins are
rechecked at checkpoints, final publication and adoption. Changed dependencies
make completed output stale and ineligible without rewriting its retained text.
New review findings therefore block older proposals; an adopted new version starts
unreviewed. Review prose is not automatically supplied as model feedback in this slice.
See [human review binding](ANALYSIS_REVIEWS.md).
An adoption transaction locks the matter before the job and revalidates source
bindings, candidate hash and revision. Competing adoptions yield one appended
version and a 409 conflict. Another authorized member may review/adopt a matter's
proposal; customer tags do not confer that authorization.

Cancelled, failed, timed-out or interrupted jobs may retain an earlier checked
candidate as explicitly partial output; they cannot be adopted. Stop intent is
distinct from compute acknowledgement. Cancellation during a call waits for a
checkpoint and blocks its output. Restart recovery never restarts a model pass.

Each retained iteration records prompt digest/measurement, provider duration,
typed patch, declared checks and acceptance/rejection. Unadopted candidates retain
model origin without claiming a human author. Adopted drafts retain proposal ID,
source version, model/policy, passes, prompt digests, unverified review notes and
adopting user. Later manual revisions preserve that lineage; immutable history
retains earlier contributions. DOCX/PDF and the UI disclose AI assistance. Exports
still select an exact version and recheck access/freshness after rendering.

## Qualification boundary

Tests and browser examples use invented documents and mocked inference. Real
PostgreSQL tests verify adoption contention; isolated Linux checks verify the
copied code. These establish engineering behavior, not live-model capability,
legal accuracy, benefit from longer inference or production performance.

R05A remains partial: reviewed public/historical authority synthesis, semantic and
adverse verification, broader correction, calibrated Standard/Deep modes and paired
lawyer-adjudicated comparisons are open. R05B's sanitized BYOK adapters remain
separate planned work. See [verification](VALIDATION.md),
[analysis requirements](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md) and [roadmap](ROADMAP.md).
