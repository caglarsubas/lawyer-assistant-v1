# Exact-version local analysis context preview

R05A-06 adds a local, read-only budget preview before requesting a private
analysis suggestion. It addresses a safely withheld pilot attempt; it does not
retry that attempt, change its source version, or establish successful inference.

## Lawyer workflow

1. Open a saved analysis and its local-model suggestion section. Select the
   single/repair mode and, optionally, specific existing review findings.
2. Choose **Bağlam bütçesini hesapla**. The server resolves the exact authorized
   saved version, its source and review dependencies, and the configured provider
   pin. It performs no provider probe, generation, queue reservation or record write.
3. Inspect full serialized-message size, framing and completion reserves, space
   remaining or excess, and frozen passage revisions, ranges and hashes.
4. Request a suggestion only if the first pass fits and configuration checks pass.
   The browser submits the preview fingerprint; the server resolves and measures
   everything again. A changed context requires a fresh preview.

Changing mode, selected findings, workspace, analysis version or observed review
head clears the browser preview. Failed or late preview responses cannot restore
an earlier context. Previews are held only in component memory, not local storage,
URLs, public datasets or portfolio events. Existing authorization, CSRF and
`Cache-Control: no-store` apply; source selections and digests are private metadata.

## Accounting and submission contract

`POST /api/v1/matters/{matter_id}/analyses/{analysis_id}/suggestions/context-budget`
accepts the existing typed suggestion inputs, including its request ID. Previewing
does not consume that ID or create an idempotency receipt. The result includes:

- Exact source version/revision, content digest and current review identity.
- Mode, maximum pass count, model and approved transport disclosure.
- The unchanged `proposal_messages` / `prompt_measurement` result: complete
  canonical JSON message bytes, a 256-unit framing reserve and 1,000-unit output
  reserve, measured against the existing configured context bound.
- Exact frozen private evidence references and a context fingerprint bound to the
  requesting user, matter, analysis, options, resolved envelope and provider pin.
- Separate `fits`, static `configuration_ready` and `can_start` observations.

These conservative UTF-8 accounting units are not observed tokenizer usage,
hardware capacity, live authentication, semantic completeness or legal quality.
Full selected text remains in the existing authorized message construction; the
preview response contains metadata rather than another copy of private prose.
Selected review/public-authority findings use the same guarded resolution as the
actual job and are included in its measured envelope. Retained authority grants
and publication checks are not relaxed.

Submission optionally accepts `context_preview_sha256` for compatibility with
existing registered comparison and authority-trial clients. A supplied mismatched
fingerprint fails with 409. **Every new submission**, including callers without
a preview, is measured and rejected with 422 before queue reservation when it
exceeds the bound. Existing receipt replay returns the original attempt rather
than creating another job. A fitting new job retains the admitted preview; the
first worker pass must reproduce its exact measurement. Each later repair pass
is independently remeasured by the existing provider before transport. Initial
fit is not a promise that a changed repair envelope will fit or succeed.

The preview recipe is `private-analysis-context-budget-v1`; the model envelope
and proposal recipe are unchanged. No context limit, completion allowance,
timeout, model, transport, credential, fallback or permission is increased.

## Overflow and preservation

An oversized analysis is neither shortened nor rewritten. No adverse authority,
unknown, allegation, condition or source is automatically removed. A lawyer may
use the existing editor to prepare a separate, focused unreviewed version with
explicit scope gaps; its exact selections and new history must be inspected.
This delivery provides no automatic narrowing or larger-context qualification.

Prior analyses, review events, failed attempts and private originals remain
unchanged. Preview and model output cannot confer human or independent review.
Owner review, source rights, historical law qualification, real inference and
held-out legal metrics remain separate open gates.

## Engineering evidence

Synthetic tests exercise zero-write/no-network previews, UTF-8 exact accounting,
one-unit overflow and exact-fit boundaries, no silent truncation, exact admitted
versus executed first-pass measurement, stale version/document/review/model/access
rejection, selected private/public findings, revoked source permission, absent
credentials and retained failed-attempt history. The browser rehearsal exercises
initially disabled start, oversized and fitting contexts, and mode invalidation
in a disposable loopback-only workspace. No personal-case text or identifiers
belong in repository tests, reports or GitHub.

The [synthetic verification record](evidence/analysis-context-budget-2026-10-20.json)
binds the implementation files and records the observed checks separately from
hosted CI and deployment.

Hosted exact-head and merged-main checks, CI reserves, installation and actual
private-case acceptance must be reported separately. Existing nine CI jobs, full
test allocation, worker counts, timeouts and five 30-second reserve gates remain.
