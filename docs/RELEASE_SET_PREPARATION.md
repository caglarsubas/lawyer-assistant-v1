# Confidential multi-source review preparation

R02 can now compose **2–8 current reviewed provision sources** into one local,
deterministic review packet. It builds on the [source-set snapshot contract](RELEASE_SNAPSHOT_SET.md)
and preserves every source's assignment, revision, rights and exact passage checks.
The operator supplies explicit canonical identities; matching titles or text never
create identity links automatically. This is an engineering preparation milestone,
not source qualification, independent legal approval or a publishable release.

## Local operator workflow

Run on the trusted deployment host using its existing configuration, encryption key
and source-review database. The operator must already be an active administrator or
curator assigned to every selected source in the same firm. An operator ID selects
a local account; it is not a remote authentication credential. There is no API route
for this command and it must not be exposed as one.

```sh
backend/.venv/bin/python scripts/prepare_review_set.py schema
backend/.venv/bin/python scripts/prepare_review_set.py prepare \
  --operator-id EXISTING_OWNER_ID \
  --request-dir /secure/review-selection \
  --registry /secure/identities.json \
  --resolutions /secure/source-resolutions.json \
  --evidence-dir /secure/private-proof \
  --output /secure/combined-review
backend/.venv/bin/python scripts/prepare_review_set.py validate \
  /secure/combined-review --operator-id EXISTING_OWNER_ID
```

`schema` prints all three input schemas without loading deployment settings or
opening a database. `prepare` validates input structure before configuration is
loaded. `validate` rebuilds the packet against the same operator's current source
reviews, package bytes and ontology. A revoked right, changed revision, account
change, different ontology or modified packet fails validation. Retained old packets
are never silently rewritten or deleted by validation.

The selection directory contains exactly `sources.json`, using
`legal-review-source-selection-v1` from the snapshot contract. The shared registry
uses `legal-identity-registry-v1`: explicit instrument, provision and version IDs,
typed parent links and private identity-proof hashes. There are at most 600 entries.
The separate `provision-source-set-resolutions-v1` document contains:

```json
{
  "schema_version": "provision-source-set-resolutions-v1",
  "sources": [
    {
      "source_id": "REPLACE_WITH_FIRST_64_CHARACTER_LOWERCASE_SHA256",
      "items": [
        {
          "mapping_id": "REPLACE_WITH_32_CHARACTER_MAPPING_ID",
          "instrument_id": "urn:tr-law:instrument:example",
          "provision_id": "urn:tr-law:provision:example-1",
          "provision_version_id": "urn:tr-law:provision-version:example-1-v1"
        }
      ]
    },
    {
      "source_id": "REPLACE_WITH_SECOND_64_CHARACTER_LOWERCASE_SHA256",
      "items": []
    }
  ]
}
```

Replace the illustrative IDs; the example is intentionally unresolved. Source groups
must exactly match the selection, with no duplicates. Mapping IDs are local to their
source, so identical mapping IDs in different packages remain distinct. Missing
identity resolutions are visible blockers; unknown mappings and inconsistent registry
parents are rejected. Input JSON rejects duplicate keys and unknown/coerced fields.

The evidence directory contains exactly the union of required rights and identity
proofs, named `<sha256>.bin`. Every hash is checked against physical bytes. A matching
hash establishes byte identity only; it does not certify rights or legal meaning.
No existing source, review ledger, account, credential or graph release is modified.

## Conflict behavior

Cross-source conflicts identify the sources and, where applicable, mappings involved:

- One canonical version must agree on exact text hash, provision kind, instrument
  and provision parents, legal dates, text role, end status and checked-through date.
  The same text may occupy different offsets in different source representations.
- Different versions of one provision must not overlap. End dates are exclusive;
  adjacent finite intervals are allowed. An open-ended interval extends indefinitely
  for overlap checks; its checked-through date is not a legal end date.
- Repeated open-ended versions require explicit evidence reconciliation. The current
  temporal contract requires the same proof set on a version and its linking
  assertion. Preparation blocks this case rather than adding another source's
  evidence to an assertion automatically. Separately identified open-ended versions
  of different provisions remain supported.
- Content-identical raw artifacts with different acquisition timestamps are blocked
  because their content-addressed graph identity would have conflicting metadata.
- Unknown acquisition dates, unresolved identities, unknown legal dates and
  unsupported text roles retain the existing source-qualified blockers.

Any blocker withholds **both** combined RDF files. A valid blocked packet still
contains its exact sources and review report for correction. Malformed, stale,
unauthorized or oversized inputs fail the command instead of producing a packet.
Conflicts are never settled by source order or a guessed preferred authority.

## Packet and confidentiality boundaries

The new outer format is `legal-review-source-set-packet-v1`. It contains private
`binding.json`, `registry.json`, `resolutions.json`, `review-report.json` and
`private-evidence/<sha256>.bin`, plus candidate source bytes under
`candidate/sources/<source_id>/{raw.bin,text.txt,locators.json}`.
`candidate/sources.json` inventories only those derived source paths, hashes and
sizes. It excludes private proof files, review notes, titles and account identifiers.
The outer manifest inventories every file and is sealed with the deployment's
local preparation HMAC. This is integrity protection, not an independent signature.

An unblocked packet also includes `candidate/structure.ttl` and
`candidate/jurisprudence.ttl`. The combined graph is checked once against the full
ontology and SHACL contract, physical artifact inventory and exact Unicode quote
locations. This provision slice adds structural assertions; it does not populate
decisions. Every assertion remains unreviewed and both graphs retain every source's
preparation-only marker. Existing single-source packet readers, promotion and release
validation reject these packets/graphs.

**The entire packet, including its candidate subdirectory, is firm-confidential.**
Selecting public authorities is private workflow metadata; generated assertions also
retain mapping-review event times. A path called `candidate` grants no permission to
share it. Publication-safe attribution and release authorization remain later work.
Output directories use mode 0700 and files 0600; existing outputs are never replaced.

Preparation captures and locks the set, compiles and seals, then successfully exits
the first snapshot before writing. It reacquires the complete set, compares bindings,
writes atomically and checks output integrity. Inputs and ontology are recaptured,
and snapshot exit revalidates every source. A failed final check removes only the
output directory created by this invocation; unrelated pre-existing or replaced
directories are preserved. Success is reported only after all contexts exit.
SQLite remains an explicitly optimistic demo mode. These rereads are not filesystem
snapshot isolation against a privileged host continually replacing bytes.

The existing bounds remain: 64 MiB selected source artifacts, 400 accepted mappings,
200 mappings per source, 128 private proof files of at most 8 MiB each and 32 MiB
total. Combined preparation adds a 25,000 evidence-link budget before graph
allocation, a conservative allocation estimate and a 64 MiB output-content cap.
The shared packet writer also enforces its per-file and inventory caps. These are
not peak-memory or total-runtime guarantees. No additional CI job or dependency is
needed; tests run in the existing bounded two-worker job.

Successful JSON output exposes confidential counts, blocker codes and fingerprints,
with `signed: false`, `publication_eligible: false` and
`current_at_validation: true`. This last field means a successful point-in-time
check, not a reservation against later changes. Failure returns exit code 2 and the
fixed `review_source_set_preparation_failed` diagnostic without partial stdout.

## Next R02 gates

Independent multi-source signatures, publication-safe metadata, audience constraints,
expiry/renewal, source-set authorization and revocation remain unimplemented. R01
actual legal/privacy/source review and full research-job cancellation, throughput
and capacity qualification remain open. The existing single-source publication
workflow is unchanged.
