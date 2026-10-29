# Verified bounded CI tool bootstrap

PR #246 passed its exact-head suite and reserve gates, then merged with a
matching tree. Independent main run `40806794079` failed its bounded cold pip
bootstrap after 20 seconds, before tests. It was cancelled; it provides no
main qualification. A warm PR cache cannot establish cold main readiness.

Replace `pip install uv` with a small closed Linux bootstrap. Keep uv `0.8.15`,
the 20-second whole bootstrap bound, 20-second frozen sync bound, zero download
retry, one-minute install-step cap, all ten jobs, test deadlines, workers and
reserve floors. There is no fallback to another version, package index or
unverified binary.

Only the exact ARM64 and x86-64 GNU Linux release archives are allowed. Their
hashes come from the official [ARM checksum](https://github.com/astral-sh/uv/releases/download/0.8.15/uv-aarch64-unknown-linux-gnu.tar.gz.sha256)
and [x86 checksum](https://github.com/astral-sh/uv/releases/download/0.8.15/uv-x86_64-unknown-linux-gnu.tar.gz.sha256).

On a miss, fetch the fixed HTTPS release URL within 15 seconds and verify SHA-256
before publishing to the existing pip-cache directory. On every hit, verify
again before extracting only the named executable into a fresh private runner
directory. Reject unsupported platforms, bad hashes and symlink archive entries.
Check the exact tool version before appending its path. Failed bootstrap never
exports a tool path; it does not silently discard or replace poisoned evidence.
The existing setup-python cache remains an optimization, never proof of trust.

The native public-image probe checks actual ARM execution from the verified
archive, then rejects intentional cache corruption. It uses no network or host
mount and removes its generated container/image. Three lightweight rejection
subtests run within the existing placement contract, preserving all 1,018 method
identities. See the [probe report](evidence/verified-uv-bootstrap-2026-10-29.json).
Both architectures, cold/warm bootstrap, exact PR head and independent main
still require fresh CI evidence. Earlier native receipt and private-runtime
preservation reports remain unchanged; operator custody and legal acceptance
are separate pending gates.

Bind the existing pip-cache key to both the frozen lockfile and the bootstrap
script. This creates a new immutable key instead of repeatedly restoring an
older wheel-only cache that cannot be overwritten. Cache contents still confer
no trust; every archive is checked against its fixed checksum before use.
