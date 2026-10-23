# Disposable campaign issuer, identity and restore guards

This candidate provides an isolated boundary around the previous durable ledger.
It does not install application routes, native dispatch or a live identity
collector. All qualification identities and issuers are invented fixtures. The
recipe is `disposable-campaign-authority-v1`; native/legal acceptance remains open.

## Boundary declared before evaluation

Use a separately pinned private authority store outside campaign backup/restore.
The existing private SQLite storage primitive supplies owned 0700 directories,
0600 files, FULL sync, DELETE journaling, bounded locking and identity checks.
The authority keeps one-use issuer intent IDs, unique campaign grant bindings,
monotonic per-ledger restore epochs, spent packet costs and exact checkpoints.
Indexed unique grant/intent keys avoid scanning the intent history for admission.
No source text, answer text or API credentials are retained. Metadata remains
confidential and must not be published for real matters.

A trusted issuer must independently approve each exact context/action and assign
the intended request a stable one-use ID. It cannot reuse that ID with another
grant or epoch; a grant cannot move to another intent. Issuing a genuinely different
ID remains an issuer policy decision. This module does not implement production
matter permissions, cryptographic signatures, human legal review or issuer IAM.
Always-true fixture authorizers must never authorize private/native execution.

The complete runtime pin requires model ID **and immutable weight digest**, local
backend/format, model/application context limits, tenant/org/key IDs, exact route
hash, approved transport mode and disabled cloud fallback. The trusted current
observer must independently establish every field; a caller dictionary is not
proof. Missing/unknown digest, route, identity or current observation fails closed.
Compare the full pin before and after each guarded phase. Key IDs are labels, not
API keys. The existing approved laptop tunnel remains a distinct explicit mode;
generic public HTTPS is not admitted. The existing provider probe does not expose
an immutable weight digest, so it cannot supply this complete observation alone.
No live identity or model qualification follows from the synthetic pin tests.

Before any campaign write, commit the issuer reservation and exact expected
post-operation checkpoint. Only then mutate the campaign store and verify its
full resulting receipt before returning. A crash/failure between commits leaves
a consumed pending intent. Never resume, refund, auto-finalize or replay it.
Changed or rolled-back campaign receipts fail against the independent checkpoint,
even for a different still-unused packet. Unexpected direct writes cannot be
promoted as the expected result. Terminal metadata uses the same protocol; it
cannot release cost or rewrite a terminal result. Existing exact evidence/wire
seals, per-request/aggregate budgets and independent review history stay intact.

Before restoring a campaign backup, an authorized fence increments the authority's
ledger epoch. All earlier intents become unusable, even if they were unspent.
Their tombstones and consumed intent IDs remain. Fresh admission requires a new
explicitly approved intent and grant; it never resets the prior allowance.
The mechanism depends on keeping this authority current and outside the restored
snapshot. Restoring both stores or malicious host/configuration administration is
outside this guarantee. No external immutable witness/HSM is implemented here.
This qualification does not alter production backup policy or install the store.

Freeze this candidate, six fresh P1801–P1806 cases, evaluator, contracts and rules
before first grading. The mock-only bridge reserves through the authority, checks
exact selector context, invokes the unchanged synthetic selector and records its
unqualified outcome only after current-pin/checkpoint validation. Fixed select-all
responses use nominated IDs, not legal labels. Require exact source copies and
matching spent totals across reopen. Exercise changed/missing pins, identity
unavailability, issuer denial/races, one-use intent/grant IDs, restored snapshots,
epoch fencing, two actual process-crash windows, duplicate concurrent reservations,
unexpected writes, consumed failures, exact terminal metadata and metadata privacy.
Retain the first report and all failures; do not tune cases to observed outcomes.

Reproduce the complete report and contracts in read-only network-disabled Linux
using temporary scratch and public source only. Keep CI jobs, caps, workers,
coverage and five timing reserves unchanged. No real provider/key, private matter,
native inference, production state or review mutation is allowed by this experiment.
A future native boundary still needs a trustworthy live identity collector and
provider/response binding, a fresh declared acceptance trial and explicit execution
authority. Prior exposed cases and eleven-call allowance cannot be reused. The
owner's focused-analysis v3 review remains pending; prior five availability gaps,
HTTP 502 root cause, native capacity and legal qualification remain open.
