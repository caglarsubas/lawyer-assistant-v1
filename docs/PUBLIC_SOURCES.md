# Public legal source staging

Public source intake is an **offline quarantine workflow**, separate from private customers, workspaces, documents and the active graph/search releases. Its first supported subject areas are contracts, commercial and employment law. Importing a package neither publishes it nor permits agents to retrieve it as authority.

A source being publicly accessible does not establish permission to store, process, redistribute or use it in inference. A rights reviewer must assess those uses independently. The importer does not provide a licence, authenticate a reviewer, confirm source identity, establish current law or certify the absence of personal data.

## Boundaries and review states

An operator imports already acquired raw bytes, separately extracted UTF-8 text, a locator map and a source record. Raw documents are opaque: this importer never executes scripts, renders HTML, parses PDF/Office contents, follows URLs, resolves citations, calls inference, or reads the private matter database. Acquisition and extraction must take place through approved source-access and sandboxing procedures before staging. A source URL is provenance, not a request to fetch it.

For the closed TBMM HTML registry, the [offline preparation workflow](REGISTERED_SOURCE_PREPARATION.md)
now produces four import-compatible artifacts after a mandatory disconnected scan
and isolated transcription. It retains original acquisition dates, encoding,
decoded-source-code ranges and pending review states. Its separate provenance and
admission sidecars belong in the review archive; preparation does not import or publish.

Each package remains:

- `rights_status: rights_pending`
- `review_status: legal_review_pending`
- `publication_status: staged`

Independent rights and source-identity review records may be attached at import. They are retained as **operator-supplied, unverified evidence**, and do not change these states. Their referenced evidence must remain available in the review archive; the importer verifies record structure and binding to the exact source version, not the referenced permission document's authenticity. The authenticated review workspace records separate accountable assessments in the firm's encrypted database. Neither workflow publishes a graph/search release or changes the immutable source package.

Private matter input, credentials, encrypted matter artifacts and synthetic legal records must not be promoted into the public corpus. Metadata requires explicit public-origin declarations and rejects private/synthetic values, matter/customer/workspace identifiers and unknown fields. These declarations cannot prove that falsely labelled raw bytes are public or free of personal data; source-identity and sensitivity review remain mandatory. Automated injection hints are triage signals only. No hint, including an empty hint list, establishes safety.

## Storage and immutability

Use a dedicated directory, configured in the API with `LA_PUBLIC_SOURCE_DIR`; the Docker API uses `/public-sources` on a dedicated named volume mounted read-only. The image creates that directory for runtime UID/GID `10001:10001`. Never point this setting or the CLI at the private matter data directory. The import command rejects existing directories with unrelated contents. Keep strict ownership and package permissions; do not make the host staging tree world-readable to work around container permissions.

Every package is a directory named by the SHA-256 of its canonical manifest. It contains only fixed logical filenames:

| File | Purpose | Limit |
|---|---|---:|
| `raw.bin` | Exact acquired source representation; never parsed here | 20 MiB |
| `text.txt` | Exact extracted UTF-8, with original normalization and line endings | 2 MiB |
| `locators.json` | Source/text digests and exact Unicode passage spans | 2 MiB |
| `source.json` | Provenance and explicit public-origin declarations | 64 KiB |
| `rights-review.json` | Optional independent rights review record | 64 KiB |
| `identity-review.json` | Optional independent source-identity review record | 64 KiB |
| `manifest.json` | Canonical package metadata and artifact digests | 64 KiB |

Imports are bounded to 5,000 passages, 20,000 Unicode code points per passage and 10,000 staged directory entries. Passage spans are ordered, nonoverlapping and hashed. Partial document coverage is allowed and must not be interpreted as complete extraction. Original and extracted-text hashes bind the locator map to their exact bytes. UTF-8 BOM, invalid UTF-8, disallowed text controls, duplicate JSON keys, symlinks and unexpected package files are rejected. File permissions are owner-read-only after atomic publication; digest verification detects later alteration. A changed source, map, metadata or review record produces a new package ID; no existing package is edited or overwritten.

Private document and review storage, legal holds, backups and deletion policies still require separate operational configuration. Read-only files are not protection against a host administrator; package hashes and release governance provide tamper detection and audit boundaries.

## Source record

Create `source.json` using the exact fields below. This is an illustrative provenance template, not a supplied source or a statement that the referenced document is licensed, current, authentic or legally reviewed.

```json
{
  "schema_version": "public-source-v1",
  "title": "Operator-supplied public legal source title",
  "source_url": "https://www.mevzuat.gov.tr/mevzuatmetin/1.5.6098.pdf",
  "source_version_id": "operator-assigned-acquisition-version",
  "domain": "contracts",
  "acquired_at": null,
  "published_on": null,
  "effective_from": null,
  "effective_until": null,
  "data_classification": "public",
  "origin": "public_legal_source",
  "contains_private_matter_data": false,
  "synthetic": false,
  "raw_media_type": "application/pdf"
}
```

Record verified dates when available; use explicit `null` for unknown publication, acquisition or effective dates. Known acquisition timestamps must include a timezone and cannot be in the future. Publication and effective dates use `YYYY-MM-DD`. They are separate facts: acquisition must never be substituted for publication or legal effect. An effective interval cannot be reversed. Unknown finality or legal applicability is not filled in by this intake workflow.

`domain` is `contracts`, `commercial` or `employment`. Permitted raw media declarations are PDF, plain text, HTML, XHTML and DOCX. The declaration does not validate the actual media. Source URLs must be credential-free public HTTPS URLs without query strings, fragments, IP addresses or private/local domain suffixes. A signed/private link must not be copied into provenance; use a stable public source URL and preserve authorized acquisition details in the appropriate restricted archive.

## Exact passage map

`locators.json` uses half-open Unicode code point offsets, not UTF-8 bytes, UTF-16 offsets or normalized text offsets. Hash each selected string after UTF-8 encoding. A locator must identify a position that a reviewer can inspect in the original representation; the importer verifies exact text spans, but a reviewer still checks whether extraction and source locators actually agree.

```json
{
  "schema_version": "public-locators-v1",
  "offset_unit": "unicode_code_points",
  "raw_sha256": "<64 lowercase hexadecimal characters>",
  "text_sha256": "<64 lowercase hexadecimal characters>",
  "passages": [
    {
      "id": "article_1_paragraph_1",
      "start": 0,
      "end": 25,
      "text_sha256": "<SHA-256 of exact text[0:25] encoded as UTF-8>",
      "locator": "Page 1, article 1, paragraph 1"
    }
  ]
}
```

The angle-bracket digest descriptions above are explanatory placeholders and are deliberately not importable. Generate actual digests from the actual acquired files. No synthetic example source is bundled into the active corpus.

## Independent review records

Optional `--rights-review` and `--identity-review` paths must be separate files from the source record and each other. Both use this schema:

```json
{
  "schema_version": "public-review-evidence-v1",
  "kind": "rights",
  "source_url": "https://www.mevzuat.gov.tr/mevzuatmetin/1.5.6098.pdf",
  "source_version_id": "operator-assigned-acquisition-version",
  "raw_sha256": "<exact source representation SHA-256>",
  "reviewer_id": "<responsible reviewer's identity reference>",
  "reviewed_at": "2026-01-01T12:00:00+03:00",
  "assessment": "pending",
  "evidence_reference": "<stable reference in the authorized review archive>",
  "evidence_sha256": "<exact supporting evidence artifact SHA-256>",
  "rationale": "<specific uses assessed, conditions, uncertainties and review rationale>"
}
```

Rights assessments are `pending`, `permitted`, `restricted` or `denied`. Identity assessments use `kind: source_identity` and `pending`, `verified` or `disputed`. Source URL, source-version ID and raw digest must exactly match the imported source. Denied/restricted/disputed evidence may be retained for review but cannot enable publication. Reviewer IDs are supplied references, not authenticated signatures. The importer does not sign or endorse them.

## Offline commands

The CLI never loads `.env`, reads API credentials or connects to any network. Run with the backend virtual environment:

```sh
backend/.venv/bin/python scripts/public_sources.py --store .public-sources import \
  --metadata /approved-transfer/source.json \
  --raw /approved-transfer/original.pdf \
  --text /approved-transfer/text.txt \
  --locators /approved-transfer/locators.json

backend/.venv/bin/python scripts/public_sources.py --store .public-sources list --limit 50

backend/.venv/bin/python scripts/public_sources.py --store .public-sources verify PACKAGE_SHA256
```

For the deployed Docker catalog, use the built API image in an explicit one-off container with `--network none --user 10001:10001`, the dedicated public-source named volume mounted read-write at `/public-sources`, and **only the approved public input directory** mounted read-only. Run the same import CLI against `--store /public-sources`. Do not inject the application `.env`, provider credentials, private documents, database volume or Docker socket into this container. The long-running API retains its read-only mount. A host CLI import into a separate directory does not update the Docker catalog.

Only the import operation writes. Verification recomputes all artifact hashes and passage constraints. Re-importing an identical intact package returns its existing ID. Tampered existing packages fail closed. Never replace an existing package in place; investigate integrity failures and preserve relevant audit evidence.

## Curator catalog API

Authenticated active `admin` and `curator` roles can read the global **public-only** staging catalog. Lawyers receive 403; unauthenticated users receive 401. Role/session authorization is checked again after the filesystem read so a revoked session does not receive the result.

- `GET /api/v1/public-sources?limit=50&after=SHA256`: bounded lexicographic pagination, source summaries, `next_cursor` and limitations. `integrity_scope: manifest_only` means artifact bytes are not rehashed while listing.
- `GET /api/v1/public-sources/{SHA256}`: complete artifact and span verification, source dates, artifact digests/sizes, independent-review presence and injection-risk hint names. `integrity_scope: all_artifacts_verified` means integrity only, not legal or rights approval.

Catalog and metadata responses include no raw source text, raw bytes, local paths, review rationales, reviewer identities or private matter links. Source titles, URLs and metadata remain untrusted display text. A catalog count measures staged packages, not nationwide corpus completeness or qualified legal coverage.

## Accountable source review

Open **Kaynak kapsamı → Kaynağı incele** as an active admin or curator. Inspect the exact extracted passages and download the original as an inert `.bin` attachment. The browser displays source text as plain text; raw HTML is never rendered. Both routes reverify every package artifact, Unicode span and digest before returning data. Passage pages contain at most 20 items; offsets are Unicode code points, preserving the acquired text's normalization and line endings.

Claim the review and record each dimension separately: rights and permitted uses, source identity, extraction fidelity, and legal context. Every decision records the authenticated reviewer, server time, rationale and revision. Acceptance requires an evidence reference with its SHA-256; extraction acceptance also requires a selected passage, and rights acceptance requires at least one permitted use. These references are review attestations, not automatically acquired or authenticated permission documents. Use a qualified reviewer and retain the referenced artifacts.

Review ownership, decisions and evidence selections are firm-confidential. They remain in encrypted PostgreSQL payloads, outside the shared public package; another firm's curator sees their own independent review. Competing updates return409 and must be reconsidered against the latest revision. Release an assignment before another curator claims it; administrators may release it with a recorded reason. Previously recorded decisions remain in the history when superseded.

All four latest assessments accepted means **ready for independent handoff**, not publication approval or blanket permission for indexing, inference or export. Export downloads an unsigned, firm-confidential JSON dossier with the current assessment projection and the latest 50 events; truncation is explicit. No source text or review notes are implicitly passed to the assistant. It provides a static guide on this page; explicitly requested portfolio summaries retain their existing authorization/filtering rules.

See [source-review API contract](SOURCE_REVIEW_CONTRACT.md) for routes, limits and payloads. Public graph promotion, signed review authority, sensitivity qualification and corpus indexing remain separate gates.

## Exact provision mapping

From an opened source review, choose **Madde eşleştirmelerini aç**. The heading adapter
proposes explicit article, temporary-article and additional-article headings. It
does not infer a statute identity, current provision version, effective date or
amendment relationship. Repeated headings, quotations, locator gaps and truncated
spans remain visible. A candidate's end may include the next editorial section
title; inspect and adjust its Unicode boundaries against the original source.

The source-review owner may save a candidate or a manually specified span as an
unreviewed mapping proposal. Preview the exact text before accepting corrections.
Each acceptance needs separate instrument, provision and historical-version
references; an explicit text role; supporting evidence; and applicable dates or
explicit unknowns. These are reviewer references, not automatically resolved
canonical graph identities. An amendment or transitional role does not itself
create a genealogy relationship or prove legal effect.

Mapping acceptance requires all four source assessments accepted and rights scope
covering local processing and internal display. Exact accepted text must be covered
by verified source locators except for whitespace gaps. Any later source-review
revision makes earlier accepted mappings stale; review and reaffirm them explicitly.
Conflicts preserve the draft and require an intentional retry. Old decisions stay
in history; no public package is edited.

The mapping dossier is encrypted in the firm's database and exported only as an
unsigned, confidential attachment. All current mappings plus the latest 50 events
are included, with explicit history truncation. A ready dossier is not a graph
release, search index, legal applicability guarantee or proof of complete source
coverage. See [provision-mapping contract](PROVISION_MAPPING_CONTRACT.md).
