# Isolated frontend test workers

The previous frontend CI job used269 of300 seconds,leaving31 seconds against a30-second engineering floor. Before adding the complete98 exact-event cases,the test command changes from two fork workers to two isolated thread workers. Vitest isolation remains enabled;all9,388 case identifiers and130 test files remain unchanged. All385 tracked frontend source and workflow files are byte-identical. No application,permission,filter,evidence,provider or graph behavior changes.

Forced TypeScript,all9,388 tests and production build pass locally. The complete suite takes100.428 seconds versus the preceding113.356-second fork observation;host load differs and these local observations do not establish hosted performance or billing savings. See[evidence](evidence/ci-thread-headroom-2026-10-19.json).

Merge requires all8 latest exact-head jobs,independently green base-main and at least30 seconds on frontend,backend job,backend test step and graph-runtime margins. Keep existing runners,caps,backend allocation and PostgreSQL checks. One ordinary matching-head squash followed by independent whole-tree and remote-main verification. No unchanged-code timing retry or gate reduction. The complete98 handoff stays unstarted until this capacity gate passes. No deployment or legal qualification is implied.
