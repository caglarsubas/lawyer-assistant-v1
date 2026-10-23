# Disposable metadata phase diagnostics

One isolated operator probe distinguishes TCP connect, TLS handshake, request send,
response headers, body and metadata validation. It uses the existing relay's exact
bootstrap pin and approved authority with a shared four-second metadata deadline.
No request DNS, proxy, redirect, retry, completion POST, model generation, new
destination, timeout increase, production hook or serving-process patch is added.

The stdlib-only candidate validates a private binding constructed from the API's
effective vetted Provider settings against the actual relay process environment.
No agent receives this binding or its key. Only the existing fixed relay base,
configured model/context and matching approved transport are admitted. The private
native mode requires a vetted private IPv4; the tunnel mode retains its approved
public bootstrap IPv4, hostname verification, SNI and HTTP Host. Disabled TLS
verification fails before connection. No request reconnect is allowed after a
partial send. All network phases share the shrinking deadline, including body
reads after HTTPConnection transfers socket ownership to a closing response.

One connection is attempted. An authenticated GET to `/v1/models` is sent only
after connection and required TLS succeed. Earlier failure can therefore produce
zero GET attempts. Non-200 bodies are not read. Successful bodies are bounded to
one MiB, strict JSON with duplicate/nonfinite rejection and local model/context
checks. Bodies, credentials, URLs, IPs, model names, headers and exception text are
never returned or logged. Reports contain fixed phases, finite failure codes,
booleans, bounded HTTP status and counters only; cleanup failures stay redacted.

This is a fresh diagnostic observation that bypasses relay queue/coalescing and
filtering in a separate child, not a trace of a serving request. It cannot prove
the cause of an earlier timeout, immutable executed-model/tenant identity, native
capacity or legal accuracy. Even successful metadata stays unqualified. A timeout
phase localizes that observation; it does not establish why the network failed.

Before live use, verify the deployed relay source hash against the frozen source
and run the child as the existing relay UID 10003 within its unchanged firewall.
Read only the bounded current process environment; never resolve a replacement pin
or fall back to broader privileges when that evidence is unavailable. Keep effective
API credentials solely in memory and protected stdin pipes, never arguments,
generated source files, logs or public receipts. The live report is owner-only.
No source is installed and no service/container is restarted or reconfigured.

Freeze candidate, eight new invented P2101–P2108 cases, fake socket/TLS fixture,
evaluator, twenty contracts and this declaration before first grading. Expected
results: eight exact phase/outcome matches, eight mock connections, six mock GET
attempts, no POSTs and no qualified identities. Exercise every timeout phase,
redirect rejection and overflowing JSON exponents. Contracts also cover route/pin
binding, private-native mode, strict TLS, no DNS/retry, socket ownership, body and
deadline budgets, cleanup and safe output. Reproduce the whole report in read-only
network-disabled Linux with public code and temporary scratch only. Retain first
failures and reports; preserve all earlier frozen inputs without tuning them.

A live observation is separately bounded to one connection and at most one GET,
using no private document. It cannot authorize private-case regeneration or native
inference. Preserve originals, exact evidence versions, encrypted bytes, credentials,
sessions, review history and the pending owner v3 review. Compare full private state
and configuration before/after. Existing nine CI jobs, caps, workers, coverage and
five protected timing reserves remain mandatory before merge.
