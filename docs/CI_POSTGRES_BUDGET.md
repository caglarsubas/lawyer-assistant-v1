# PostgreSQL concurrency CI budget

PR95's first submitted head passed all 95 PostgreSQL/runtime cases in 267.02
seconds, but its job exceeded the unchanged five-minute limit and was cancelled.
The job took 304 reported seconds including image/service setup and cleanup.
A passing test step is not a passing check; this run did not authorize merging.

The service repeatedly creates and drops isolated child databases. Hosted logs
show forced checkpoints throughout the run. Its existing runner-disk storage and
late expensive concurrency groups left insufficient room for lifecycle work.

The disposable CI PostgreSQL service now mounts its data directory on bounded
512 MiB temporary memory storage. PostgreSQL, WAL, fsync, full-page writes,
synchronous commits, transaction isolation and the actual in-test row-lock races
remain real. The job explicitly asserts the three durability settings are on
before running the suite. This configuration qualifies concurrency and
live-authorization behavior; it is not a crash-durability or disk-recovery test.
Application deployments and their persistent volumes are unchanged.

Start runtime authorization, set authorization and declared assembly before the
other PostgreSQL groups, reducing a possible late worker tail. All original
files and all 95 cases still run exactly once in this job. Health probes use a
one-second interval with thirty attempts, avoiding an unnecessary ready-service
polling delay while preserving the bounded readiness check.

Controlled local Linux measurements used the same pinned PostgreSQL image,
unchanged application image, current tests mounted read-only and two CPU shares/
pytest workers. Each used a fresh owned internal network and database:

| Complete 95-case configuration | Elapsed seconds | Result |
|---|---:|---|
| Original disk storage/order | 99.09 | All passed |
| Temporary storage, original order | 94.88 | All passed |
| Temporary storage, long groups first | 91.52 | All passed |

Every configuration verified `fsync=on`, `full_page_writes=on` and
`synchronous_commit=on`. Local timing is not a hosted guarantee or billing
measurement. The corrected submitted head requires all seven hosted checks.

Seven jobs, the same runners, two workers, every job/step deadline, the complete
exclusive 4,521-case backend selection and no-retry behavior remain. No assertion,
fixture logic, production source, provider or deployed service changed. The
initial cancelled attempt remains cancelled; no cached success or automatic
retry is introduced. Existing workflow concurrency supersedes an obsolete run
when the corrected commit is pushed.

See [engineering evidence](evidence/onward-destination-return-2026-10-15.json).
