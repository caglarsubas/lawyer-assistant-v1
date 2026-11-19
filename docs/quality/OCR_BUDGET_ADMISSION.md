# F00-04: bounded OCR admission and incomplete captures

This engineering slice keeps the seven private OCR fields pending. Synthetic
controls qualify budget handling and retention; they do not resolve those fields,
approve legal analysis, or establish broad severe-scan accuracy.

## Admission contract

The saved-analysis punctuation sidecar retains the existing six-second page OCR
budget. A glyph call needs at least 0.35 seconds of native execution allowance
plus 0.12 seconds of processing reserve. A row call needs 0.25 seconds plus a
0.05-second reserve. Admission is checked again after image preparation, directly
before native OCR. Native timeout ceilings stay at 0.65 and 1.20 seconds,
respectively. This is a conservative admission change: the previous glyph gate
treated 0.35 seconds as the entire remaining window rather than native allowance.
No OCR passes or retries are added.

Typed budget exhaustion distinguishes refused admission and late completion from
a timely blank result or native-reader error. Results completed before a later
reader fails remain literal, source-located, review-only observations. A failed
or unstarted reader contributes no invented glyphs. The original PDF, raster,
saved extraction, evidence pins and lawyer decisions are not replaced.

## Capture assessment and history

New `native-pdf-punctuation-v2` results bind the following assessment into the
producer fingerprint, capture digest, encrypted receipt and observation metadata:

| Field | Values |
| --- | --- |
| `status` | `complete`, `incomplete` |
| `reason` when complete | `checked`, `no_currency_scope` |
| `reason` when incomplete | `page_budget`, `reader_error`, `reader_unavailable`, `source_scope_unverified` |
| `stage` | `nomination_raw`, `nomination_contrast`, `currency_fields` |

A complete assessment requires `currency_fields`. `no_currency_scope` requires
zero events. A diagnostic event cannot be labeled complete. Regional-reader
errors, unbound reads and unresolved source geometry also prevent completion.
An overall budget result takes priority while preserving any earlier field event.
`checked` describes completion of this bounded check, not verification of the
amount, legal significance or the absence of all OCR errors.

Incomplete runs use `captured_incomplete`, including when no field was nominated.
The review UI explains the stage and reason beside the run and any selected
observation. A zero-event incomplete run is never presented as a successfully
checked absence of alternatives. Even a complete `no_currency_scope` result only
means the bounded readers did not nominate a supported currency field; it does
not establish that the page contains none.

Historical v1 receipts remain readable without an assessment. Their IDs, hashes,
encrypted payloads and chronology stay unchanged. The UI marks completion as
unrecorded. Current v2 producers must supply a valid assessment; missing, malformed,
contradictory or digest-mismatched assessments fail closed. No migration, history
rewrite, canonical promotion or new source-selection authority is introduced.

## Qualification and release boundaries

Deterministic tests cover preprocessing costs, minimum admission, timely blank
and error results, late native/parsing completion, partial raw/contrast reads,
outer-run budget results, encrypted history and legacy reopening. Native paired
controls compare original raster bytes and literal events against the installed
PR #322 dependency image using synthetic source PDFs only. Frozen blank and
trailing-period pages are scope controls, not proof of punctuation recognition.

Frontend qualification covers incomplete zero-event runs, partial-reader display,
legacy unknown completion and metadata binding. CI retains two workers, full
coverage, existing job caps and the 30-second reserve floor. Exact-head PR CI,
merge, independent main CI and local deployment remain separate evidence states.
The live roadmap advances only after the new main commit is independently
qualified. F00-04 readiness and the pending owner review remain unchanged.
