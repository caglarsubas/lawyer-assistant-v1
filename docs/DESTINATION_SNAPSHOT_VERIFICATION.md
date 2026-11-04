# Read-only destination snapshot verification

`DestinationVerifier` is unregistered trusted local wiring for disposable
operator identities. It verifies one explicit metadata snapshot against an
independently pinned receiver context and fresh source observations. No matter,
portfolio, provider or recovery route is activated by this component.

The host supplies the exact source reference, original `DestinationPin`, fixed
destination selection and a server-held source session. Requests cannot supply
source credentials, replace pins, choose a latest review or provision a target.
Source and destination account databases, private namespaces and encryption keys
must be independent. Repeated logical fixture labels do not merge their account
namespaces or sessions. Common public host code is permitted.

The receiver authenticates its currently assigned reviewer, including cookie,
Origin, CSRF and current RBAC checks, before reading a packet or either snapshot.
The closed packet contains only the original source handoff fields. Every field,
full reference and explicitly present decision acknowledgement must match. A hash
alone never authenticates an actor or establishes source or destination authority.

Under the existing bounded receiver admission lock, verify the current local
selection, account/database identity, package/source versions and journal
snapshot. Twice revalidate the exact source handoff using the separately held
source session. Reobserve local inputs and journal around those source reads;
changed observations, revoked actors, unavailable checks, malformed inputs,
tampering and exhausted checked execution budgets return no partial metadata.
The execution budget is ten seconds checked between bounded operations, in
addition to the original two-second lock admission bound.

The result binds the original handoff hash, exact reference, receiver context,
current receiver session commitment and observed local inputs. Its expiry is
the earliest original handoff, receiver-session or local-input expiry. Preserve
the original handoff expiry separately; a new receiver instance or fresh read
cannot extend it. Reusing a result still requires fresh authorization and
verification. Missing acknowledgements, negative decisions and stale versions
remain unchanged history, never a substitute current approval.

Unexpected staging blocks the read and remains untouched. Unregistered journal
records participate only in snapshot comparison; they are not decrypted,
advertised or adopted. The service writes nothing and has no publication,
repair, restore, acknowledgement-recovery, listener or trust-renewal operation.
Source credentials and actor/session records are never returned. Verification
metadata remains private to its authorized operator context.

Matching independently supplied pins does not establish their genuine origin,
physical mount posture, external channel authenticity or key custody. This
slice is not native deployment or production/legal qualification. Cross-store
atomicity and privileged joint rollback remain unqualified. Every original
capability flag remains false, including handoff/execution readiness.

The opt-in `qualify_destination_snapshot.py --output NEW.json` campaign freezes
24 outcomes across three disposable source/receiver pairs and six isolated
account contexts. It retains six original input-review ciphertexts and two
declared injected entries, verifies unchanged original inputs, accounts and
review history, and binds 770 source files plus the preceding inventory report.
Twenty-five focused tests also exercise credential separation, fresh revocation,
database failure, exact versions, races and original expiry. Read-only cases
share a disposable pair per worker, with a whole-source/account/history byte
check around each test. Mutating cases retain fresh isolated pairs. Every
business assertion and case identity from the initial fresh-pair run remains.

The first PR run passed all 13 checks but retained only 16 seconds in backend,
below its fixed 30-second floor. Retain that rejection. Its new test file used
104.60 worker-seconds, including 84.18 seconds of repeated setup. Correct that
setup and move the complete file into existing analysis capacity: analysis
becomes 160 plus its unchanged frozen 53-case pair; backend returns to 3788
collected, 3691 passes and 97 original skips. The placement guard requires the
new file exactly once. Keep the 13-job, 73-minute CI ceiling, two workers, all
older case identities and business assertions, placement manifests, deadlines
and reserve floors unchanged. Fresh PR and independent-main evidence still
gate delivery; local timings or a green run alone do not establish headroom.

The owner's focused-analysis-v3 legal review remains pending. The next slice is
read-only retention/re-observation readiness for explicit receiver verification
references, without treating retained bytes as acknowledgement or renewed trust.
