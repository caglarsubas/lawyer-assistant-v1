# Local provider relay

The API stays on internal Docker networks. Its optional native-engine route is
`http://172.30.240.2:8083/v1`, on the dedicated `172.30.240.0/28` provider network.
Check for a subnet collision before enabling this deployment. If the subnet is
changed, change the relay firewall's source subnet together with Compose.

The relay connects to `host.docker.internal:8080`, resolving the Docker host once
at startup to one RFC1918 IPv4 address. `PROVIDER_NATIVE_HOST` may instead be an
operator-pinned RFC1918 IPv4. Startup installs default-deny input, output and
forwarding policies, permits only that native host's TCP 8080 and requests from
the dedicated provider network, closes DNS, then drops to UID/GID 10003. It has
no published port, persistent volumes, database network, credential environment
or access logs. Its `/health` reports process readiness only.

## Explicit laptop-tunnel exception

An operator may approve one HTTPS tunnel whose upstream is the same locally
hosted inference engine. This is an internet-transport exception, not an
air-gapped deployment or permission to use cloud inference. Defaults remain
disabled. Keep `LLM_PROVIDER_BASE_URL=http://172.30.240.2:8083/v1` and configure
all three settings in the gitignored repository-root `.env`:

```dotenv
LLM_PROVIDER_TUNNEL_URL=https://your-exact-tunnel.example/v1
LLM_PROVIDER_TUNNEL_APPROVED=true
LLM_PROVIDER_TUNNEL_APPROVED_HOST=your-exact-tunnel.example
```

Only HTTPS port 443 and the exact `/v1` path are accepted, without credentials,
query parameters, fragments or wildcards. Verify the tunnel agent maps that
hostname to the intended native engine; matching TLS does not prove where the
tunnel terminates. Tenant binding and no-cloud-fallback checks below still apply.

The relay checks every DNS answer at startup, rejects non-public addresses,
pins one public IPv4, and permits only that IP's TCP 443. Each TLS connection
validates the approved hostname with the system trust store, connecting directly
to the pinned address without another DNS lookup. DNS is closed before serving.
Every model and completion request must match the API's approved-route fingerprint
before credentials or content are forwarded upstream. The relay overwrites
upstream transport metadata with its own; the API verifies it. These checks bind
deployment configuration, not remote hardware attestation. Route failures never
fall back to another tunnel, the native host or a cloud model. If DNS changes,
recreate the relay to validate and pin the new destination.

Review tunnel request inspection, upstream retention and telemetry separately.
The relay's lack of persistence does not guarantee that the tunnel or engine
retains nothing. Verify changes with synthetic text before any client matters.
Disable the exception by clearing URL and approved host and setting approval to
`false`, then recreate both API and relay; the relay returns to the native route.

Only authenticated `GET /v1/models` and bounded JSON `POST
/v1/chat/completions` are forwarded. Model discovery reveals only the configured
local model's required metadata. Generation must use that exact model, buffered
text messages and JSON output with at most 1,000 completion tokens. Other routes,
tools, image URLs, streaming, substitution, redirects and compressed responses
are denied. The bearer arrives in the request and is never persisted by the
relay. The native engine remains responsible for safe logging and tenant auth.

## Activation checks

1. Compare the user's root `.env` key with the protected engine registry, without
   printing either secret. Require `lawyer-assistant-v1`, `org-lawyer` and
   `lawyer-assistant-v1-primary`, with an active credential interval.
2. Verify the running native engine has cloud fallback disabled. The engine's
   `x-engine-model-substitution: off` header disables resident substitution;
   **it does not disable OpenRouter failure fallback**. Confirm the effective
   service configuration, process environment and startup time, or use a
   provider-supported runtime attestation. Do not change a shared engine's
   global behavior as a shortcut. A response-model check cannot prevent a prior
   disclosure to a fallback model.
3. Select one exact locally served model from authenticated metadata and set
   `LLM_PROVIDER_CONTEXT_LIMIT` no higher than its `max_model_len`.
4. Set the private relay URL, `LLM_PROVIDER_ALLOW_PLAIN_HTTP=true`, and only after
   the checks above set `LLM_PROVIDER_IDENTITY_VERIFIED=true` and
   `LLM_PROVIDER_CLOUD_FALLBACK_DISABLED=true` in the operator-managed `.env`.
   These booleans are deployment attestations, not automatic live guarantees;
   revalidate after any key, route, model or provider deployment change.
5. Recreate the API and relay. Use the authenticated application readiness check,
   then synthetic generation through the app. Separately test the API's lack of
   an internet route, relay denial of every destination except the selected
   native host TCP 8080 or explicitly approved tunnel IP TCP 443,
   no effective capabilities in its running Python process, and blocked admin
   paths. Successful connectivity does not qualify Turkish legal accuracy.

`scripts/provider_preflight.py` produces a secret-free registry and metadata
report. It does not modify keys, claim fallback isolation, or perform generation.
It checks the native endpoint independently of any tunnel settings; it does not
validate the tunnel route. `Provider.probe()` checks the configured relay route.

The public research gateway is independent. Enabling this route does not enable
internet research or cloud inference. The explicit exception enables only the
approved tunnel transport. Fresh deployments default to blocked
generation until both attestations and local-model metadata checks pass.
