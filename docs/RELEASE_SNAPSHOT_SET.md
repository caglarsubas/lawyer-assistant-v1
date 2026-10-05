# Consistent review of multiple sources

The R02 foundation inspects **2–8 existing reviewed source packages in one database
transaction**. A trusted local operator supplies each source's exact review and
mapping revision. The command returns confidential counts and a fingerprint only
after all checks, including checks on context exit, succeed.

This is a read-only inspection contract. It does not compile a combined graph,
create a review packet, sign, publish, activate, acquire data or approve rights.
R01 representative-source and legal/privacy qualification remains open.

## Operator command

Use the deployment's Python environment on its trusted host. The `inspect` command
loads the existing deployment configuration, encryption key and database; it does
not initialize missing storage, create an account or change credentials. An operator
ID is a local administrative selection, not remote authentication. Do not expose
this command as an API accepting an arbitrary operator ID.

```sh
backend/.venv/bin/python scripts/inspect_review_set.py schema
backend/.venv/bin/python scripts/inspect_review_set.py inspect \
  --request-dir /secure/review-selection --operator-id EXISTING_OWNER_ID
```

`schema` requires no deployment settings, credentials or database. The request
directory must contain exactly one regular, unlinked `sources.json` file, at most
64 KiB. Symlinks in the directory ancestry, hard links, extra files, duplicate JSON
keys, unknown fields, invalid identifiers, repeated sources and coerced revisions
are rejected. Example structure (replace both placeholder IDs with actual IDs):

```json
{
  "schema_version": "legal-review-source-selection-v1",
  "sources": [
    {
      "source_id": "REPLACE_WITH_FIRST_64_CHARACTER_LOWERCASE_SHA256",
      "expected_source_review_revision": 5,
      "expected_mapping_revision": 2
    },
    {
      "source_id": "REPLACE_WITH_SECOND_64_CHARACTER_LOWERCASE_SHA256",
      "expected_source_review_revision": 5,
      "expected_mapping_revision": 2
    }
  ]
}
```

Both revisions must be integers from 1 to 1,000 and match the current ledger. Every
source must be assigned to the selected active administrator or curator in the
same firm. Each must independently pass all existing source-review, accepted
mapping, history-integrity and six-use rights checks from the
[single-source contract](RELEASE_PREPARATION_CONTRACT.md).

Success writes one JSON summary to stdout: source count, mapping count, total
artifact bytes, binding SHA-256, consistency mode, `signed: false`,
`publication_eligible: false` and `confidentiality: firm_confidential`. Source IDs,
passages, reviewer notes, account/firm identifiers and credentials are omitted.
Counts and fingerprints are still confidential selection metadata. Failure returns
exit code 2 and a fixed diagnostic on stderr, with no partial stdout. Treat a
successful result as a point-in-time inspection; repeat it before subsequent work.

## Consistency and bounds

- PostgreSQL acquires the operator row first, then source-review and mapping heads
  in ascending source-ID order. One session retains all locks until exit. Existing
  authenticated writers use a compatible order. Requests from the same operator
  serialize, including a group of five simultaneous inspections.
- Each source keeps its existing `legal-review-snapshot-v1` binding. The containing
  `legal-review-snapshot-set-v1` binds the complete sorted selection and explicitly
  denies publication eligibility. It is not accepted as an existing publication
  authorization or prepared packet.
- Original artifact bytes and metadata/review fingerprints are retained privately.
  All sources are revalidated before the caller receives them and again at exit.
  Returned-object mutation also fails the operation. Request bytes are recaptured
  before exit. The caller must discard dependent output whenever exit fails.
- At most 64 MiB of total selected artifact bytes and 400 mappings are admitted.
  Per-package limits still apply. This aggregate bound is not a peak-process-RAM
  guarantee: decoding, verification and temporary reads require additional memory.
- Existing PostgreSQL bounds are a five-second connection timeout, five-second
  lock timeout and fifteen-second statement timeout. These are individual
  database-operation limits, not a total workflow deadline or cancellation API.
- SQLite is available only through existing explicit demo storage. Its reported
  mode is `sqlite_demo_optimistic_revalidation`; it cannot guarantee transactional
  row locks or replace PostgreSQL concurrency qualification.

Source packages are immutable through the supported store API. Rechecks detect
ordinary tampering during inspection; they are not filesystem snapshot isolation
against a privileged host replacing bytes between reads. The internal Python
interface accepts no untrusted SQL or source query language.

## Remaining R02 work

Canonical identity/version conflicts across sources, public/private manifest
composition, audience restrictions, expiry/renewal, aggregate compilation,
publication/revocation, cancellation and full research-job capacity qualification
remain subsequent packets. Matching source-version labels do not establish matching
legal identities. This inspection neither deduplicates nor joins their assertions.

Real PostgreSQL tests use only an explicitly selected disposable local test service.
`LA_TEST_POSTGRES_URL` must name `lawyer_snapshot_test` on loopback or the CI
`postgres` service, without URL query parameters. Each test creates a randomly named
child database and drops only that child. Never configure this variable with an
application database. The CI job provisions its own pinned PostgreSQL service;
normal backend test runs skip these cases when the opt-in variable is absent.
