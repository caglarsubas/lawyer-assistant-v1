# Registered source preparation for curator review

This R01/R03 packet connects [registered acquisition](REGISTERED_SOURCES.md) to
[public-source staging](PUBLIC_SOURCES.md). Operators can turn one quarantined
TBMM HTML representation into original bytes, extracted passages and an inspectable
source map. It does not approve a source, acquire current law, populate either graph
or add authorities to research.

## Run offline

Use the existing evaluated local API and scanner images. Build the separate
preparation image without network access; this does not start or replace an API:

```sh
docker build --pull=false --network none \
  -f deploy/public-source-preparation.Dockerfile \
  -t lawyer-assistant-public-preparation:0.1.0 .

backend/.venv/bin/python scripts/prepare_public_source.py \
  /approved-public/acquired-tbmm-6101 /approved-public/prepared-tbmm-6101 \
  --signatures /approved-signatures/clamav
```

Input is an exact two-file acquisition (`raw.html`, `acquisition.json`). The output
parent must exist; the output directory must be new. Only the closed registry and
current registry version are accepted. Custom URLs, raw-file substitutions, image
options, signature-age overrides and asserted clean-scan documents are unavailable.
Neither CLI nor workers load `.env`, contact inference or use a database.

Images must already exist locally; the wrapper resolves both to immutable IDs and
uses `--pull never`. Disconnected installations receive sources, images and official
CVD signatures through their approved transfer process. Missing/expired signatures
stop preparation. Use the separate [signature workflow](../deploy/scanner/README.md)
for provisioning; preparation does not download databases, change the deployed
scanner or extend its age policy.

## Scan first, parse second

The host captures a bounded exact acquisition inventory with descriptor-relative
no-follow reads, regular-file checks, hardlink rejection and repeated captures.
It verifies registry identity, original digest/length, enacted-text limitations,
pending review states and timezone-aware acquisition ordering. This binds
operator-supplied provenance; it cannot authenticate a historical acquisition.

A disposable disconnected scanner receives only a read-only public snapshot and
the read-only official signature directory. It cryptographically verifies all three
CVD databases before and after `clamscan`, rejects changed databases and requires
zero exit status. Configured limits reject encrypted/broken or over-budget content.
Daily signatures must be no older than seven days. The 120-second scan subprocess
deadline fails closed; the engine's soft scan-time limit is disabled because it can
assume clean on timeout. The complete worker has a 180-second deadline, 3 GiB memory,
one CPU and 64 processes. Its receipt binds the original digest and all three
signature digests, sizes, versions, counts and build dates.

Only after a source-bound clean receipt and another snapshot check does the wrapper
start the parser. It receives the same read-only snapshot and a new output directory,
with 256 MiB memory, one CPU, 32 processes and a 45-second outer deadline. Both workers
use `--network none`, a read-only root, bounded non-executable scratch space, no
capabilities, no privilege escalation, a minimal environment and cleared proxy
defaults. They have no application networks, ports, matter volumes, credentials or
Docker socket. Cleanup is required on success and failure before output publication.

## Transcription and exact locators

The adapter supports strict UTF-8 (including an initial BOM), explicitly declared
Windows-1254 and ISO-8859-9. It does not guess undeclared legacy encodings or replace
undecodable characters. Unsupported/conflicting declarations fail.

An inert HTML parser extracts blocks, decodes character entities, trims outer block
whitespace and inserts two newlines between retained blocks. It omits head, script,
style, template, iframe, object, SVG and noscript regions. Nested omitted regions
stay omitted; ambiguous self-closing executable regions and unclosed omitted regions
fail. No browser, external resource, DTD, model or rendering is used. CSS visibility,
visual order, images and other non-text content remain unverified. An omission count
is not a completeness denominator.

Every passage has exact half-open Unicode offsets in the extracted text, a passage
digest, and a corresponding decoded-original source-code range plus line/column.
Original ranges exclude an initial UTF-8 BOM and count Unicode code points, not bytes,
UTF-16 units or rendered-page positions. Ranges include intervening inline markup and
outer whitespace. These are inspection locators, not provision identities or proof
of fidelity. The decoded-original digest and encoding make positions reproducible
against retained raw bytes. Inspect Windows-1254 originals in a text editor using
that encoding.

Limits are 1 MiB original HTML, 2 MiB extracted UTF-8, 5,000 passages and 20,000 code
points per passage. Exceeding a limit fails the whole preparation; no silently
truncated package is emitted. Publication/effect dates remain explicitly unknown.
Original acquisition dates are preserved and never substituted for legal dates.

## Output and explicit import

Seven owner-read-only files are published into a new owner-only directory with
exclusive atomic rename. Existing destinations are never replaced:

| File | Use |
|---|---|
| `raw.bin` | Exact original HTML bytes, retained as an inert attachment |
| `text.txt` | Extracted UTF-8 |
| `locators.json` | Import-compatible exact passage map |
| `source.json` | Import-compatible public-origin and date declarations |
| `acquisition.json` | Unchanged acquisition record |
| `preparation.json` | Adapter version, encoding, decoded-original digest/ranges, omissions, parser-call wall time and limitations |
| `admission.json` | Artifact digests, immutable worker IDs, signature evidence and scan wall time |

A privileged host can alter files; digests detect alteration but do not authenticate
independent review or establish legal truth. Scan/parser timings measure individual
calls, exclude curator effort and do not establish representative corpus throughput.

Import explicitly into a dedicated public-only staging store:

```sh
backend/.venv/bin/python scripts/public_sources.py --store /public-staging import \
  --metadata /approved-public/prepared-tbmm-6101/source.json \
  --raw /approved-public/prepared-tbmm-6101/raw.bin \
  --text /approved-public/prepared-tbmm-6101/text.txt \
  --locators /approved-public/prepared-tbmm-6101/locators.json
```

Keep acquisition/preparation/admission sidecars in the review archive; the catalog
importer accepts the four source artifacts, not these sidecars. A host staging tree
does not update the Docker catalog. For an approved installation, use the documented
isolated import container and dedicated public-source volume. Claim the source in
the curator workspace and assess rights, identity, fidelity and legal context
separately.

All sources remain rights pending and legal review pending. Enacted text remains
explicitly **not current consolidated law**. Public-origin declarations cannot prove
absence of PII; sensitivity review remains open. Preparation fabricates no reviewer
signature, permission evidence, semantic reference, publication or graph identity.

## Observed sample and next qualification gate

On 10 October 2026 the previously acquired 6101 representation (acquisition dated
4 October) passed the real disconnected scanner and parser. It produced 38 passages
from declared Windows-1254. A new acquisition attempt for each registered source
stopped at the gateway DNS timeout and admitted nothing. The retained sample is not
a fresh acquisition, representative corpus or legally reviewed reference. See
[verification](VALIDATION.md) and the [receipt](evidence/registered-source-preparation-2026-10-10.json).

Next: restore the approved connected acquisition route, obtain diverse lawful
originals across the three practices and representations, have qualified curators
review fidelity/rights/history, and independently author source-linked references
with measured review effort. R01/R03/R05A legal qualification remains open.
