# Portable operator preview and trusted host binding

This is a deterministic **public source export for a compatible application
host**, not a standalone application or an installation. It contains the exact
existing preview Python source, its static HTML and a closed SHA-256 manifest.
It contains no accounts, sessions, configuration, receipts, case documents,
keys, model files or test fixtures. Original preview/handoff/re-observation code
and all evidence/history formats remain unchanged.

Build into a new destination with `python scripts/build_operator_preview.py
DESTINATION`. Reusing a destination fails. Retain the manifest's SHA-256 through
a separately controlled review process; never approve a package by reading its
own checksum. A matching hash establishes bytes, not publisher authenticity or
the independence of a transfer channel.

The manifest pins all compatible host application Python files, the original
staged dependency closure, the packaging/binding tools and the host's dependency
declarations/lock. The host supplies the dependencies from that lock; this export
does not download or vendor them. Python 3.12+ is required. A source/dependency
change requires a fresh export and approval. No import path is added by the
loader, and no application or private store is loaded by manifest inspection.

The already initialized **disposable** host calls
`operator_preview_binding.bind_preview` with the package root, separately
approved manifest pin, trusted compatible host source root and a typed
`HostBinding`. The binding explicitly supplies the existing adapter, selected
source and handoff pin, context-binding pin, disposable profile, distinct
preparer/reviewer IDs and single canonical origin. These inputs come from
trusted operator wiring, never an HTTP body, uploaded manifest or URL. The
factory creates no identity, session, authority, receipt or provenance record.

Before executing source, inspection checks a closed package inventory, strict
manifest fields, ownership, permissions, link safety, bounded bytes and hashes.
It checks the compatible host inventory and loaded module origins against the
explicit host root, refusing an incompatible module namespace. Code already
loaded into the trusted host, Python dependencies and the host's administration
are part of the trust boundary; source hashes cannot attest an untrusted or
monkey-patched interpreter.

The default policy requires kernel-read-only package **and host source** mounts.
Host code may have owner-only `0600` or public `0644` source files; exported
assets must be `0644`, directories `0755`, all owned by the current UID with no
symlinks or hardlinked files. `require_readonly=False` is an explicit policy for
disposable qualification only, not an alternate production approval. At most
512 host files/8 MiB and a 20-second cooperative budget apply to each verification
pass. The factory repeats package/host inspection after construction, checks the
captured page bytes, revalidates both actor/source bindings and samples the final
clock before returning. There is no cached or persistent binding approval.

The result is an **unregistered ASGI callable**. The operator must separately
qualify any future listener/proxy deployment. The wrapper requires the exact
bound scheme and Host header and refuses duplicate Host, forwarding headers or
a mounted root path before authentication/body reads. No forwarded-header trust
or CORS is enabled. Existing current-session/RBAC/origin/CSRF admission, source
pins, original five-minute preparation window, blank independent checksum entry,
response withholding and all preview/re-observation budgets remain in force.
Binding does not renew that window or establish legal/execution authority.

Qualification uses fresh invented accounts and copied public code in a separate
Python process with a relocated host. It verifies preview and independent-entry
reads, revocation, substitution, expiry, namespace mismatch, changed page and
wrong host/proxy rejection without changing the four retained histories. It
does not qualify kernel-read-only native mounting, deployment, genuine operator
appointments, checksum-channel provenance, provider inference or legal review.
The private focused-analysis-v3 review remains pending.
