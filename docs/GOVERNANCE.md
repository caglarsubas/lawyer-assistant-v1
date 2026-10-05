# Matter lifecycle and dependency governance

The governance API records operator decisions and makes archiving reversible. It does not certify a retention policy as legally sufficient and cannot physically erase stored files, backups or exported copies. No timer expires a hold, deletes a record, or archives a matter.

## Access and transactional boundaries

Every matter operation requires an active account, matching firm and explicit matter membership. Administrator status never bypasses membership. Hold creation/release, retention changes, erasure planning, archiving, restoration and dependency invalidation additionally require `admin`. Members can inspect active-matter governance and plan dependency impacts. Only administrators with membership can inspect an archived matter's detailed governance; the archived list shows each caller's own memberships, including lawyer accounts, with `can_restore` indicating authority.

All mutations use existing session authentication, CSRF and origin checks. Governance rechecks the current account and membership inside its transaction. Mutations lock the matter row on PostgreSQL and increment its optimistic revision; conflicting writes fail rather than silently overwriting another revision. Product changes also use the existing optimistic version check. SQLite is a demo environment, not a production concurrency qualification.

A successful lifecycle mutation commits its encrypted ledger records, corresponding `Audit` event and state change atomically. Each governance event includes the actor, time, matter, reason or linked decision record, and the previous event's digest. This detects a broken chain when compared with trusted records; it is **not** an externally anchored, tamper-proof audit system. Authentication/authorization failures are rejected before creating a matter ledger event. Existing authentication logging remains separate. Dry-run plans add an audit entry but do not alter source records, product contents or lifecycle state.

## API

All paths start with `/api/v1`. Bodies reject unknown fields and bound free-text and identifier lengths.

| Method and path | Behavior |
| --- | --- |
| `GET /matters/{id}/governance` | Current revision, effective holds, original holds and releases, current policy and history, archive/restore history, event ledger and remaining external gates. |
| `POST /matters/{id}/legal-holds` | Create a hold with `reason` and `authority_reference`. No expiry field is accepted. |
| `POST /matters/{id}/legal-holds/{hold_id}/release` | Append a release decision with `reason` and `authority_reference`. The original hold stays unchanged. A second release returns 409. |
| `PUT /matters/{id}/retention-policy` | Append a policy version linked to its predecessor. Requires `reason` and `policy_reference`; accepts nullable `retention_days`, `trigger`, `review_due_at` and `qualification_reference`. |
| `POST /matters/{id}/erasure-plan` | Inventory the matter, child records, original-file references, products and declared dependencies. Return an inventory digest and blockers; no erasure occurs. |
| `POST /matters/{id}/archive` | Require `reason` and current `expected_revision`. Reject an active hold or outdated revision. Create a tombstone and change only the matter kind to `archived_matter`; cancel queued/running research. |
| `GET /governance/archived-matters` | List only the caller's archived memberships; no organization-wide counts. |
| `POST /governance/archived-matters/{id}/restore` | Require `reason`, current `expected_revision`, admin, membership, firm match, archived kind and an existing tombstone. Restore normal access; do not restart cancelled jobs. |
| `POST /matters/{id}/dependencies/impact` | Plan exact dependency matches with `reason` and `changes`; return affected products without changing them. |
| `POST /matters/{id}/dependencies/invalidate` | Apply the same match rules; mark matching products stale and append an audit event. |
| `POST /governance/releases/impact` | Plan an exact `old_release_id` → `new_release_id` change for the administrator's accessible matters. |
| `POST /governance/releases/invalidate` | Apply that exact change to matching products in accessible active or archived matters. Does not install or activate the new release. |

A retention policy defaults to indefinite preservation/manual review (`retention_days: null`), with automatic expiry and erasure disabled. Supported triggers are `manual_review`, `matter_closed` and `last_activity`; these are recorded policy attributes, not scheduler commands. Even an elapsed review date or duration cannot authorize deletion. Operator-supplied qualification references are retained as references only: status remains `operator_recorded_unqualified` until a separate qualified process exists.

Archiving keeps the encrypted matter payload, originals, facts, products, memberships and all governance records. Existing normal matter, document, research and product endpoints deny the archived kind. Restoration retains its tombstones and history. A hold discovered during an archive can be imposed by an authorized administrator; restoration is still possible for preservation/inspection, while another archive is blocked. There is no purge endpoint, including for unheld matters.

## Dependency matching and reviewed products

A `changes` item has `kind` (`source`, `assertion` or `release`), exact `old_id`, and optional different `new_id`. At most 100 changes are accepted. An absent new source/assertion ID can describe withdrawal; the release operation always requires two different nonempty identifiers.

The implementation reads declared provenance from `snapshots`, `evidence`, `graph_paths`, `authority_candidates` and `dependencies`:

- Source identifiers: snapshot source keys; private practice record and version IDs; document, artifact, passage, evidence and text-representation identifiers and explicitly named content hashes.
- Assertion identifiers: graph edge IDs and explicitly named assertion IDs/maps.
- Release identifiers: explicit corpus/graph/release IDs and bundle hashes; snapshot ontology, model and policy identifiers; ontology hashes inside graph snapshots.

Matching is equality within the requested type. Free-text titles, summaries, claims and quoted text are not searched for identifiers. A no-match result means **no declared matching dependency was found**; it does not establish that every possible semantic dependency is known. Products made before provenance recording, external copies and undeclared dependencies require separate review. The first implementation derives the dependency index from encrypted product records at request time; it is not a separately persisted global graph.

Invalidation updates only `status`, `stale_reason` and `stale_event_id`. Claims, quotations, evidence, original snapshots, product versions and historical review decisions remain unchanged. The event preserves prior product status/revision and the exact old/new dependency identifiers. A reviewed product becomes stale and needs a new preparation/review cycle; the previous review is neither erased nor represented as approval of the changed source. No legal review is fabricated.

Release impact/invalidation operates only on current caller memberships, including archived matters so restoration cannot conceal a known source change. Responses contain only affected accessible matters and products. Other matters are not counted, reported, audited or changed. Each affected matter records its own event. The operation has no network or third-party effects and never rewrites the stored release snapshots to pretend that a new release was used.

## Erasure inventory and outstanding operational gates

The erasure plan includes record IDs/kinds, per-kind counts, product dependencies, active hold IDs, the effective retention policy and an inventory SHA-256. Original references are checked only inside the configured document directory; filesystem paths are not returned. `present` is a file-presence observation, not a cryptographic verification of the original. Missing references, unavailable originals and unsafe references are distinguished. `purge_allowed` and `physical_erasure_available` always remain false.

Production retention qualification still requires: a legally approved schedule and authority review, legal-hold operating procedures, deployment-specific inventory of backups/replicas/caches, controlled disposal with evidence, export/copy handling, externally anchored audit retention, and backup/restore acceptance. Those external gates remain open. This module provides the decision ledger and reversible application lifecycle; it does not claim that backup deletion, statutory compliance or forensic erasure has occurred.

Validation: `cd backend && .venv/bin/python -m pytest tests/test_governance.py -q`. Tests use clearly synthetic records and check holds, authorization, immutable policy history, no expiry, retained original bytes, cancelled research, restored access, exact dependency matching, metadata-only staleness, scoped release invalidation and audit linkage.
