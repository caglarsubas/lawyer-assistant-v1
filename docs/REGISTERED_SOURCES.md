# Registered public-source acquisition

This operator workflow acquires a closed set of public legal representations for
quarantine and later review. It is separate from the generic research gateway:
the latter still denies arbitrary non-root paths. No application API route
exposes this acquisition function, and no existing network profile is changed.

## Closed registry

| Registry ID | Exact registered representation |
|---|---|
| `tbmm-6101-enacted` | [TBMM: 6101, enacted text](https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y3/T1/KanunMetni/3c4eac23-5d02-49cd-9ef1-4bf8de05aee6.html) |
| `tbmm-6098-enacted` | [TBMM: 6098, enacted text](https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y2/T1/KanunMetni/a657b33d-109c-473d-9266-5aa48d603ab2.html) |

TBMM identifies these as enacted texts that exclude subsequent amendments.
Acquisition preserves that historical representation and explicitly records
`current_consolidation=false`. Neither source is presented as current
consolidated law. Adding or changing a destination requires a reviewed code and
registry-version change; users cannot substitute a URL, path, query or header.

## Connected staging command

Use an approved connected staging host with the locally built application image
`lawyer-assistant-api:0.1.0` containing this workflow. The CLI resolves that image
to its immutable local ID and never pulls an image. The output parent must exist,
and the output directory must be new.

```sh
mkdir -p .data/registered-acquisitions
python3 scripts/acquire_public_source.py tbmm-6101-enacted \
  .data/registered-acquisitions/tbmm-6101-enacted-2026-10-04 \
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

The host validates the resulting artifact names, lengths, provenance fields and
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

Before staging in the public-source catalog, perform the mandatory local malware
scan and isolated extraction, preserve passage locators, and assemble the
required provenance and review-evidence package. Publication to an immutable
serving release remains a separate reviewed operation. No acquisition automatically
alters a graph, search index, private matter or reviewed work product.

Focused tests use synthetic HTTP/DNS fixtures only; passing them is not evidence
that either registered source was actually acquired or legally qualified.
