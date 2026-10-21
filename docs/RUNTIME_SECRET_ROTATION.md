# Runtime secret isolation and recovery

Resolved environment/configuration inspection can disclose passwords, bearer
tokens and encryption keys. The remedy is containment plus rotation, not a claim
that previously printed values can be erased from an existing transcript.

## Prevent a repeat

Compose grants explicit secret files to each service. The API receives its database
URL, encryption key, bootstrap password, extractor token, gateway token and provider
key; the extractor receives only its token; PostgreSQL receives only its bootstrap
database password. Optional publisher and gateway grants remain narrower. The web,
scanner, graph and search services receive none of these files. No new network,
provider-administration route or cloud fallback is enabled.

Settings and the isolated extractor read `*_FILE` directly without exporting values
into environment variables. Missing, nonregular, symlinked, oversized, writable or
invalid files fail with fixed diagnostics. Literal-plus-file ambiguity fails
without a Pydantic input-value dump. Secret-valued Settings fields are excluded from
`repr`, `model_dump` and JSON serialization. Legacy literal settings remain supported
for explicit synthetic fixtures; they are not the normal Compose deployment.

Use `scripts/runtime_diagnostics.py` for an allowlisted posture report and
`docker compose config --quiet` for validation. Never print raw inspection,
resolved configuration, `.env`, private receipts, exceptions with captured output,
or secret files. Repository [operator instructions](../AGENTS.md) enforce the same
handling boundary for agents. Docker/root administrators still have privileged
access; file mounts do not establish protection from a compromised host.

For a **new, empty vault only**, create a new owner-only directory using:

```sh
backend/.venv/bin/python scripts/provision_runtime_secrets.py .data/runtime-secrets/active
```

The command emits no values. Set `LA_SECRET_DIRECTORY` to that directory, supply
the bootstrap username and place the user-managed provider key in `provider_api_key`.
An empty provider file leaves inference unconfigured. Preserve the original key
and verify an encrypted backup before any change to an existing vault. On Linux,
qualify host ownership and runtime-UID readability of each 0600 file; never solve
a permission failure by making a secret world-readable. Compose file-backed
secret ownership behavior is platform dependent.

## Rotate an existing private-record deployment

1. Record a private inventory with safe output. Identify exposed values internally,
   actual credential consumers and any source-history/ciphertext bindings. Do not
   infer that editing a bootstrap value changes an existing account or database role.
2. Close admission and stop the API and every writer. Verify zero active research
   jobs and an unchanged frozen inventory. Authenticate a complete encrypted cold
   backup and an encrypted recovery bundle containing the old configuration/keys.
   Retired keys must remain available only for controlled historical recovery.
3. Generate a **new immutable secret generation** in a new private directory.
   Preserve unrelated provider credentials/identity. Never overwrite mounted key
   files beneath a running process or copy values into CLI arguments or logs.
4. Rehearse the operation on an isolated restore. Run `scripts/rotate_private_key.py`
   offline with protected database-URL and old/new-key files. The CLI requires
   explicit stopped-writer and authenticated-backup prerequisites. These flags
   record operator assertions; they do not independently prove those conditions.
5. The qualified migration profile permits existing nonempty `records` plus
   bounded flat encrypted originals. It refuses other populated encrypted ledgers:
   some source-selection snapshots bind ciphertext digests. Those deployments
   need an independently qualified compatibility/migration plan first.
6. Rotation preserves exact decrypted payload bytes, original document bytes,
   IDs, revisions, audit/review rows and Fernet timestamps. All active ciphertext
   must decrypt using the new key and reject the old key. The API never retains a
   fallback decryption key. Ciphertext bytes necessarily change; no evidence
   re-extraction, legal finding or human review is created by maintenance.
7. A new-key-encrypted journal binds old/new row state and staged original hashes.
   Before-commit exceptions restore originals and roll back the database. After an
   ambiguous commit or abrupt exit, keep writers stopped and use `recover`; it
   chooses rollback/forward from exact committed rows, validates all inputs before
   any replacement, and refuses unknown/tampered state. Startup and review reads
   are blocked while the maintenance marker remains. Missing/corrupt journals or
   an interrupted final cleanup require controlled backup recovery or a separately
   verified completion; never delete a marker merely to force startup.
8. Rotate the PostgreSQL role through an existing authenticated administrative
   connection using a precomputed SCRAM verifier; do not put clear passwords in
   SQL/logs. Verify a fresh connection with the new password and rejection of the
   old password. `POSTGRES_PASSWORD_FILE` alone cannot change an existing role.
9. If the exposed bootstrap value matches an actual login hash, replace that
   account's password hash and revoke its sessions, preserving identity, permissions
   and review history. Otherwise preserve the unexposed account password. Record
   a separate security audit event; never manufacture or overwrite a legal review.
10. Install matching API/extractor images and file-only credential configuration,
    recreate PostgreSQL to remove old literal environment values, and preserve
    volumes, network boundaries and pinned service addresses. Verify new/old
    authentication, scanner/extractor readiness, source/plaintext manifests, all
    review metadata and the complete old audit-row subset. Preserve prior failed
    or unadopted analyses. Prepare and authenticate a new-key recovery backup.
11. Encrypt and retire old secret-bearing diagnostic/configuration copies with an
    authenticated recovery archive. Preserve their original bytes there and leave
    explicit retirement receipts. Do not edit originals, application evidence or
    review artifacts to redact infrastructure credentials. Current startup must
    not reference retired credentials. This does not prove physical SSD erasure
    or undo prior disclosure.

Old prepared packets and recovery archives remain historical. A changed preparation
MAC key cannot silently reauthorize an old packet; rebuild/review against the
current deployment or inspect the retired snapshot in controlled recovery. Signed
publication authority and legal qualification remain separate gates.

Engineering tests use invented data, including abrupt subprocess exit, pre-commit
rollback, post-commit recovery, tampering, original-byte preservation, immutable
review metadata, file scope and fixed diagnostics. They do not qualify every
storage profile, HA/multiwriter rotation, backup-retention policy or production
key-management system. See [engineering evidence](evidence/runtime-secret-isolation-2026-10-21.json).

Primary contracts: [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/),
[Fernet rotation](https://cryptography.io/en/45.0.5/fernet/),
[PostgreSQL ALTER ROLE](https://www.postgresql.org/docs/16/sql-alterrole.html).
