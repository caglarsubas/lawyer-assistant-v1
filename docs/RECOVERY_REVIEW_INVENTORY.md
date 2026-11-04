# Acknowledged recovery-review inventory

`ReviewInventory` is unregistered trusted wiring for one disposable operator
scope. It reads at most four host-registered review references. It does not
discover reviews by filename, choose a latest decision, recover an uncertain
acknowledgement or create any record. No matter, portfolio or public-data route
is registered by this component.

Each `Reference` contains the exact selection, review identity, review ciphertext
and plaintext hashes, and an explicitly present or missing decision ciphertext
hash. A retained decision whose acknowledgement is missing stays missing. Extra
ciphertexts are neither advertised nor decrypted. Their physical presence changes
the snapshot commitment, so an earlier inventory cannot silently be reused.
Unexpected staging blocks the read and remains untouched.

`inventory` authenticates the current assigned actor before inspecting the
registry or ciphertext. Within the original bounded namespace lock it checks
the same context twice, including source versions, original expiry, encrypted
reviews and current actor eligibility. It returns only acknowledged reference
metadata and outcomes. Stale and negative reviews remain visible as history;
inventory itself never grants handoff readiness. A changed observation, revoked
caller, invalid ciphertext or exhausted execution budget yields no partial list.

The inventory hash is bound to the caller's current session, host reference and
destination registries, and journal snapshot. It is a comparison commitment,
not an authorization token or a comprehensive current review-head claim. A
fresh read still checks authority, source applicability and time. The service
does not infer supersession between independent review records.

`handoff` requires an explicit registry entry, all exact references, the fresh
inventory hash and a separately registered destination ID. `DestinationPin`
binds that entry and destination to the review reference, selection, review
context, journal pins, target-context hash and fixed expiry. Missing pins are
never filled from observations or requests. A current independent acceptance is
required; the resulting expiry cannot exceed the review, destination or caller
session expiry.

Matching separately supplied hashes does not establish who provisioned a pin,
authenticate an external channel, inspect the physical destination or approve
key custody. Genuine provenance remains a separate operator gate. The fixture
issuer is explicitly invented and must not be used for real enrollment.

Readiness covers a disposable metadata handoff only. It does not publish or send
a packet, start a listener/controller, restore a store, renew trust, activate a
provider or establish production/legal approval. Cross-store atomicity and
privileged joint rollback remain unqualified. Every original ciphertext and
history stays unchanged; the component has no write operation.

The opt-in `qualify_recovery_review_inventory.py --output NEW.json` campaign
freezes 20 outcomes across three invented contexts. It retains six original
encrypted review records plus two deliberately injected entries, tests real
sessions and independently recorded decisions, and verifies unchanged source
stores, account files and original review bytes around reads. Its report binds
766 source/placement files and the preceding reviewed-input report hash.
It makes no native mount, listener, genuine destination-provenance, execution or
legal-acceptance claim. The owner's focused-analysis-v3 review remains pending.
