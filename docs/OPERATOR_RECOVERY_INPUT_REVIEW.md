# Reviewed operator recovery inputs

The unregistered `RecoveryInputReview` service lets an assigned operator select
one exact retained fixture context, prepare a review, obtain an independent
decision and request fresh readiness. Selection IDs come from trusted host
wiring; requests cannot supply paths, keys, profiles, packages or replacement
pins. Selection aliases remain distinct even when their underlying inputs match.

`observe` checks the original cold descriptor, six ciphertext stores, retained
keys, account/profile identity, original handoff, receipt/provenance and package
and host source. It returns private metadata hashes and the original expiry.
`prepare` requires that exact observation hash and the assigned preparer's live
session. Its review expiry cannot exceed the original handoff or session expiry.

`decide` requires the separately assigned reviewer's current session, exact
selection and review references, unchanged inputs and a bounded reason code.
Accept, changes required and reject remain separate outcomes. New records use
the existing AES-GCM receipt format in a separately pinned, independently keyed
review journal. Original stores, keys, documents and existing review histories
are never modified. Publication cannot overwrite an existing decision.

`readiness` requires an explicit decision ciphertext hash. It rechecks current
sessions, roles, original expiry, selected inputs and exact encrypted record
versions before release. Changed or expired inputs and stale review actors
withhold readiness. An authorized `inspect` retains the old decision as history;
it never produces readiness. Missing references are not replaced with a discovered
or latest decision. Revoked callers receive no review metadata.

Namespace admission uses bounded in-process and directory locks, including
separate instances. The 64-record budget reserves space for an independent
decision. Unexpected staging names block access without cleanup. A publication
whose acknowledgement is uncertain remains retained; a retry conflicts and does
not recover an acknowledgement or infer acceptance.

Readiness is limited to a disposable input handoff. It starts no listener or
controller and grants no recovery execution, trust enrollment, appointment, key
custody, external-checksum authenticity, production activation or legal approval.
There is no atomic cross-store snapshot or privileged joint-rollback guarantee.
Public package/host inputs require kernel read-only mounts by default. Only
explicit fixture wiring relaxes that policy; requests cannot change it.

Run `backend/.venv/bin/python scripts/qualify_recovery_inputs.py --output NEW.json`
for the opt-in local campaign. Its frozen 18 outcomes use three invented contexts
and six encrypted review records. They exercise real session/RBAC checks,
independent decisions, fresh-instance reads, expiry, maintenance, exact selection
and references, and trusted post-publication acknowledgement-loss injection.
The campaign checks exact original stores, keys and account database bytes. It
starts no native listener or model/provider request and makes no new native-mount
claim. The report binds 757 sources and the unchanged native cold-controller
report. The owner's focused-analysis-v3 review remains pending.
