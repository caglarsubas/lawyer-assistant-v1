# Security boundaries and qualification gaps

This document describes implemented controls and their limits. It does not certify a production environment.

## Trust boundaries

1. Browser → API: authenticated HttpOnly SameSite sessions, CSRF token on mutations, allowed origins, metadata-only errors and no-store responses. Production requires TLS/secure cookies and customer identity controls.
2. User → matter: membership and firm checks precede reads, mutations, research and export. Firm administration alone grants no matter access. Research rechecks access before inference and publication.
3. Matter → storage: encrypted aggregate payloads and encrypted originals; identifiers/access-routing metadata remain plaintext. The data encryption key must be backed up separately and protected by customer key management. Demo keys sit beside synthetic demo data and are unsuitable for customer use.
4. Matter → graphs: private selections remain encrypted in matter products; public RDF datasets receive no automatic updates. No arbitrary graph query endpoint is exposed to agents. Both families activate as one independently signed release; runtime mounts are read-only, query-only services hold a publication lock, and API reads validate release receipts and signed source membership. No active reviewed release means no graph evidence fallback.
5. API → inference: private destination checks, server-held bearer key, explicit tenant-binding attestation, pinned model, context budget, no redirect/proxy inheritance, strict response validation. An explicitly approved laptop tunnel can be reached only through the restricted relay: exact HTTPS hostname, startup DNS validation and IP pinning, TLS hostname verification and per-request route binding before upstream forwarding. This exception uses public-network transport and is not air-gapped. It grants no general external-provider access; tunnel inspection/retention and provider-side cloud-fallback prohibition still require operator verification. See [relay contract](../deploy/provider/README.md).
6. API → gateway: exact payload/destination/user/matter/policy digest, expiring single-use requests, explicit matter-request approval. Generic queries are restricted to registered legal vocabulary and registered destination paths. Unknown narrative/identifiers fail closed pending stronger detectors. Approvals cannot override a DENY.
7. Gateway → public source: allowlisted HTTPS destination, DNS answer checks and connection pinned to the checked address, no redirects, bounded response, quarantine/hash/provenance. Incoming HTML is not rendered or promoted to authority. No original matter documents or inference keys are present in the gateway container.
8. API → extractor: independent token and byte-only input; no matter identifiers or provider secrets. The service has no matter/database mount and shares only a dedicated internal network with the API. Resource-bounded child processes return strictly validated text/locators. Production does not fall back to local API parsing.
9. Connected staging → offline public catalog: the one-off acquisition CLI accepts only code-reviewed registry IDs, with no user text, URL, headers, credentials or matter mounts. It validates every DNS address, pins the TLS connection and bounds transfer time/bytes. Its output is untrusted quarantine; scanning, text extraction, rights and legal review are separate admission steps. The API mounts staging read-only. Only active admin/curator roles can inspect metadata, exact passages or an integrity-checked opaque original attachment. Staged records never enter research automatically.
10. Curator → review dossier: source-review ownership, evidence selections and rationale are firm-confidential encrypted records, not public graph annotations. Authenticated account/session/firm checks precede reads and mutations; writes lock the live account/session rows and use optimistic revisions. Acceptance requires explicit evidence and scope, but remains an unsigned reviewer attestation; publication still requires the independent release-review process. Source-review assistant guidance never implicitly includes this content or calls inference.
11. Reviewed source → provision mapping: deterministic heading detection produces untrusted proposals. Exact text and offsets derive from the verified package; arbitrary client-supplied quote text is not accepted. Mapping mutations require source-review ownership and both revision counters. Acceptance needs complete non-whitespace locator coverage, accepted source reviews and scoped local-processing/display rights. Any source-review revision change invalidates earlier mapping acceptance for handoff. Reviewer-supplied identities and dates are not canonical graph resolution or proof of applicability; unsigned dossiers remain outside shared RDF/search services.
12. Accepted mappings → offline review preparation: current owner and both ledgers are locked/revalidated; six explicit use scopes and physical rights/identity evidence are required. Private binding, references and proof stay outside candidate RDF. Deployment-local HMAC seals protect exact inventories but are not legal signatures. Preparation markers fail closed at release validation. Preparations remain unsigned; only the separate reviewed conversion can produce signing inputs.

13. Review → publication: public graph signatures and private deployment-audience authorization bind exact transformed bytes, current source/mapping state, six uses, proof inventory, expiry and local epoch. Installation, activation and rollback require a live locked private gate; legacy signatures alone fail closed. API graph/search/research/review/export also enforce current authorization. Private records never reach Fuseki. Restore removes the historical epoch; manual restores must do likewise before service startup. See [publication contract](PUBLICATION_AUTHORIZATION.md).

## Planned BYOK boundary — not implemented

The [5 October requirement amendment](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md) adds a
separate optional broker/vault for OpenAI, Anthropic and Gemini deep research. Existing
controls above remain the implemented behavior: neither the local-provider relay nor
the public-source gateway supports this by changing an allowlist or adding a key.

The planned broker accepts only an approved locally sanitized scenario, a scoped key
reference and job capability. It has no private document/matter-store access. Privacy
checks include contextual and cumulative disclosure; fidelity checks prevent changing
legally material dates, amounts, roles or facts. Approval binds the complete provider,
model, tool, retention and budget envelope. Provider-managed downstream searches have
separate disclosure/qualification because initial-payload approval does not inspect
all remote searches. Returned content remains untrusted until independently admitted
and verified; final application to private facts runs locally. Disconnected mode must
emit no external research traffic. See the amendment for key lifecycle, revocation,
retry/spend, retention and per-provider release tests.

## Mandatory unfinished qualification

- Network deny rules must independently contain compromised processes. An internal Compose network is useful isolation but does not replace a customer firewall, host hardening, TLS and egress tests.
- The separate extraction service and resource-bounded subprocess require target-host filesystem/process/network escape testing before real confidential intake. Container separation is not proof against kernel vulnerabilities or a compromised API. Non-demo intake also fails closed without a configured ClamAV service; signature supply must work offline.
- The current query policy is intentionally restrictive. It has not met the ≥98% legitimate-sensitive-task target. Add local Turkish PII/entity detection, secret detection, contextual intent rules, multilingual/injection cases and lawyer-adjudicated ethical behavior checks before broader outbound query support.
- The provider's tenant identity setting records operator attestation; the consumer contract lacks a non-admin whoami proof. Independently verify the activated key mapping without exposing administrative routes or secrets to the assistant.
- No national legal-review signoff or licensed historical corpus is bundled. Source or model text cannot self-approve an assertion, disable policy, alter the graph schema, or grant access.
- OpenSearch/Fuseki are private services. Their current development topology assumes trusted service identities and encrypted host disks; multi-tenant ACL/TLS/credential hardening and resource-abuse testing are required before customer exposure.
- Retention, legal holds, deletion propagation, cryptographic key rotation, tamper-resistant audit retention, backup rotation, migrations and revocation during concurrent actions need production qualification.

Security regression tests assert failure behavior as well as successful workflows. Unknown coverage, extraction failure, source ambiguity and service unavailability remain visible to the lawyer. A failed mandatory control blocks its action instead of silently weakening policy.
