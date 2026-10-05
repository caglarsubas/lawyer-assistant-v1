# Local malware-scanned intake

The runtime scanner is ClamAV 1.4.6, pinned to the official multi-architecture Debian image digest in `Dockerfile`. It runs as uid 1000, has no capabilities or published ports, and only joins the internal `scanning` network shared with the API. It has no matter volume, credentials, extraction-worker network, public gateway or Internet route. Temporary scan data stays in a bounded, non-executable tmpfs.

The custom entrypoint verifies three official CVD signatures with `sigtool --info` before starting `clamd`. It never invokes FreshClam. The vendor entrypoint is deliberately bypassed: disabling its FreshClam daemon alone does not prevent an initial download on an empty database directory. ClamAV signature databases must be staged and admitted explicitly.

## First provisioning

Build the scanner image on an approved connected build machine:

```sh
docker compose build scanner
```

To acquire public signatures on that connected staging machine, run:

```sh
python3 scripts/scanner_signatures.py fetch --destination .data/clamav-signatures
```

`fetch` runs a disposable FreshClam container outside the application networks. It receives only a temporary public signature directory and configuration, with no application environment or private data. It acquires `main.cvd`, `daily.cvd` and `bytecode.cvd`, then verifies their cryptographic signatures in a second, disconnected container. Successful admission atomically publishes a new directory containing those files and a checksum/version manifest. Downloads or validation failures publish nothing. The destination must not already exist.

For an air-gapped installation, transfer the image and official CVD files through the organization's approved media/package process, then verify and publish locally:

```sh
python3 scripts/scanner_signatures.py import \
  --source /approved-media/clamav \
  --destination .data/clamav-signatures
docker compose up -d scanner
```

The default Compose bind mount is `.data/clamav-signatures:/var/lib/clamav:ro`. `LA_SCANNER_DATABASE_DIR` can select another approved directory. Set `LA_CLAMAV_HOST=scanner` in the repository-root `.env` and recreate the API after first provisioning.

## Controlled updates

Import or fetch to a **new** destination, for example `.data/clamav-signatures-2026-10-04`. Set `LA_SCANNER_DATABASE_DIR` to that directory and run `docker compose up -d --force-recreate scanner`. Check `docker compose ps scanner` and the application's intake-readiness view before accepting documents. Keep the previous package for bounded rollback, provided its daily signature date still passes policy. Do not replace files inside a currently mounted release or rely on hot reload; runtime `SelfCheck` and automatic updates are disabled.

Daily signatures may be at most seven days old by default. `LA_SCANNER_MAX_SIGNATURE_AGE_DAYS` accepts 1–14 days, with the same policy applied during import, daemon health checks and **every upload**. Import uses `--max-age-days` when an explicitly chosen different policy is required. The signed build date is checked; changing file modification time cannot make an old package current. Main/bytecode databases may legitimately be older and still require valid official signatures and a positive signature count. Future-dated signatures are rejected beyond five minutes of clock tolerance. Offline operators must arrange approved updates within this window; expiry blocks intake.

## Admission and failure behavior

Before transmitting content the API checks PING and the loaded engine's VERSION/date. One total deadline bounds health, transmission and fragmented response reads. Only the exact complete `stream: OK` response admits a document. Malware detections, encrypted content and exceeded engine scan limits are rejected; unavailable, stale, malformed or truncated responses fail closed. Daemon responses, hostnames and signature names are not reflected into user-facing errors. Scan limits are 20 MiB input, 100 MiB expanded data, 12 nested layers, 5,000 members, two scanning threads and a 20-second scan budget.

ClamAV screening is one intake control and does not prove arbitrary files harmless. Parsing still takes place in the separately isolated extraction service. An accepted scan never grants source content authority to instruct agents.

The scanner logs operational settings and generic `stream` detections locally; it receives neither filenames nor matter identifiers. No file quarantine copy is persisted by this service.

## Evidence checked on 2026-10-04

- Official Debian image supports native `linux/arm64`; upstream index digest `sha256:a3cbbbc2b17a3871862689c0773bc9f5d70a1e4914ada7c8a05e157722ee8a9d`.
- Actual cryptographic admission: main version 63 (3,287,027 signatures), daily version 28142 (355,713), bytecode version 339 (80).
- Loaded daily signature date: `2026-10-03T06:24:16Z`.
- Live daemon accepted synthetic clean text and rejected an EICAR test stream assembled in memory. No EICAR file was written to the host.

References: [ClamAV Docker behavior](https://docs.clamav.net/manual/Installing/Docker.html), [official CVD signature verification](https://docs.clamav.net/manual/Signatures.html), [clamd transport and scanning](https://docs.clamav.net/manual/Usage/Scanning.html). These are operational references; deployed image/configuration and observed health remain the release evidence.
