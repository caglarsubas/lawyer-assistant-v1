# Development progress projection

The local interactive roadmap uses `scripts/roadmap_progress.py` and the adjacent
CSS/JavaScript assets. Its source-pinned generator appends these assets to the
existing tracker and passes the `progress` result in its embedded snapshot.

Keep a protected `progress-history.json` beside the tracker. Append one snapshot
of item IDs/statuses only when the receipt confirms the matching merged source
and successful PR CI. Pending heads compare against the last verified delivery;
repeated refreshes and the final head-to-merge transition retain that baseline.
Never discard or rewind the history to improve a reported result. An explicit
reconciliation is required for status changes against an already recorded source.

The four groups partition all catalog items: done; open (in progress + planned);
blocked/waiting (the existing waiting category); deferred. Display before/current
counts, deltas and percentages using the declared current denominator. Report
added/removed IDs and individual status changes even when net counts are zero.
A partial engineering delivery can leave all item counts unchanged. Waiting is
not a claim that every listed dependency is externally blocked; item shares are
not effort-weighted completion, legal approval or deployment readiness.

The maintained tracker is a local generated artifact. Its catalog, prior verified
status snapshots and generated-file hashes remain separate from product runtime
data and cannot authorize provider calls, legal decisions or production actions.
