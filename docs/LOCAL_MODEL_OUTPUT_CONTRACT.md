# Bounded local analysis output

R05A-08 corrects an observed generation failure: generic JSON mode could expand
an answer until the unchanged completion limit, returning `finish_reason=length`
and an unfinished document. That is a provider completion failure, not evidence
that a legal draft was evaluated and rejected. Historical attempts and their
original diagnostic codes remain unchanged.
The historical generic `ProviderError` did not retain its finish reason; its
exact transport outcome cannot be reconstructed. The truncation mechanism was
reproduced with synthetic data, rather than retroactively asserted for that case.

Private analysis proposals now request a finite JSON schema through the existing
local provider. The same standard-library contract module is shipped in the API
and isolated relay. The relay admits only four exact server-owned variants:
ordinary proposals, selected review findings, selected public-authority findings,
or both. Arbitrary schemas, remote references, expanded string/array limits,
changed strictness and extra request fields are rejected. The only schema
references are fixed internal definitions. Existing generic quotation requests
retain their separate JSON-object contract.

The schema permits short application/conclusion edits and review notes; selected
finding responses remain explicit. It cannot change the original facts, rules,
sources, node links or requested disposition. A normal `stop` response must pass
independent wire-shape/duplicate-key/length checks, then the existing typed patch,
fixed-target, evidence, review, authority and structural checks. A valid schema
does not establish entailment, legal applicability or a human review. Generated
proposals remain separate until explicitly adopted into a new unreviewed version.

New context previews and worker/provider measurements include the complete
serialized response contract and its digest alongside the unchanged complete
message envelope. No selected evidence is trimmed. The 256-unit framing reserve,
1,000-token completion allowance, configured context limit, model pin, timeouts,
local-only routing, tunnel disclosure and fallback prohibition remain unchanged.
Changed fingerprints and oversized requests fail before queue admission.

Incomplete completions and contract violations now retain separate safe error
codes/messages. Provider text, exception payloads and credentials are not reflected
in errors. There is no automatic application retry, schema relaxation, truncated
JSON repair, JSON-object fallback or replacement of an earlier attempt.

An isolated relay rehearsal used only invented input and no private volumes or
published ports. Its bounded native-provider response stopped normally and passed
typed, draft-scoped validation while preserving fixed premises. See the
[engineering record](evidence/bounded-analysis-output-2026-10-21.json). Hosted CI,
merge, guarded installation and the authorized private rerun are separate receipts.
Owner review and legal/source qualification remain open; case payloads, scope
selections and evidence fingerprints do not belong in this document or GitHub.

## Finished prose and fixed references

R05A-09 addresses a separate limitation: a normal structured completion can still
confuse page locations with clause identifiers, or finish a string at its grammar
limit in the middle of a sentence. JSON validity does not catch these defects.

Proposal recipe `private-analysis-proposals-v4` uses four closed
`private_analysis_v2` contracts. Each generated prose field has a smaller
180-character ceiling, a plain-text sentence-ending pattern, and an instruction
to finish well below that ceiling. Numbered facts and references remain in the
existing fixed draft, exact source quotations and typed link fields. The model
cannot restate numerical locators, dates or amounts in editable prose. This
restriction applies only to model proposal prose; it does not remove numbers,
formatting, partial sentences or any bytes from original sources, saved versions,
human-authored drafts or their displays. Source and node identifiers retain their
separate contract and exact-target validation.

Independent validation rejects prose containing numbers or recognized Roman
locators, missing terminal punctuation, formatting, a reached character ceiling,
an ellipsis, empty punctuation or a declared dangling conjunction. It never cuts
text, appends punctuation, substitutes a guessed reference, or retries a call.
Failures retain the safe `provider_output_prose_invalid` diagnostic without
reflecting generated text. Existing attempts and diagnostic codes stay intact.

These are bounded reference-surface and sentence-boundary checks, not a complete
Turkish grammar checker or proof of entailment. Spelled-out references and other
unsupported interpretations still need source inspection and lawyer review.
Accepted candidates remain separate from the saved analysis until explicitly
adopted into a new unreviewed version. Human review cannot be inferred from a
machine check, a native rehearsal or an assistant's inspection.

The full changed prompt and schema are measured together; no context, completion
or time limit increases. A fresh preview is required for the new fingerprint.
The relay admits only the new four exact contracts, so a guarded installation
must update the API and relay together while research is idle. No migration or
rewriting of historical proposals or original documents is required.
