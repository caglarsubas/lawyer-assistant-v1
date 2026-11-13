# Delivery sanity and acceptance audit — 13 November 2026

**The product is not release-qualified.** The review covered all **93 checklist
items and 14 milestones** at `d9ff2b16cc91726ffa4fb2f44dc45d18f53aff4c`, the
verified #296 main commit. Three **GPT‑6.1‑sol agents at xhigh effort** performed
the roadmap, backend and browser assessments. Their engineering assessments do
not provide independent legal review or provision real trust identities.

[Interactive report](uat-report.html) · [Roadmap findings](ROADMAP_SANITY.md) ·
[API UAT](BACKEND_UAT.md) · [Browser UAT](FRONTEND_UAT.md) ·
[All requirement mappings](roadmap-sanity-catalog.json) ·
[Exact combined run and implementation hashes](audit-run-results.json)

| Evidence layer | Fresh outcome | What it establishes |
| --- | --- | --- |
| Roadmap sanity | 93/93 items, 14/14 milestones inventoried; source/rollup checks pass | Explicit delivery scopes, dependencies, evidence references and remaining gates. Eleven phase/checklist prerequisite gaps are recorded. |
| Disposable API journeys | 7 pass, 1 known failure | Real handlers, isolated encrypted SQLite storage and synthetic accounts; no live provider. |
| Chromium journeys | 9 pass, 1 known failure | Production frontend with a closed synthetic API router; desktop and narrow-screen interactions. |
| Read-only deployed checks | Shell/health respond; anonymous private endpoints return 401 | Relay stopped, scanner unavailable; 129/130 compared backend files match main. `context_packing.py` differs. |
| Authenticated installed-stack and legal UAT | Not qualified | The browser presented sign-in; no owner credentials were retrieved, private cases opened or review decisions made. |

Two executable regressions remain open: the preview returns to the old file
after upload from a direct file link, and damaged encrypted originals produce a
generic HTTP 500 instead of a controlled integrity conflict. The latter leaks
no original bytes in the observed synthetic response. The API test is a narrow
strict expected failure; the browser test is a TODO. Neither counts as a pass.
The combined acceptance runner returns nonzero while either remains open,
even if the underlying test framework exits successfully.

The dated baseline records **295 merged PRs**, **42 done / 21 open / 24 waiting /
6 deferred checklist items**, and **0 ready / 9 partial / 4 waiting / 1 planned
milestones**. These are three different denominators. The interactive tracker
records subsequent merges and current roadmap curation separately. The audit
does not turn synthetic examples into corpus approval, held-out legal results,
five-job qualification, recovery acceptance or the owner's pending v3 review.

The final combined run completed **46 checks: 44 passed, 2 known failures**.
That includes 28 audit-tool checks in addition to the 18 user-workflow journeys.
Both inventories matched exactly. The two-worker API/quality phase took 6.66s;
the ten Chromium scenarios took 15.40s. These local measurements do not predict
hosted runner cost or production latency.

## Repeatable commands

Use the existing backend development environment; no live credentials are needed.
Run these from the repository root:

```sh
python3 scripts/check_roadmap_sanity.py \
  --snapshot docs/quality/audited-roadmap-snapshot.json --json
python3 scripts/run_delivered_uat.py --output /private/tmp/lawyer-uat-fresh
python3 scripts/observe_uat_runtime.py --compare-backend-code
python3 scripts/build_delivered_uat_report.py
```

The first command rechecks the retained public snapshot against the exact
historical Git blobs. A different current snapshot needs explicit catalog
reconciliation; source drift is not silently accepted. The second creates a
new owner-only observation directory, uses two workers, and keeps framework
failures, expected failures and unexecuted work distinct. Choose a new output
directory for every run; existing observations are never overwritten.

Add `--browser` after provisioning the separate browser tooling described in
[the browser report](FRONTEND_UAT.md#reproduce). That builds the frontend and
executes the actual Chromium interactions. Add `--observe-runtime` only for
read-only, unauthenticated observations of the local installed stack. It makes
no provider request and does not restore services or alter Docker volumes.

The default PR workflow adds only the compact audit/API contracts after the
existing frontend-history workers exit. Existing test assignments, worker
ceilings, job caps and reserve policies remain unchanged. The on-demand browser
run and full acceptance verdict remain separate; green engineering CI is not
a UAT pass. Exact PR and independent main evidence are published by the tracker.

## Corrective work order

1. Repair the two reproduced user-workflow defects with their failure tests.
2. Restore admitted scanner and approved local relay operation; reconcile the
   intended `context_packing.py` and exact installed candidate.
3. Run signed-in synthetic intake → analysis → separate review → export on that
   candidate, including expiry/revocation and original recovery.
4. Carry forward the pending private owner review without overwriting it, and
   advance rights-cleared, independently reviewed contracts corpus work.
5. Qualify historical/adverse retrieval, representative formats, five-job load,
   independent restore, held-out legal outcomes and lawyer preparation time.

The current roadmap amendment reconciles release dependencies and sets this
sequence. Historical packet counts, frozen qualification records, original
documents, source versions and review histories remain unchanged.
