# Turkish retrieval fields — R04 engineering baseline

New managed indexes use `public-search-index-v3`, retaining the v2 normalization
recipe and adding [literal citation discovery](CITATION_RETRIEVAL.md).
Original signed text, titles,
identifiers, hashes, locators and dates remain unchanged. Six additional text/title
fields carry deterministic search terms; they are never substituted for evidence.

| Channel | Indexed/query representation | Intended role |
|---|---|---|
| `lexical` | Existing Turkish analyzer on original text/title | Retain the previous stemming baseline |
| `lexical_original` | Case-preserving original tokens | Discover literal spellings independently of stemming |
| `lexical_normalized` | NFC, Turkish I/İ casing and apostrophe variants | Discover canonical spelling/case variants |
| `lexical_folded` | Normalized tokens with combining accents removed and ı mapped to i | Nominate spelling aliases, including ASCII queries |

The derived channels retain negation/exception words, leading zeros, internal
date/number separators and signed numeric tokens. They do not perform morphology,
stop-word removal, OCR correction, NFKC compatibility folding or citation identity
resolution. Token boundaries remove surrounding punctuation; this is not a phrase
or exact-quotation search. For example, `kar` and `kâr` can share an alias while
remaining separate passages and assertions. No legal equivalence follows.

The application computes the same terms for indexing and querying. Derived fields
use OpenSearch's [whitespace analyzer](https://docs.opensearch.org/latest/analyzers/supported-analyzers/whitespace/),
which adds no casing or stemming pass. The normalization recipe records
`turkish-lexical-v1` and Python's Unicode database version; see
[Unicode normalization](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize).
Readers reject unknown profiles, Unicode-version mismatches, modified mappings or
custom analyzer overrides. Changing this recipe requires a new version and rebuild.

## Retrieval and evidence boundaries

All channels apply the same release, rights, review, authority and historical-date
prefilters. Their candidates are unioned with the existing reciprocal-rank fusion;
no normalized or graph match is required for original/stemming candidates to enter
the union. Ranking and bounded result limits can change the final displayed set.
The new channels share a total budget of **200 candidates**, apportioned across
requested channels, under the existing cooperative 12-second retrieval budget.
They do not add retries or extend timeouts. A channel failure leaves other successful
channels visible with partial coverage. Revocation or index-receipt changes discard
all candidates. Real inference and large-corpus concurrency still need qualification.

Exact `authority_id` lookup remains one structured query with the original identifier.
No normalization, alias expansion or vector request is applied to that identifier.
This milestone does not resolve literal statute/decision citations into authorities
or historical provision versions; those remain explicit R04/R05 work.

Each candidate is independently projected from currently authorized signed source
evidence. Only original source fields are returned, never derived index text.
Text searches additionally expose at most 32 `matches.spans` per hit, with `field`,
`start`, `end` and the matching token channels. Spans are recomputed from the verified
text/title and address **Unicode code points**, not UTF-8 bytes or JavaScript UTF-16
indices. They can be sliced directly in Python; clients must convert before using
UTF-16 offsets. Decomposed characters keep their original extent.

These spans are bounded token-match hints, not OpenSearch highlighting, score
explanations, quotations proving a proposition or completeness claims. The engine's
token-length handling can nominate a passage without a matching whole-token hint.
`truncated` reports when more spans exist. No HTML or generated replacement text is
returned. Original graph evidence locators remain authoritative.

## Build, migrate and qualify

Use the existing [index build and selection workflow](OPERATIONS.md#build-or-rebuild-a-public-search-index).
Every build creates a new concrete index and checks the entire original-plus-derived
inventory by count and exact readback before sealing it. Batches are limited to 50
records and 1 MiB of bulk bytes; the existing 32 MiB total and 2,000-record caps now
include derived fields. Larger input fails visibly, rather than dropping content.

Existing sealed `public-search-index-v1` indexes remain readable through their
original lexical channel; v2 indexes retain all four lexical channels. The fixed
legacy index route remains unchanged. Neither
old indexes nor aliases are rewritten, and new indexes are not selected automatically.
Switch only after checking the new receipt, exact evidence and representative
queries for the same currently authorized graph release. Revert selection only to
an intact, authorized prior index. Old clients refuse the new schema, so deploy
the updated reader before selecting a v3 index. Citation discovery requires a new
v3 index; existing v2 normalization behavior remains available without rebuilding.

The opt-in [isolated OpenSearch drill](OPERATIONS.md#isolated-opensearch-qualification)
now includes synthetic Turkish matching cases alongside signed-source/publication
and PostgreSQL concurrency/revocation checks. The Turkish-specific cases use an
explicit fixture projection; the separate lifecycle workload tests real signed
evidence projection. They establish software behavior on the pinned OpenSearch
image, not real legal corpus recall, improved lawyer outcomes or source rights.

Remaining R04 gates include reviewed citation/alias identities, the 360-query
three-practice development benchmark, original/normalized/folded ablations, adverse
recall, local embedding/reranking selection and representative latency/resource
qualification. R01 source review and R08 independent held-out evaluation remain open.
