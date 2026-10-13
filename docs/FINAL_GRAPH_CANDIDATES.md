# Final serving candidates and bounded permission requests

A trusted local operator can stage canonical Graph A/B serving payloads from a
current independently attested complete declared assembly. Every original A/B
source and component grant is reconstructed under the existing mixed transaction;
the resulting candidate remains unpublished and unauthorized for serving.

Configure `LA_GRAPH_FINAL_GRANT_TRUSTED_KEY` with a separately vetted Ed25519
**public** key. It identifies the future whole-release permission signer and must
differ in key material from all four component/private/final-review trust roles.
No command generates a key or signature, accepts a signed permission, or contacts
an inference or graph service.

```bash
python scripts/prepare_final_graph_release.py prepare \
  --packet /trusted/current-reviewed-assembly \
  --reviewer 'VETTED INDEPENDENT PERMISSION REVIEWER' \
  --approved-at 'ACTUAL-TIMEZONE-AWARE-PROPOSAL-TIME' \
  --expires-at 'TIME-WITHIN-ALL-CURRENT-COMPONENT-GRANTS' \
  --output /trusted/new-final-candidate

python scripts/prepare_final_graph_release.py validate /trusted/new-final-candidate
```

The placeholders are intentionally invalid until replaced with actual reviewed
identities and timestamps. Request approval time cannot be future-dated or precede
final review or component approval. Request expiry must be after approval/current
time, at most 90 days, and no later than **any** component's expiry; B component
expiry already includes source-specific rights and reviewer appointment bounds.
The proposed permission reviewer label differs from the final public reviewer.
Labels/key separation require external human vetting to establish actual independence.

The new immutable directory contains only:

- `prepared/`: independently validated final bundle, exact final attestation,
  ontology and physical evidence, canonical N-Quads and serving manifest.
- `permission/`: deployment-HMAC-sealed, encrypted review binding and unsigned
  `legal-final-assembly-permission-request-v1` signing input, with a fixed notice.
- `NOTICE.json`: explicit unsigned scope and serving denial.

The encrypted request binds final release/serving/ontology/review hashes, the
original reviewed packet digest, dependency and public-inventory digests, complete
component IDs, restore epoch, all six required uses, deployment audience, reviewer
and bounded dates. It asserts `signed: false`, `decision: request`, and
`national_release_serving_authorized: false`. No earlier A-only/B-only grant can
authorize these final payloads.

Validation verifies the original reviewed packet and its complete live sources;
it reconstructs the public candidate and exact permission input rather than
trusting the candidate's integrity seal. Candidate graphs/evidence/attestation must
match the reviewed bytes exactly. Extra files or directories, altered requests,
changed public bytes, revoked members, changed keys/epoch/base or expiry withhold
the whole candidate. Expensive public validation stays within the protected source
transaction; final byte, trust and lifetime checks run after original-source exit.

The original reviewed packet and original encrypted component grants must remain
available at their retained paths. They are referenced, not silently relocated or
reapproved. Every staging/validation operation reconstructs permission state afresh;
no validation survives the operation. Atomic no-replace writes preserve existing
evidence and discard only newly owned output after a late failure/interruption.
Directories/files remain private (0700/0600), with the existing 256-file/96 MiB
output and per-file read bounds. The candidate is not an installed runtime release.

The next gate is acceptance of an externally signed whole-release permission with
conjunctive current install/activation/rollback/read guards. Those guards must
distinguish immutable reviewed base dependencies from legitimate active-pointer
changes and support explicitly retained mixed-base inventories. Actual legal/editor
qualification, licensed corpus coverage, production key custody, deployment and
held-out lawyer acceptance remain separate requirements.
