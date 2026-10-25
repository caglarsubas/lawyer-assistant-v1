# Frozen campaign discovery and CI headroom

The main-branch repeat after PR #226 exceeded the frontend job's existing five-minute budget. Its Vitest worker passed all 70 assigned files and 5,299 tests in 248.17 seconds; the concurrent deployment worker was still running the 26-case archive method when GitHub cancelled the job. Eight other jobs succeeded. Successful PR CI and identical merged-main trees do not make that cancelled repeat successful.

The scheduling unit was the cause of the deployment tail. A whole inventory campaign was forced to ARM and a whole archive campaign to x86. The scheduler could neither distribute their individual cases nor report which case was still running.

`ci_case_discovery.install` now registers each of the frozen 20 inventory and 26 archive cases as a distinct asynchronous unittest method. Every method retains its exact fixture ID, expected outcome, body, integrity checks and cleanup. Each case gets an isolated event loop and fixture lifecycle. Duplicate, malformed or colliding identities are rejected before class mutation. The frozen case lists, policies, native reports and report graders remain unchanged.

The complete, committed deployment manifest must equal fresh discovery. Both existing sequential deployment workers use stable test-ID hash partitioning. The two old campaign-specific placement overrides are removed. Manifest contracts require each frozen case exactly once and require both campaigns to span both lanes. The 46 case methods replace two campaign methods; two new helper contracts bring the total from 630 to 676. This is a change in test granularity, not 46 new product capabilities.

Each worker emits a public test ID at start and its elapsed seconds at completion. The final report retains every executed ID and per-case duration. If a job is interrupted, the partial log identifies its last admitted case without dumping configuration, credentials, source text or private evidence.

The nine jobs, two workers per frontend lane, runner architectures, one frontend production build, 139 frontend files, 10,532 frontend tests, job and step caps, external-network policy and retry policy remain unchanged. There is no new runner or automatic rerun. Unit scratch remains separate from native durability qualification.

Acceptance requires complete/disjoint manifest execution, all nine checks on the exact proposed head, and at least 30 seconds of reserve for frontend, frontend-history, backend job, backend test step and graph-runtime job. Merge uses the tested head as a lease; independently fetched main must have the same full tree. Record PR CI, cancelled historical repeats and new main-push CI separately.

The independently authorized staged-reader binding and withdrawal-fence cutover remains the next product slice. This prerequisite creates no binding, enrollment, provider call, inference, deployment or legal-review decision.
