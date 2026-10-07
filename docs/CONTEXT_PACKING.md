# Inspectable private evidence context

R04 now packs already-authorized private document passages into a bounded,
inspectable quotation context. Research retains exact selected text, original
source references, a selection/omission manifest and a digest of the prepared
model messages. It does not generate legal analysis or establish that a quotation
contains every relevant condition or exception.

## Selection contract

| Current development limit | Bound |
|---|---:|
| Candidate passages examined | 2,000 |
| Original Unicode code points examined across candidates | 2,000,000 |
| Selected passages | 8 |
| UTF-8 bytes per excerpt | 1,800 |
| Total excerpt UTF-8 bytes | 4,000 |
| Serialized prompt | Configured local provider context limit, including reserves |

Documents enter in creation-time/ID order; extracted passage order is preserved.
Within a document, distinct Turkish-cased query-word overlap ranks candidates;
ties retain original order. Each document's best passage gets a turn before its
next passage. Repeated wording with different source identities stays distinct.
An ambiguous repeated passage ID within the examined inventory fails the job.

Scanning stops before a passage that would exceed the character budget or after
the candidate cap. Remaining passages are **unexamined**, not irrelevant.
Omission counts partition all omitted passages; per-passage omission records
cover only the examined inventory. Selection does not imply full-file coverage.

Each excerpt is one contiguous, unchanged span. Full passages are preferred when
they fit. Otherwise punctuation/line boundaries nominate a window around the first
matching word, with neighboring context where space permits. These boundaries are
heuristics: abbreviations, formatting and legal conditions still need inspection.
A long sentence/line falls back to a clearly labeled fragment of complete
whitespace-delimited tokens. Unsplittable tokens are omitted instead of shortening
an identifier or amount.

Offsets use half-open **[start, end)** Unicode code-point ranges within the
original extracted passage, not UTF-8 bytes, JavaScript UTF-16 units or PDF coordinates.
Hashes bind both the complete extracted passage and selected excerpt; document
hash/revision and existing locator remain attached. Original document bytes and
extracted text are not rewritten. These hashes bind software inputs; they do not
verify OCR fidelity, judicial finding roles or legal applicability.

## Model envelope and accounting

**private-evidence-pack-v1** and **private-quotes-v2** are recorded dependencies.
The provider uses the canonical JSON envelope measured by the packer: the complete
question and ordered evidence entries containing only id, text and partial.
Filename/path metadata, revision metadata, arbitrary extra fields and the
manifest do not enter this envelope. Selected text and the question remain private
data, sent only through the existing authorized local-provider transport. This
is not a PII sanitizer or BYOK release.

Measurement includes actual UTF-8 content bytes after JSON escaping, a 256-unit
framing reserve and a 1,200-unit completion reserve. These are conservative
engineering accounting units, not observed tokenizer usage or hardware/model
qualification. Existing authentication, local-model, context-capacity and transport
guards remain. No larger output, timeout, permission or fallback is introduced.

When a candidate exceeds the prompt limit, its window is reduced and the exact
envelope remeasured. Candidates that cannot fit remain explicit. The question is
never silently shortened. If the question itself cannot fit, no provider probe
or generation occurs and the draft reports the gap.

The message digest covers the ordered role/content objects serialized with sorted
JSON keys, compact separators and literal Unicode. Credentials, HTTP configuration
and provider identity headers are excluded; model/policy/transport references
remain in existing snapshots. The digest does not establish receipt or retention
by a provider and cannot confer approval. Provider use separately records a
validated quote response, no configuration, no selected evidence or preparation
only. The shared provider envelope also supports the existing guide-plus-eight-
workspace portfolio inventory; research's stricter caps do not change its access.

## Review, export and confidentiality

The research panel shows compact counts and collapsed selection details, exact
prepared excerpts, source ranges, fragment warnings and omission reasons. Full
original passage inspection remains subject to matter membership. DOCX/PDF exports
retain counts, limitations, source ranges and message/excerpt digests. Old products
remain readable/exportable without a retroactively assigned packing record.

The manifest, omitted-source IDs and message digest are confidential matter metadata.
They stay in the encrypted product under existing authorization, review, stale-work
and retention controls. All original document revisions remain dependencies,
including documents whose passages were omitted. Recipe IDs participate in explicit
release-impact invalidation. Updates never silently rewrite earlier reviewed work.

Public graph/search candidates retain independent release and permission checks and
remain separately inspectable. They do not enter this private quote envelope.
Public parent/exception expansion, supporting/adverse allocations, reviewed decision
roles, evaluated reranking and R05A premise/rule/application/correction remain
future packets. The real development benchmark and lawyer adjudication are still
required.
