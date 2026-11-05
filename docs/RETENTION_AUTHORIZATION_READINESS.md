# Independent retention-review and provenance readiness

This unregistered, read-only adapter checks independently reviewed metadata for
one exact retained verification reference. It accepts only disposable SQLite
identity profiles; production accounts and matter stores are refused by the
underlying authority. It grants readiness for **disposable metadata planning**.
`retention_authorized`, genuine acknowledgement, durability, custody, trust
renewal, production activation and legal qualification remain false.

Trusted host wiring supplies the verifier, a distinct owner-only proof directory,
independent directory/context pins, three distinct public keys/principals and up
to four explicitly versioned proof sets. Requests contain only an entry ID and
the exact proof-set hash. They cannot supply keys, paths, credentials or review
decisions. There is no signing, key-generation, registration, retention, restore
or activation API.

Each proof set contains three detached Ed25519 envelopes with distinct purposes:

1. Issuer provenance pins the encrypted record, plaintext hash, original
   acknowledgement pin, plan and issuer context. Custody and durability are
   explicitly unqualified.
2. A preparer signs the exact provenance-file hash, plan, reference and assigned
   reviewer, including the current disposable preparer session.
3. A distinct reviewer signs the exact proposal-file hash, current reviewer
   session and a closed accept/changes-required/reject decision and reason.

All envelopes bind the same proof ID, private directory identity, target profile,
note-store context and reference. Signatures use domain separation. Host pins
bind key roles, principals, profiles, contexts, validity windows and revocation.
File hashes and a strict schema preserve exact versions. Another valid signature
or later version cannot replace what was reviewed. Distinct disposable account
IDs do not prove independent human identities or genuine key ownership.

Authenticate the assigned reviewer before registry lookup, inventory or parsing.
Validate signatures and current preparer/reviewer authority first; negative
reviews grant no readiness and trigger no encrypted-source reads. Accepted
records require two fresh exact source/destination re-observations, current
sessions, stable registries, exact proof bytes and unchanged bounded inventories.
Ten-second checked aggregate and two-second admission budgets fail closed.
Staging, links, broad permissions, oversized inputs, races and unavailable checks
withhold all result metadata, preserving unexpected bytes without repair.

The result contains only pinned hashes and validity limits. Its expiry cannot
exceed the original handoff, current verification or signed review/key windows.
Reopening does not extend a window, rewrite a decision or renew authority.
Independent stores are observed sequentially; atomicity and joint rollback are
not qualified.

The opt-in frozen campaign qualifies 20 outcomes using two pairs/four isolated
account contexts, two encrypted verification records, six proof sets/18 exact
signed envelopes and 12 invented signing keys. Two declared fixture-only session
revocations and one namespace injection are retained. Four original input-review
records and source/review bytes remain exact. Fourteen measured service reads
write nothing. The report binds 781 source files, all 777 predecessor pins and
the preceding report hash. No real keys or case documents enter the campaign.

```sh
backend/.venv/bin/python scripts/qualify_retention_authorization.py --output /private/new-report.json
```

Use an owner-only output location whose file does not yet exist. Failure records
only an incomplete status/error type. Fixture-only publication/signing happens
outside the application service and never establishes production custody.

Thirteen ordinary regression cases use existing backend reserve. Retain the
initial CI rejection: the final-release tests passed but the job retained only
12 seconds against the fixed 30-second floor. The supervisor stopped backend
early. The preceding 31-second baseline was too close to the floor.

Move complete adjudication39 and effort31 files plus the unchanged preview-final
slice7 to backend. Move the unchanged materialization-final slice20 to portfolio
review. Backend has 3927 selected cases: 3830 passes and 97 original skips;
final-release has 13, and portfolio has 47. Closed manifests remain byte-exact,
with all 20 preview, 58 materialization and 19 cohort identities executing once.
Logical slice names and their contents are retained; only their hosting jobs
change. Placement assertions require the new assignments explicitly.

Preserve all older source bytes, cases, 13 jobs, the 73-minute aggregate cap, two
workers, deadlines, supervisor and reserve floors. Hosted exact-head and
independent-main execution/reserve/preservation qualification gate closure.

Next: explicit metadata-handoff packaging and read-only destination acceptance,
binding reviewed proof/reference versions and requiring fresh destination
authorization. Genuine issuer enrollment, signing custody, acknowledgement-channel
authenticity, durable retention and the owner's legal review remain separate gates.
