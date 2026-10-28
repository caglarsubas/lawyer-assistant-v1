# Single-build placement and backend reserve

PR #241 passed exact-head qualification. Its merged main run 40652152012
completed all ten jobs successfully, but the backend job used 1,179 of 1,200
seconds. Its 21-second reserve fails the unchanged 30-second release gate.
The 840-second backend test step and all internal contract phases met their
own reserve requirements. Functional CI success is not full qualification.

Move the single `npm run build` from the backend job to the frontend job,
after locked dependency installation and before Vitest. The observed ARM build
took 27 seconds; the main frontend job retained 112 seconds. These measurements
justify the candidate placement, not a guarantee about future x86 runtime.
Keep backend Node/dependency preparation for existing contract checks.

The first placement candidate passed the frontend job with only 34 seconds of
reserve. Contract work no longer shares that job, so use its existing two-worker
budget for two isolated Vitest workers instead of leaving one slot idle. The
history job retains one Vitest worker plus one contract worker. This restores
use of the existing per-job ceiling, with no extra executor, retry, test command
or longer deadline.
The complete build still runs once. Preserve x86 frontend coverage, both isolated
frontend shards, all 139 files/10,532 cases, all backend groups, the 1,018-method
manifest and assignments 418/425/90/23/17/26/19. Update the existing placement
contract without changing the method inventory.

Require fresh exact-head and independent-main CI and actual execution receipts.
Every job and the backend test step must retain at least 30 seconds; existing
short-phase floors remain. No near-deadline green run substitutes for this gate.
Keep PR #241's records as historical evidence of its distinct functional and
qualification states. No application, private runtime, source evidence or review
history is changed by this CI-only follow-up.
