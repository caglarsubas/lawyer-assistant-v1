# Offline source-diversity experiment

Policy declared before grading the fresh synthetic suite. This is a new offline
recipe; production packing, the original bundle planner and disposable adapter
retain their existing contracts.

1. Validate the complete frozen inventory, unique evidence IDs, positive integer
   revisions and source/text hashes. A document ID and revision cannot name two
   document hashes. Source versions are distinct `(document_id, revision, hash)`
   groups. Retain original order and complete inventory identity.
2. Scan at most the existing 2,000 passages / 2,000,000 code points and an explicit
   20,000 nonblank physical-line work cap. Larger inputs fail closed before
   nomination, without claiming a partial scan is exhaustive.
3. Nominate complete physical lines with query overlap using the existing Turkish
   folding and inverse line frequency. No synonym dictionary, semantic model,
   expected-answer lookup or legal-effect inference is introduced.
4. For a passage with no matching words, nominate its first nonblank line as an
   explicitly labeled `unmatched_source_fallback`. This is bounded consideration
   of an otherwise ignored source, not a relevance or abstention result. It may
   expose irrelevant text and may miss later paraphrased evidence.
5. Keep an anchor and its immediate nonblank neighbors separately, at most one
   blank line away. Wider separators and passage edges remain unlinked. Preserve
   negations and conditions; do not trim companions to admit a bundle. A complete
   passage of at most 1,800 UTF-8 bytes can replace an overlong part. Otherwise omit
   the complete bundle with a reason.
6. Rank within each source version, then visit one candidate per source version
   before a second visit. Source order uses best score and stable input order.
   Admission remains atomic and bounded: 20 bundles, 64 parts, eight evidence
   passages, 4,000 copied UTF-8 bytes, 768 bytes per ordinary part, and the exact
   serialized prompt plus the existing framing/completion reserves. This does not
   guarantee that all sources or adverse evidence fit. Keep every omission.
7. Seal recipe, limits, question, complete sources, span/version metadata and
   prompt. Resolve only against a complete rebuild; old plans and adapters cannot
   silently adopt the new recipe.

Freeze the fixture inventory, expected source groups, both planner implementations
and evaluator before the first grade. Use the same new cases and budgets for the
retained v1 planner and this candidate. Report group availability, both-side source
coverage, unmatched fallback counts, original/version integrity, prompt budget and
all omissions. Preserve every failure and do not tune this exposed suite into an
acceptance set. Expected groups are evaluator-only data.

No native inference, HTTP, private documents, production changes, reviewed answers
or legal qualification are part of this experiment. A new adapter and a separately
declared native acceptance trial remain later gates. Keep the owner's version-3
review pending and retain earlier model/HTTP failure evidence.
