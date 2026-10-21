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

## Finished prose and source-qualified references

R05A-09 separates source-label correctness from JSON shape. Proposal recipe
`private-analysis-proposals-v11` uses four closed `private_analysis_v7` contracts.
The ordinary pass proposes at most one application edit and one review note;
its generated uncertainty array stays empty. Existing uncertainty, facts, roles,
rules, conditions, links and all other applications remain in the fixed draft.
Selected review/authority variants retain their bounded multi-finding responses.

Each prose field must finish a plain sentence. The sampling grammar permits
canonical `m.N` and `s.N` labels inside that sentence, so a legitimate abbreviation
is not mistaken for its end. The field ceiling is restored to the original 400
characters; reaching it still causes rejection. This avoids forcing an otherwise
complete sentence into the unsuccessful smaller ceiling. The overall completion
allowance remains 1,000 tokens, the call limit 120 seconds, and the configured
context limit and full-envelope accounting remain unchanged. There is no text
slicing, punctuation insertion, guessed citation replacement or automatic retry.

The wire layer rejects incomplete boundaries, dangling abbreviations, formatting,
opaque prose citations, placeholders and numbers outside the canonical label
forms. Fixed-target validation then qualifies each label against its permitted
source scope. A private contract-clause label requires both the fixed rule's
explicit label and a matching heading at the beginning of its exact quotation.
A page label comes only from an exact extractor locator, never from a filename or
authored inference. A page cannot silently become a clause. Unresolved labels
fail closed. Public authority numbers require a separately qualified provision
mapping; the existing exact authority links remain available without inventing
numbers in prose.

This is lexical source-label qualification, not proof of legal authority,
applicability or entailment. The sentence guards are not a complete Turkish
grammar checker. Unknown facts cannot be treated as invalid legal acts merely
because a response passed these checks. Lawyer review and independent semantic
qualification remain mandatory; reviewed status is never inferred.

Safe diagnostic categories distinguish reference, boundary, field-limit and
format failures. Unqualified source labels retain a separate safe code. Historical
attempts keep their original outcomes; later diagnostics do not retroactively
classify a previously generic error. Whenever usage is reported, invalid token
counts or reported completion/context overruns reject the response. Missing usage
is not a measured zero or evidence of an enforced upstream budget. A provider may
perform internal work, so one HTTP completion request is not proof of one physical
model generation; private qualification must inspect the reported aggregate usage.

Full prompt and schema bytes participate in the new fingerprint. API and relay
must be installed together while research is idle. Private development rehearsals
use the same source/permission checks in read-only transactions, with encrypted
receipts and unchanged case/review records. They are separate from application
jobs, hosted CI, merge, installation, adoption and human review. No case payloads,
identities, selections, fingerprints or execution measurements belong in GitHub.
