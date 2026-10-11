# Evidence-bound jurisprudence occurrence candidates

This R03 packet supplies read-only API and offline operator inspection of one
retained public-source passage. It does not adjudicate a decision or add graph
nodes, edges, reviewed dates or authorities. The source remains in quarantine.
Curator UI and accountable decision mapping are subsequent packets; this API is
not an agent authority-resolution tool.

## Inspect an existing passage

The existing privileged CLI accepts only a dedicated local public catalog, an
existing package ID and one existing passage ID:

```sh
backend/.venv/bin/python scripts/public_sources.py --store /approved-public/catalog \
  jurisprudence-candidates PACKAGE_SHA256 --passage pdf_page_0001
```

It never reads `.env`, scans/parses originals, uses inference or contacts a network.
Operators must complete mandatory scan/preparation before admitting a registered
acquisition. Caller-supplied text, URLs, models and graph queries are unavailable.
Retain output in the approved local review context: public decisions may contain
personal data, and public origin grants no redistribution permission.

Authenticated administrators/curators with current `source.curate` permission use:

```text
GET /api/v1/public-sources/{package_sha256}/jurisprudence-candidates?passage_id=pdf_page_0001
```

Missing, repeated or extra query parameters are rejected. There are no mutation
or review endpoints. Responses contain canonical `evidence_json` and its exact
UTF-8 `evidence_sha256`, with `no-store`, `nosniff` and inert content policy. The
existing request permission/firm-lock boundary applies; session, role and firm
identity are checked again before return. Results are not persisted or globally
cached. Exact original integrity is checked before and after extraction; changed
packages withhold output. This does not attest source authenticity or legal review.

## Recognized syntax and unresolved meaning

`tr-jurisprudence-occurrences-v1` recognizes these limited literal forms:

| Candidate kind | Examples | Unresolved meaning |
|---|---|---|
| Application number | `Başvuru Numarası: 2018/31036`, `B. No: 2018/31036` | Own versus quoted proceeding; canonical identity |
| Case number | `Esas No: 2020/12` | Institution, chamber and proceeding identity |
| Decision number | `Karar No: 2021/3` | Issuing body, decision identity and document role |
| Decision/publication date | `Karar Tarihi: 12/1/2021`, `Resmî Gazete Tarihi: 5.2.2021`, `Yayın Tarihi: 5/2/2021` | Which event/authority is dated; finality and legal effect |
| Instrument number reference | `4857 sayılı` | Instrument type, identity, version and relationship |
| Article number reference | `MADDE 18`, `m. 18`, `md. 18`, `20. maddesi` | Instrument/version, citation role and authority treatment |

Bare numbers/dates and names are not resolved. Quoted, repeated and conflicting
occurrences remain separate, including identical values at different spans. Dates
are marked `calendar_valid_only` or `invalid_calendar_date`; calendar validity is
not a reviewed document/event date. Unsupported spelling is not silently repaired.

Every item retains exact spelling, full and value-only half-open Unicode spans,
passage-relative spans, digest, rule/version and a stable ID bound to package,
version, raw/text/passage identity. Separate compact numeric/ISO calendar hints
never rewrite evidence. Status stays `machine_proposed`, identity `unresolved`,
event role `unknown`, authority treatment `unknown`. Labels cannot distinguish
an allegation, majority, dissent, finding, cited decision or editorial summary.
Source dates and review ledgers never change.

This staging profile is separate from the existing `tr-literal-citations-v1`
retrieval-key grammar and its 12,000-character/64-occurrence budget. It adds
curator date/article hints and evidence binding; it does not change retrieval keys,
broaden the serving search profile or assert compatible/exhaustive recognition.

## Coverage and resource limits

Search is limited to one selected passage: 20,000 Unicode code points, 200
occurrences and 256 KiB canonical evidence. Fixed patterns have bounded numeric
and whitespace widths. Exceeded budgets, unknown passages and failed integrity
withhold the entire result; no partial/truncated receipt is emitted. The exact
passage locator and whole raw/text hashes remain available. Matches do not cross
passage boundaries. An empty result is neither absence of citations nor a complete
judgment scan, recall metric or corpus-coverage result.

Original-page fidelity, rights/privacy, canonical identities, historical provision
versions, decision/proceeding links and legal effect need separate accountable and
independent review/publication. Citation is never promoted to endorsement, binding
force or applicability. National ontology and jurisprudence qualification remain open.
