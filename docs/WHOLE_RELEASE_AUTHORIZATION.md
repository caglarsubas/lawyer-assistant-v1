# Signed whole-release authorization and guarded serving

The complete declared A/B assembly, independent final legal attestation and
unsigned candidate request remain separate from permission to publish. The final
permission signer uses the fifth, independently configured Ed25519 public key.
No application command generates a signing key or signature. A declared release
is permission-qualified only for its acquired, reviewed inputs; this does not
establish nationwide corpus completeness or legal applicability to a matter.

The external signer's body is the **exact** encrypted candidate request, with
only these replacements:

- `schema_version`: `legal-final-release-authorization-v1`
- `decision`: `approve`
- `signed`: `true`
- `national_release_serving_authorized`: `true`

The envelope has exactly `algorithm: Ed25519`, `body` and a base64-encoded
64-byte `signature` over canonical UTF-8 JSON of the body. `approval_body` in
`app.final_release_authorization` produces unsigned signing inputs; it grants
nothing. The independent reviewer must inspect the complete candidate and
retained evidence before supplying an external signature. Approval cannot
extend any member's expiry, exceed 90 days, precede its final/component reviews,
claim another epoch, change identities/inventories or share component/final-review
key material. Permission reviewer labels must also differ from source ownership,
component permission/review and independent final review identities.

```bash
python scripts/review_final_publication.py \
  --candidate /trusted/final-candidate \
  --authorization /trusted/externally-signed-whole-release.json
```

Acceptance atomically creates a closed, mode-0700/0600 packet in the existing
private `release-authorizations/<release-id>` namespace. The signature and private
candidate binding are encrypted; a fixed routing marker reveals only namespace
and public release ID. It creates no graph installation or active pointer.
Existing outputs are never replaced. Any failed exit discards only a newly owned
output. The original candidate, reviewed assembly, components, private grants,
source bytes and institutional register must stay at their vetted paths.

For whole-release runtime serving explicitly set
`LA_GRAPH_SERVING_REVIEW_ROLE=final`; `component` remains the default for existing
source-only releases. The API, index builder and query-only Fuseki loader select
this configured public attestation role. They never try another key after a
failure. Keep all five vetted trust files configured and separately provisioned.
The final private permission remains broker-side; Fuseki receives no private
ledger, grant, original client files or inference credentials.

Use the existing operator publication CLI with the **final review** public key
for whole-release installation and transitions:

```bash
python scripts/graph_releases.py --root /trusted/publication install \
  /trusted/final-candidate/prepared --trusted-review-key /trusted/final-review-public.pem
python scripts/graph_releases.py --root /trusted/publication activate FULL-RELEASE-ID \
  --trusted-review-key /trusted/final-review-public.pem \
  --expected-current none --expected-sequence 0
python scripts/graph_releases.py --root /trusted/publication rollback \
  --trusted-review-key /trusted/final-review-public.pem \
  --expected-current CURRENT-FULL-ID --expected-sequence CURRENT-SEQUENCE
```

Replace all placeholders with actual vetted paths and observed pointer values.
Omitting `--root` retains the stopped-service Compose coordinator. Mount and
retain the exact approved paths in that coordinator; moving a host packet into a
different container namespace does not rebind an approval. No service is stopped,
restarted or deployed automatically. A release with a different attestation role
requires explicitly supplying that role's public key, including rollback.

Every install, activation, rollback and runtime read reconstructs the complete
current A/B sources, rights, owner, independent reviewers, canonical identities,
equivalence reviews, institutional-register evidence, appointments and component
grants under one globally ordered database transaction. Exit checks cover all
bytes, inventories, keys, ontology, epoch, expiry and original ledgers. No legal
or permission verdict is cached between uses. A change in **any** member withholds
the whole release; a denied namespace never falls back to another policy.

Preparation continues to require the exact declared active base. Signed serving
has an explicit context: the immutable original base inventory and dependency
fingerprint remain required, while the live pointer has its own before/after
contract. Read requires the exact active installed release; runtime readers pin
its sequence. Activation and rollback require the publisher's real exclusive
lock and exact monotonic CAS transition. Shared readers block transitions; stopped
API/Fuseki services remain an operational prerequisite. Rollback revalidates its
target's present permission and never restores revoked authority.

A failure after rename or pointer replacement raises `TransitionOutcomeUnknown`.
Inspect the installed bytes and exact pointer before deciding any next action;
never retry blindly. No repair, replay or granting permission follows from an
unknown outcome. Reviewed work is not silently rewritten by these transitions.

Qualified tests use invented sources and external **TEST-ONLY** signatures,
including first activation, two-release rollback, retained structural base,
rights withdrawal in either family, epoch/key/packet changes, late failures,
closed inventories and real PostgreSQL readers blocking both source families'
rights writers. Actual licensed corpus/legal qualification, deployment and
lawyer acceptance remain separate gates. Reassembly onto a previously mixed
active base remains a separately gated successor; it fails closed here.
