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


## Two progress views

Engineering subtasks are repository PR records. A completed record requires an
actual GitHub merge and a merge commit in the inspected source ancestry. Open PRs
remain open even when GitHub provides a synthetic merge SHA. Only explicit
`blocked` / `status:blocked` labels classify a PR as blocked; pending checks do not.
Closed PRs without a merge are excluded. This inventory includes implementation,
documentation and evaluation deliveries; a merge does not establish deployment,
passed historical CI, legal correctness or product acceptance.

The engineering list includes titles, dates, exact merge/PR links and checklist
references derived from explicit PR mentions in curated delivery notes. Unmapped
records remain visible. Exact PR-number search avoids accidental hash matches.
The full historical plan remains in the delivery ledger.

Milestone readiness retains the 14 declared workstream states and the existing
93-item checklist. Completed PR work never automatically changes those states.
The separate denominators, percentage scopes and remaining gates remain explicit.

Collect allowlisted GitHub metadata and verify it against the current checkout:

```sh
python3 scripts/collect_roadmap_delivery.py --source-root /path/to/checkout --output /path/to/tracker/engineering-receipts.json
```

The local generator loads `records`, `snapshot`, `project` and `readiness` from
`scripts/roadmap_delivery.py`, and appends `delivery-views.css` / `delivery-views.js`
after the existing tracker and progress assets. It retains `engineering-history.json`
separately from the unchanged 93-item `progress-history.json`. Both receipt/history
files belong in its generated-file integrity manifest. Source hashes include the
collector, projection module and all four UI assets.

Snapshot counts must equal the retained individual records. A verified source
snapshot is append-only; duplicate refreshes do not inflate completion or move the
baseline. Historical completed counts can be reconstructed from verified merge
ancestry; historical open/blocked states that were never sampled stay unknown.
The initial PR #224 baseline therefore has unknown open/blocked counts; PR #225
has an observed complete PR inventory. New deliveries retain fully observed
before/current counts. No retrospective open/blocked states are fabricated.
