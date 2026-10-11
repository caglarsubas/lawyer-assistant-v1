# Registered public-source acquisition

This operator workflow acquires a closed set of public legal representations for
quarantine and later review. It is separate from the generic research gateway:
the latter still denies arbitrary non-root paths. No application API route
exposes this acquisition function, and no existing network profile is changed.

## Closed registry

| Registry ID | Intake domain | Exact registered representation |
|---|---|---|
| `tbmm-6101-enacted` | contracts | [TBMM: 6101, enacted text](https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y3/T1/KanunMetni/3c4eac23-5d02-49cd-9ef1-4bf8de05aee6.html) |
| `tbmm-6098-enacted` | contracts | [TBMM: 6098, enacted text](https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y2/T1/KanunMetni/a657b33d-109c-473d-9266-5aa48d603ab2.html) |
| `tbmm-4857-enacted` | employment | [TBMM: 4857, İş Kanunu, enacted text](https://cdn.tbmm.gov.tr/KKBSPublicFile/D22/Y1/T1/KanunMetni/359dee72-3cd1-4131-8597-48c58658e326.html) |
| `tbmm-6103-enacted` | commercial | [TBMM: 6103, commercial-code transition statute, enacted text](https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y2/T1/KanunMetni/7f9bad4f-097c-4097-960f-2ef0bb0ed482.html) |

The two additions follow the final-text links on TBMM's official
[4857 law record](https://www.tbmm.gov.tr/Yasama/Kanun/f72877bd-9f9a-037b-e050-007f01005610)
and [6103 law record](https://www.tbmm.gov.tr/Yasama/Kanun/f72877be-33d5-037b-e050-007f01005610).
Intake domains organize review; they are not exhaustive legal classifications,
applicability judgments or graph assertions. The 6103 entry is the transition
statute, not the entire 6102 commercial code.

TBMM identifies these as enacted texts that exclude subsequent amendments.
Acquisition preserves that historical representation and explicitly records
`current_consolidation=false`. None of these sources is presented as current
consolidated law. Adding or changing a destination requires a reviewed code and
registry-version change; users cannot substitute a URL, path, query or header.

New acquisitions use `tbmm-enacted-2026-10-11-v2`. The immutable
`tbmm-enacted-2026-10-04-v1` snapshot retains only 6098/6101 and their original
titles, URLs and contract-domain metadata. Offline preparation resolves the
manifest's declared version, preserves the original manifest bytes and rejects
missing/unknown versions or a new member claiming v1. It never defaults to the
latest registry or relabels an old acquisition. Validation binds metadata and
content; it does not authenticate an operator-supplied provenance declaration.

## Connected staging command

Use an approved connected staging host and an existing local API base image. Build
the separate fixed acquisition image containing the reviewed registry; this does
not retag, rebuild or restart the deployed API. The CLI resolves the acquisition
image to its immutable local ID and never pulls an image. A stale worker's registry
or mismatched title/domain is rejected before admitting its output. The output
parent must exist, and the output directory must be new.

```sh
docker build --pull=false --network none \
  -f deploy/public-source-acquisition.Dockerfile \
  -t lawyer-assistant-public-acquisition:0.1.0 .

mkdir -p .data/registered-acquisitions
python3 scripts/acquire_public_source.py tbmm-4857-enacted \
  .data/registered-acquisitions/tbmm-4857-enacted-2026-10-11 \
  --connected-staging
```

The only arguments are a registry ID, new output directory and explicit connected
staging opt-in. There are no custom URL, query, credential, proxy, image or header
options. A disconnected installation receives the resulting approved public
package through its normal media-transfer process; it does not run acquisition.

Each invocation starts one disposable container on Docker's standalone bridge,
outside the application's networks. It receives only a newly created empty
public staging directory. No application environment, `.env`, client documents,
private volumes, provider credentials or Docker socket is mounted or forwarded.
Proxy defaults are cleared and the worker starts with a minimal environment.
The filesystem is read-only apart from bounded scratch space and that staging
directory; capabilities are dropped, privilege escalation is disabled, and
memory, CPU and process counts are bounded. The CLI removes the worker even when
the Docker client times out, and requires cleanup confirmation before publishing.

## Network and response admission

- Resolve the exact registry hostname once; reject the entire answer if **any**
  address is non-global, reserved, multicast, loopback, link-local or an IPv4-mapped
  IPv6 address. Pin one admitted address for the connection while validating TLS
  against `cdn.tbmm.gov.tr` with the standard trusted CA store.
- Send only an exact `GET` for the registered path, with fixed headers and no
  query, cookies, authorization or request body. No redirect is followed.
- Require HTTP 200 and `text/html`. Reject compression, ambiguous framing,
  duplicate critical headers, malformed or incomplete content and empty bodies.
- Bound DNS/idle waits to five seconds and total network work to 20 seconds,
  including slow-drip headers. Content is limited to 1 MiB; total HTTP wire data
  also has a 1 MiB plus 64 KiB cap. A 45-second outer container wait bounds process
  overhead and cleanup starts after that wait fails.
- Do not parse, render, execute, scan, index or promote the acquired HTML in this
  worker. Errors never reproduce server bodies, arbitrary response headers or
  TLS diagnostics.

Failures report fixed categories such as `dns_timeout`, `http_status`,
`compression` or `exclusive_publication`; they never quote a remote diagnostic.
If Docker is still removing an auto-removed worker, cleanup waits briefly for a
successful absence check before admitting the package.

The host validates the resulting artifact names, lengths, exact manifest fields,
registered title/domain, timezone-aware acquisition ordering, pending states and
content hash before atomic publication to a new directory. Exclusive rename
prevents replacement even if another process creates the destination during the
acquisition. Linux and macOS are supported when their filesystems provide
[exclusive rename](https://man7.org/linux/man-pages/man2/renameat2.2.html);
[macOS support](https://developer.apple.com/documentation/foundation/urlresourcevalues/volumesupportsexclusiverenaming)
is checked by the operation itself. Unsupported publication fails closed.

## Output and next steps

The package contains only:

- `raw.html`: exact acquired bytes, untrusted and unscanned.
- `acquisition.json`: registry/source identity, original URL, acquisition start
  and completion timestamps, content hash, byte count, content-derived source
  version ID, and the enacted-text limitation.

State remains `rights_pending`, `legal_review_pending`, `quarantined`,
`untrusted_unscanned` and `not_processed`. A public URL, successful TLS or content
hash does not establish usage rights, legal applicability, current consolidation
or a qualified legal corpus.

Use the [offline preparation wrapper](REGISTERED_SOURCE_PREPARATION.md) to perform
the mandatory local malware scan, transcribe registered HTML in an isolated worker
and assemble exact passage locators and provenance. Import into the public-source
catalog explicitly, then collect accountable review evidence. Publication to an immutable
serving release remains a separate reviewed operation. No acquisition automatically
alters a graph, search index, private matter or reviewed work product.

Focused tests use synthetic HTTP/DNS fixtures only; passing them is not evidence
of acquisition or legal qualification. The separately recorded actual samples in
[validation](VALIDATION.md) remain pending human review. All four registry entries
use the same TBMM HTML representation; source/representation diversity, current-law
coverage and historical jurisprudence acquisition remain separate roadmap gates.
