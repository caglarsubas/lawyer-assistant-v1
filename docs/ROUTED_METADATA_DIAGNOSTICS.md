# Read-only routed metadata diagnostics

This separate observer wraps the frozen provider-identity collector without changing
its validation or granting execution authority. One invocation permits at most one
authenticated GET to the exact existing vetted model-list route. Configuration
rejection sends nothing. There are no completion POSTs, retries, redirects, proxy
environment use, cloud fallback, new destinations, credentials or production hooks.

The report contains only a fixed recipe/stage, bounded HTTP status, finite client
error class and allowlisted relay code, error-body inspection state and counters.
It excludes bodies, exception messages/types/traces, headers, URLs, model names,
tenant/key labels, hashes and arbitrary server fields. A non-200 error body can be
read in memory only up to 4096 bytes and the shared ten-second diagnostic deadline.
Compressed bodies, invalid JSON, duplicates, nonfinite numbers, unknown codes and
incomplete/budget-exceeded bodies supply no relay code. No prefix is accepted.
Successful metadata keeps the frozen collector's one-MiB and elapsed-time guards.

HTTP rejection, client transport failure, encoding, JSON, relay-transport identity,
model inventory/selection, local context and changed configuration remain distinct
fixed stages. Only known literal collector errors are classified; unknown exceptions
produce a silent generic rejection. A reported relay code describes what that relay
reported, not independent proof of ultimate upstream cause or the old HTTP 502
incident. Missing stage evidence remains unknown; no error message is guessed.

Even accepted unsigned metadata supplies no qualified identity or native authority.
This observer accepts no trust key and emits no runtime pin. The separately observed
local manifest is not routed execution proof. Signed provider/relay identity and
request/response binding, independently provisioned trust, durable campaign guards
and fresh bounded native acceptance remain separate requirements.

Freeze candidate, twelve new invented D2001–D2012 cases, fixture, evaluator,
twenty contracts and this declaration before first grading. Expected outcomes are
twelve exact stage matches from twelve mock GETs, zero POSTs and zero qualified
identities. Cases include legacy success, relay closure, untrusted error content,
redirect, timeout, malformed JSON, foreign route, missing model, context mismatch,
oversize, encoding and changed configuration. Contracts also test safe output,
finite allowlists, error-body size/time/parse limits, one-request boundaries and
configuration denial. Reproduce the complete report and contracts in read-only,
network-disabled Linux with scratch only and no private mounts.

A separate explicitly requested live diagnostic may load existing app settings in
memory and perform one fresh GET through its approved route. Preserve its fixed
report locally with owner-only permissions. Never log secrets or original documents,
recreate a container, change provider settings or run inference. Compare full private
database/evidence/original/vault/history and configuration hashes before and after.
Record actual findings separately from frozen synthetic expectations. No legal
review, private analysis regeneration, production install or source mutation follows.
Keep CI topology, workers, time caps, coverage and five timing reserves unchanged.
