# Retention reconciliation operating and qualification plan

**Draft for operator review, 7 November 2026.**

This packet prepares a reviewed transition from the disposable campaign to a
selected deployment. Record the deployment, accountable people and their
decisions in a private copy of the review record below.

## Current evidence and prerequisites

The [staged report](evidence/staged-recipient-reconciliation-2026-11-06.json)
records ten outcomes, two interrupted writer processes and 793 source hashes.
Its inputs are invented. The
[adapter](../scripts/recipient_receipt_retention.py) verifies current source and
review context before returning the selected receipt's observation.

The predecessor authority accepts disposable SQLite identity profiles. The
recipient adapter has no registered production route or genuine identity
provisioning command. Production integration requires a separately reviewed
host authority and wiring implementation. The gates below identify the
evidence required before that implementation can be approved for operation.

The [isolated host admission gate](HOST_RECONCILIATION_AUTHORITY.md) now checks
real application sessions and version-bound authorization with invented inputs.
It remains unregistered, performs no receipt IO and supplies no bridge into the
disposable planners. The genuine trusted resolver and operational wiring remain
outstanding.

| Gate | Required evidence in the private review packet | Current state |
|---|---|---|
| Deployment and scope | Exact revision, host identity, selected record and approved purpose | Awaiting selection |
| Accountable people | Named deployment operator, independent technical reviewer and key custodian | Awaiting appointment |
| Host integration | Reviewed authentication, origin/CSRF, RBAC, scope and session-revocation behavior | Implementation and qualification required |
| Trust and custody | Independently confirmed public fingerprints, key roles, contexts, validity and revocation | Genuine provisioning required |
| Retention permission | Exact independently signed permission and accepted recipient review | Genuine authorization required |
| Recovery checkpoint | Verified encrypted backup and separately controlled key-recovery evidence | Deployment-specific drill required |
| Operating limits | Measured time, concurrency, cancellation and failure behavior on the selected host | Deployment-specific qualification required |
| Deployment decision | Attributed reviewer decision over the exact evidence packet and revision | Pending |

Source rights, lawful retention and the owner's private analysis review remain
separate recorded decisions. Associate each assessment with its exact version.

## Responsibilities and trusted inputs

The deployment operator assembles the packet and records observations. The
technical reviewer checks the exact packet and records acceptance, requested
changes or rejection. The key custodian supplies independently verified custody evidence.
Record actual people and authority, alongside the software principal IDs.

The existing adapter requires distinct issuer and custodian keys and principals,
separate from the predecessor review principals. The current independent
recipient reviewer must still match the accepted signed review and session.
Appointments must satisfy those identity constraints. Signing a fixture result
cannot supply a genuine appointment or custody confirmation.

| Trusted host input | Required binding |
|---|---|
| Recipient observation | Exact source receipt, specification, signed review-set hashes and current authorization context |
| Receipt store | Separate owner-controlled directory and encryption key, directory identity and scope hash |
| Permission | Record ID, receipt ID, predecessor plan hash, store hash, issue/expiry times and both signatures |
| Public keys | Independently obtained fingerprints, roles, principals, profiles, contexts, validity and revocation state |
| Reopen pin | Exact ciphertext digest, permission-bound custody signature and validity window |
| Reconciliation pin | Selected staging ID, expected pair state, ciphertext digest where present, signature and validity window |

Provision these inputs through the reviewed host boundary. The reconciliation
request contains only the opaque record ID. Paths, keys, pins, decisions and
credentials belong to trusted wiring.

## Prepare the review packet

1. Select the deployment revision and record its source and package hashes.
   Check the staged report against that revision. Record changes since the
   qualified source, and identify the regression evidence for those changes.
2. Record the selected host, account contexts, reviewer appointments, storage
   ownership, filesystem and approved record scope in the private packet.
3. Obtain independent fingerprint confirmation and custody records through the
   approved channel. Keep encryption-key recovery separate from the encrypted
   checkpoint and scope access to the appointed recipients.
4. Inspect the current receipt, accepted review, signed permission and expiry.
   Record unresolved facts and missing evidence as open gates.
5. Verify a backup and restored copy in an isolated environment. Compare original
   ciphertext, exact evidence versions and review history. Record the actual
   restore scope and measured recovery behavior.
6. Obtain a technical decision over the exact packet before deployment-specific
   execution. A changed revision, identity, permission, key, source version or
   operating limit requires a new attributed assessment.

Keep raw documents, selected filenames, account identifiers, signatures and
diagnostics in authorized private storage. A public roadmap entry may record
the gate status and a non-sensitive evidence reference.

## Reproduce the disposable evidence

Use the repository backend environment. Both commands below are available
today. The posture command returns an allowlisted projection of service health
and configuration posture. It establishes a runtime observation.

```sh
backend/.venv/bin/python scripts/runtime_diagnostics.py --project lawyer-assistant-v1
umask 077
receipt_dir="$(mktemp -d)"
backend/.venv/bin/python scripts/qualify_recipient_reconciliation.py \
  --output "$receipt_dir/qualification.json"
```

The campaign creates fresh disposable identities and stores under temporary
storage. Its output must be a new file in an owner-only directory. Retain the
report, exact revision and comparison with the frozen report privately.
Report a failed or incomplete campaign with its attempted revision.

## Qualify the deployment integration

Run these cases on a reviewed isolated copy before approving a production
operation. The executor must use the reviewed host integration. That integration
is an outstanding deliverable identified in the first table.

| Qualification | Expected result and retained evidence |
|---|---|
| Current authorization | Authenticate before lookup. Wrong role, expired/revoked session or changed permission withholds metadata |
| Exact retained record | Authenticated plaintext matches the original receipt and permission. Tampering or another store's ciphertext is withheld |
| Absent selected pair | Both selected names are absent. The observation applies only to that pair |
| Staged-only file | Owner-only regular ciphertext has one link and the exact signed digest |
| Final-only file | The final ciphertext has one link and the exact signed digest |
| Linked pair | Both selected names identify the same inode with exactly two links and the exact signed digest |
| Invalid namespace | Symlinks, extra hard links, incompatible modes, sizes or directory identity are withheld |
| Fresh custody | The reconciliation pin is signed over the permission and selected state, lasts at most 60 seconds and expires within the permission |
| Change during a read | Changes to the selected pair, source, review, session or registry withhold the result |
| Interruption and restart | Preserve the interrupted state, reconstruct the reader and obtain fresh applicable authorization before re-observation |
| Capacity and cancellation | Exercise the declared concurrency and cancellation limits. Record completion, withheld results, elapsed times and preserved files |
| Preservation | Compare originals, ciphertext, exact evidence versions, review records and audit history before and after every operation |

Preserve the adapter's 16-second checked operation budget and the predecessor's
10-second checked budget and two-second admission limit during qualification.
Record actual behavior under load. Define the production operating limit from
the results and its independent review.

The existing adapter returns identifiers, digests, expiry and the observed
state. Its authority flags remain false. A deployment approval needs the
separate evidence and attributed decision described above.

## Handle outcomes

| Outcome | Operator response |
|---|---|
| Reconciled | Retain the exact observation and expiry alongside its reviewed inputs |
| Denied, unverifiable or budget exhausted | Preserve the attempt and state, investigate the failed prerequisite and obtain a fresh assessment |
| Retention conflict | Preserve the first ciphertext and independently inspect the selected record |
| Retention uncertain | Preserve both names and the attempted publication evidence. Perform an authorized read-only reconciliation before considering another write |
| Expired observation | Obtain a fresh custody observation within the original permission window |
| Requested changes or rejection | Retain the decision and prepare a separately versioned packet if work continues |

Reconciliation leaves selected files in place. Cleanup, relinking, repair,
rollback, key rotation and another retention write each require their own
reviewed action and authorization.

## Private review record

Use a private copy of this template. The schema identifies a review worksheet.
The application does not load it as configuration.

```json
{
  "schema": "retention-reconciliation-operating-review-v1",
  "revision": null,
  "deployment_evidence_ref": null,
  "operator_appointment_ref": null,
  "technical_reviewer_appointment_ref": null,
  "custodian_appointment_ref": null,
  "integration_review_ref": null,
  "fingerprint_confirmation_ref": null,
  "permission_and_recipient_review_ref": null,
  "encrypted_checkpoint_and_restore_ref": null,
  "staged_report_ref": null,
  "deployment_qualification_ref": null,
  "preservation_comparison_ref": null,
  "operating_limits_ref": null,
  "open_gates": ["appointments", "host_integration", "genuine_provisioning", "deployment_qualification"],
  "decision": "pending",
  "reason": null,
  "reviewed_by": null,
  "reviewed_at": null
}
```

Complete the references with evidence the reviewer can inspect. Attribute
acceptance, requested changes or rejection to the appointed reviewer. Retain
each original packet, its decision and any successor as separate versions.
