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
