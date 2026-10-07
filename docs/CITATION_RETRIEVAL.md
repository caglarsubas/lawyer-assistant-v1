# Literal citation discovery — R04 engineering baseline

Managed `public-search-index-v3` indexes add a separate `literal_citation` channel
to the four [Turkish lexical channels](TURKISH_RETRIEVAL.md). It finds passages
containing explicitly labeled numbers without relying on stemming or numeric token
similarity. It does **not resolve the cited authority**. A containing passage's
existing signed `authority_id` is not automatically the target of its citations.

## Supported forms and limits

The deterministic profile is `tr-literal-citations-v1`. These examples are invented:

| Source/query spelling | Discovery key |
|---|---|
| `E. 2099/0012`, `Esas Sayısı: 2099/0012` | `esas:2099:0012` |
| `K. 2099/0012`, `Karar Numarası: 2099/0012` | `karar:2099:0012` |
| `B. No: 2099/0012`, `Başvuru Numarası: 2099/0012` | `application:2099:0012` |
| `Kanun No: 001234`, `001234 sayılı Kanun` | `law:001234` |

Labels are case-insensitive. The number labels `No` (optional period), `Numarası`
and `Sayısı` are recognized; `Esas` and `Karar` may also precede a number directly.
Spaces, tabs and nonbreaking spaces are accepted around the colon and slash.
Numbers remain ASCII: four year digits and 1–9 serial digits, or 1–6 law-number
digits. Leading zeros are preserved; `2099/0012` and `2099/12` stay distinct.
Esas, karar, application and law labels never share a namespace. Searching multiple
keys nominates passages containing **any** key; co-occurrence does not create a
case-number pair, institutional identity or graph relationship.

The narrow header grammar is informed by official AYM representations such as the
[norm-review decision header](https://normkararlarbilgibankasi.anayasa.gov.tr/ND/2017/12)
and [individual-application header](https://kararlarbilgibankasi.anayasa.gov.tr/BB/2019/27182).
These references establish examples of labels, not corpus rights, full-format
coverage or authority/effect rules. Tests use invented text and numbers.

Unsupported forms remain eligible for ordinary lexical search. These include bare
`2099/12`, suffix forms such as `2099/12 E.`, statute abbreviations, named-law
expansion, article references, OCR repairs and line-wrapped citations. The parser
does not classify `sayılı Kanun Hükmünde Kararname` as a law-number citation. It
does not stitch lines, strip zeros, infer a court from a number, choose between
colliding references or bind a current provision to historical text.

Each text/title field has a 12,000-codepoint parser bound and at most 64 recognized
occurrences. An overflowing source blocks index preparation before writes; it is
never silently indexed with missing keys. A query can use at most 16 distinct keys
and 64 recognized occurrences. When it exceeds either limit, the citation channel
is skipped with an explicit limitation and partial coverage, while other channels
continue. No subset of the query's keys is silently selected. Ordinary search
retains its existing 4,000-character query bound.

## Evidence and retrieval contract

The builder derives an exact keyword array `citation_keys` from authorized original
text/title and includes it in full inventory hashes and readback validation.
The query uses a terms filter alongside the same release, rights, review and
historical-date filters as the lexical channels. All requested channels share the
existing 200-candidate and cooperative 12-second budgets. Ranking/result limits
still apply. Exact `authority_id` lookup keeps its separate single-query path.

Every citation-channel candidate is independently projected from signed source
evidence and reparsed. If its claimed key is absent from that source, it is rejected
from the citation channel. Valid nominations from other channels remain eligible.
Revocation or a changed/unreadable index receipt discards all candidates.

For queries with recognized keys, hits expose `literal_citations` with:

- `resolution: unresolved` and `offset_unit: unicode_codepoint`;
- up to 32 original occurrences with `field`, `start`, `end`, `literal`, `kind`
  and the typed discovery `key`;
- an explicit `truncated` flag when the annotation bound is reached.

An independently nominated lexical hit may have no matching occurrences. Offsets
address the exact returned source text/title, not folded text, UTF-8 bytes or
JavaScript UTF-16 units. Clients must convert offsets if needed. The snapshot
records the citation profile and coverage reports recognized query-key count,
query-budget overflow and `authority_resolution: not_performed`.

These annotations do not establish adoption, treatment, binding force, applicable
law or historical version. No citation assertion is published to either graph.

## Migration and qualification

Deploy the v3-capable reader, then use the existing
[build/select workflow](OPERATIONS.md#build-or-rebuild-a-public-search-index) to
create, verify and deliberately select a new index. Old binaries reject v3.
The new reader accepts intact v1 lexical and v2 normalized indexes; neither gains
citation search without rebuilding. No index is automatically rewritten, selected
or deleted. Rollback requires an intact index for the same authorized release.

The opt-in v4 OpenSearch drill covers seven targeted literal-citation cases against
eight invented passages: role separation, leading zeros, collisions, unchanged
spans, date filters, unsupported bare numbers and a deliberately forged keyword
rejected against original text. These matching cases use an explicit fixture
projection. The separate signed-source lifecycle and PostgreSQL workloads exercise
actual signed evidence, rebuild/read concurrency and committed source revocation.
Fast tests cover parser/query bounds, v1/v2 compatibility and partial-channel failure.
The [verification record](VALIDATION.md) distinguishes these evidence scopes.

R04 remains partial. Reviewed alias/citation identities, institution epochs,
ambiguity review, provision versions, the 360-query development benchmark,
retrieval ablations, adverse recall, local models and representative performance
remain open. This engineering baseline does not establish real-corpus recall or
legal correctness.
