# Saved-analysis punctuation observations

Status: source-bound integration with synthetic qualification. Qualification does not approve
private OCR fields, legal conclusions, release readiness, or a runtime deployment.

A lawyer may request a punctuation check while inspecting an exact saved-analysis
source. The current check compares raw and locally leveled OCR readings of bounded
currency fields. It does not certify every punctuation mark on the page.

The server resolves the selected analysis version, evidence quote, original PDF
revision and page. It reads and verifies the encrypted original, then sends only
the PDF bytes and page number to the authenticated isolated extractor. The client
cannot submit OCR readings, raster bytes, source paths or producer identities.

The extractor shares the existing two-slot limit. A child process renders one
original page at a maximum dimension of 2,000 pixels and performs a six-second OCR
stage. The subprocess has a twenty-second wall budget, fifteen-second CPU limit
and bounded output. Private requests have no cloud fallback. Missing configuration,
invalid output or a producer recipe mismatch leaves the action incomplete.

Each successful capture appends an encrypted immutable run receipt containing the
exact original-page PNG and literal producer events. Events retain source geometry,
raw and contrast readings, missing-reader diagnostics and code recipe identity.
Zero-event captures retain a receipt without inventing an alternative. Identical
retries reuse deterministic receipt and observation identities. They do not create
a new legal review decision or replace previous observations.

An observation binds these identities:

- Firm and authorized matter.
- Saved analysis and version, including its content digest.
- Selected evidence and quote digest.
- Original document identity, revision, digest, page and page count.
- Raster, literal event, producer recipe and complete run digests.

Observations describe source-page context. A selected quote anchors navigation but
does not establish that a glyph lies within its character range. All readings stay
review-only with `canonical_usable: false`. No observation changes original bytes,
extracted passage text, saved analysis content, evidence versions or review history.

Read and capture operations verify fresh matter permissions and exact source pins.
The capture coordinator also rechecks the authenticated session after source I/O,
after worker execution and during retention before commit. Observation lists,
details and PNGs are authorized, bounded and returned with `Cache-Control: no-store`.
Context selection metadata stays inside the private matter boundary.

The saved-analysis panel validates metadata and event hashes, echoed source pins,
PNG digest and raster dimensions before displaying both readings and the exact
source crop. Navigation cancels requests and clears previous-source content.
Capture history and observations have independent bounded pagination.

The producer fingerprint identifies Python recipe sources. It does not attest
native OCR binaries, trained data or the complete image. The retained raster and
readings preserve what was observed. Native image identity belongs in separate
execution qualification evidence until runtime environment attestation is added.

The seven private F00-04 fields remain pending until clearer scans are available.
Disposable PostgreSQL qualification exercises concurrent idempotent retention,
real row-lock permission revocation and atomic rollback. The same new tests run
in the existing PostgreSQL CI job with two workers. Current hosted CI headroom,
main verification, deployed service compatibility and broader OCR qualification
remain separate release checks.
