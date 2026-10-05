# CI runtime and cost controls

GitHub Actions runs the complete backend suite once per PR update and once for a
push to `main`. Feature-branch pushes do not start a second copy of the same PR
checks. Manual runs remain available. The existing concurrency group cancels an
older run for the same PR or branch; separate PRs retain separate checks.

Backend tests use **two pytest-xdist workers inside one runner**, grouped by file:

```sh
uv sync --project backend --frozen --extra dev
backend/.venv/bin/pytest backend/tests -n 2 --dist loadfile --max-worker-restart=0 --durations=30
```

This retains the complete suite and its real SHACL, cryptographic, authorization
and publication checks. There are no selective test skips, mocked validation
shortcuts, extra matrix runners or automatic worker-crash retries. Fixtures use
separate temporary directories, and network-server fixtures allocate ephemeral
ports. PostgreSQL concurrency tests remain in their separate serial job with an
explicit disposable database; they skip in the normal backend job.

The backend job has a **30-minute hard limit**; frontend and PostgreSQL jobs each
have a **five-minute limit**. Exceeding a limit fails/cancels the check rather than
marking partial work successful. Lint, backend tests and deployment tests are
separate steps. The test log prints the 30 slowest setup/call/teardown durations
to guide future optimization. Required job names are unchanged.

## Evidence and measurement boundary

On 5 October 2026, completed [run 37283288461](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37283288461)
reported **1,971 tests in 2,101.48 seconds (35m01s)**. Dependency installation
took only four seconds. Both `push` and `pull_request` independently executed
the suite for the same revision. Removing that duplication removes one complete
automatic workflow run per PR revision; it does not remove post-merge verification.

A local profile of two graph tests found repeated SHACL/RDFS/SPARQL work dominated
execution. Those validations and ontology fingerprints are unchanged. File-level
timestamps in the old GitHub log are buffered and do not reliably measure individual
test files; use pytest's duration report instead. Dependency caching is not the
current bottleneck and no additional cache infrastructure was added.

The complete R02 backend collection passed locally with the exact two-worker
command: **2,058 passed, eight PostgreSQL cases skipped, 28 existing deprecation
warnings in 336.83 seconds (5m36s)**. The PostgreSQL cases remain mandatory in their
dedicated CI job. `actionlint`, project-wide Ruff, frozen offline dependency sync
and lockfile inspection passed; the only added packages are the development-only
`pytest-xdist` and `execnet`, with all existing versions retained. Local evidence
is in `.data/verification/ci-parallel-full.log` and `ci-old-run.{json,log}`.

Compare the first completed two-worker hosted run with the above baseline before
claiming a hosted speedup or currency savings. Local wall time is not a hosted
runner benchmark, and elapsed runner minutes are not an invoice. Existing runs
use the workflow with which they started; changing the file does not retroactively
change their worker count or timeout.

References: [GitHub triggers and timeouts](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[pytest-xdist worker distribution](https://pytest-xdist.readthedocs.io/en/stable/distribution.html).
