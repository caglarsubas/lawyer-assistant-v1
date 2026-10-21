# Local document intake contract

Uploads are bounded to 20 MiB and are matter-authorized before processing. In production, both a responding malware scanner and the isolated extraction service are mandatory. The API stores the original encrypted, assigns passage identifiers itself, and treats parser output as untrusted. An unsuccessful extraction remains a visible failed document with its original available to an authorized lawyer; it contributes no passages to research. A blocked malware check does not store the upload.

The source viewer opens **Özgün belge** by default. PDF pages render directly from
the stored original bytes with page navigation and zoom; supported browser images
display the original image. DOCX previews render the original document's paragraphs,
tables, images, headers and footers locally, with an explicit notice that browser
pagination and fonts may differ from Word. UTF-8 text, Markdown, CSV, HTML and EML
show the original source as escaped text. Other formats, including TIFF and the
remaining Office/OpenDocument types, offer the original download and an explicit
preview-unavailable state. They never substitute extracted passages for an original
preview. Synthetic records without an original have a separate empty state.

**Çıkarılan metin** retains passage identifiers, extraction warnings and highlighted
citations. Citation inspection opens this view and the selected passage; switching
to the original PDF opens its cited page when the locator identifies a page.
Preview reads use the existing authenticated, matter-authorized original endpoint
and its integrity check. PDF workers, character maps and font assets are bundled
locally; no document is sent to an external viewer. DOCX HTML chunks and navigable
document hyperlinks are disabled. The preview does not validate signatures or
establish complete extraction.

Compose includes an isolated ClamAV scanner with no Internet route or automatic updates. Its read-only database release must contain officially signed CVD files admitted through the [offline signature provisioning process](../deploy/scanner/README.md). The signed daily database date may be at most seven days old by default; `LA_SCANNER_MAX_SIGNATURE_AGE_DAYS` permits 1–14 days. File modification dates cannot extend validity. Health, freshness and a complete clean scan response are required for **every upload**, before the document is sent to extraction. Malware, encrypted content and exceeded scan limits are rejected; unavailable or malformed responses fail closed.

Authenticated `GET /api/v1/intake/readiness` checks scanner health/signature age and the extractor's token-protected `/ready` contract without sending documents or calling the LLM. The upload screen disables file selection and dropping while this check is unavailable, blocked or refreshing, and offers **Yeniden denetle**. This preliminary check does not replace per-upload checks. A scanner outage or expired signatures block new intake, while sign-in and authorized reading of existing documents remain available. Synthetic demo bypasses are explicitly labeled and are not production screening.

The extractor has a dedicated internal network shared only with the API, no database or matter-vault mount, no provider credentials, a separate service token, a read-only filesystem and bounded scratch space/process resources. Each parse runs in a fresh subprocess with a clean environment and a deadline. Deployment isolation still requires target-host verification; the local synthetic demo is not a production sandbox.

| Formats | Implemented extraction | Explicit limitations |
|---|---|---|
| PDF | Page text; bounded local Turkish/English OCR fallback | Up to 500 pages, OCR attempts at most three textless pages; unread pages remain listed; no layout or signature validation |
| DOCX | Body paragraphs and bounded nested table content interleaved in XML order; unique physical cells | Four table levels and 50,000 visited structural blocks; tracked changes flagged; merged-cell meaning, headers, footnotes, text boxes, embedded objects and visual reading order unverified |
| XLSX | Sheet/row/cell locators, literal formulas | Formulas and links never executed; charts, objects, formatting and calculated-value correctness unverified |
| PNG, JPEG, TIFF, BMP, WebP, GIF | Local Turkish/English OCR | 30 million pixel bound; first frame only, remaining frames explicitly omitted; OCR requires visual review |
| TXT, Markdown, CSV | Strict UTF-8 text; paragraph or CSV-row locators | Encoding mismatch fails visibly; Markdown is data, never executed |
| PPTX | Slide text frames and table rows | Notes, grouped shapes, images, charts and objects omitted; up to 500 slides |
| ODT, ODS, ODP | Bounded `content.xml` paragraph text | External XML entities prohibited; repeated cells not expanded; formulas not run; cell coordinates/layout unverified |
| HTML | Text parsing without browser/network access | Scripts/styles/embedded executable content omitted; CSS visibility and reading order unverified |
| EML | Headers and preferred plain-text/HTML body | Attachments counted but not recursively ingested; originals of attachments must be uploaded separately; headers are unverified assertions |
| RTF | Plain text, including Unicode escapes | Embedded objects, fields and layout not validated |
| XLS | Stored legacy cell values through xlrd | Formula definitions/calculation, macros, charts and objects not processed; encrypted workbooks unsupported |
| MSG | Unicode subject/sender/recipient/header/plain-body MAPI streams | HTML/RTF/ANSI-only bodies and attachments explicitly unprocessed; header authenticity unverified |
| DOC | Bounded local antiword conversion | Requires antiword; layout, revisions, macros and objects unverified; no macro execution |
| Supplied UDF | Not admitted yet | Representative supplied files, format/version identification, parser and signature fixtures are required before pilot qualification |

Office/OpenDocument archives have member-count and expanded-size bounds; duplicate members and known macro containers are rejected. Parser responses have independent byte, text, passage, warning and time bounds. An extension never establishes authenticity or complete extraction. Representative Turkish legal-document testing, including large scans and complex tables, remains required before claiming format qualification.

New DOCX extraction uses the declared `docx-body-tree-v2` profile. A table stays
between its surrounding body paragraphs. Rows containing nested tables retain
each cell's paragraph/table sequence, including paragraphs following an inner
table and multiple sibling tables. Locators identify the enclosing table, row,
physical XML cell and nested block; blank paragraphs still consume their own
number. Rows without inner tables retain a single row passage, joining each
physical cell's paragraphs in order. Horizontal spans are not expanded and
vertical continuation cells do not repeat the merged origin's content.

Extraction admits at most four table levels, counting the outer table, and
50,000 visited body blocks, rows, cells and cell paragraphs/tables, including
empty ones. Exceeding either limit fails the extraction; no partial successful
passages are returned. Existing file/text/response/process limits also apply.
Cell numbers identify physical XML cells, not visual column positions. XML order
does not establish Word pagination, right-to-left visual order, floating-object
placement, merged-cell meaning, tracked-change acceptance or complete extraction.
The result retains an explicit table-layout warning.

The authenticated worker response carries the profile; the API stores it on the
new document record. The worker, client and demo intake reject an absent or
unknown DOCX profile, and reject a DOCX profile on another format. Deploy API and
extractor together: a new API with an old worker fails new DOCX extraction visibly
instead of silently labeling old output as v2. The existing `parser_version` identifies
the adapter family; the narrower profile identifies this DOCX behavior. Older
records without a profile or with `docx-body-order-v1` remain historical. The
offline calibration model retains the exact declared v1 or v2 profile, without
upgrading it. Existing records are not backfilled, reordered or re-extracted. Originals, passage IDs, exact
quotations, draft versions and reviews remain unchanged. A deliberate future
re-extraction requires a separately recorded evidence version and review.

Synthetic checks cover interleaved Turkish clauses/tables, dates, amounts,
negation, blank paragraphs, nested/sibling tables, merged cells, structural/depth
limits with closed worker failures, isolated subprocess parsing,
strict transport/calibration metadata, original-byte round trips and preservation
of prior document records. They establish a regression fix, not representative
format qualification. See [current engineering evidence](evidence/docx-nested-tables-2026-10-21.json)
and the [historical v1 regression record](evidence/docx-body-order-2026-10-21.json).

Research currently selects bounded exact excerpt windows, retaining source hash, locator and offsets. A document being uploaded does not imply that every passage was examined in a particular research run. Exports retain that distinction.

Local deployed checks accepted synthetic clean text with HTTP 201, preserved its exact two passages and round-tripped the original bytes; an EICAR test upload was rejected with HTTP 422. Browser checks confirmed live readiness and disabled uploads during a scanner outage while existing passages remained readable. These bounded checks do not qualify arbitrary-file safety or extraction completeness; see [validation evidence](VALIDATION.md).

Primary parser contracts: [python-pptx](https://python-pptx.readthedocs.io/en/latest/user/quickstart.html), [xlrd supported content](https://xlrd.readthedocs.io/en/latest/), [Python email parsing](https://docs.python.org/3/library/email.parser.html), [striprtf](https://pypi.org/project/striprtf/). These library capabilities do not constitute legal-document completeness or security certification.
