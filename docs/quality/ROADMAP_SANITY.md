# Roadmap sanity audit

Reviewed the public tracker snapshot generated on 13 November 2026 at 03:51 UTC
against `d9ff2b16cc91726ffa4fb2f44dc45d18f53aff4c`, the verified merge of PR
#296. The [audit catalog](roadmap-sanity-catalog.json) maps all 93 checklist
items to their declared status, dependencies, pinned plan source, relevant
implementation and test files, retained evidence where applicable, and remaining
acceptance gate. All 14 milestones have a checklist inventory and explicit exit.
The six deferred items are separately inventoried. Historical references are
bound to the reviewed Git revision.

| Measurement | Result at the reviewed snapshot |
| --- | --- |
| Engineering PRs | 295 merged, 0 open, 0 explicitly blocked. PR #296 added one merged PR and changed no checklist status. |
| Checklist | 42 done, 21 open (10 in progress and 11 planned), 24 blocked/waiting, 6 deferred. |
| Milestones | 0 ready, 9 partial, 4 waiting, 1 planned. All 14 declare legal qualification false. |
| Evidence supporting the 42 done items | 4 engineering/contract deliveries, 25 synthetic functional deliveries, 10 synthetic navigation deliveries, and 3 deliveries with historical local runtime observations. |
| PR and main CI | Independent runs 43357061062 and 43359460603 both passed 13/13 jobs. Minimum job reserve was 40s PR and 42s main. The minimum for steps with a 30s floor was 32s PR and 36s main. Existing 60s short phases retain their declared 15s floor. |
| Provisioning and legal acceptance | Host continuity is staged. Independent trust provisioning, restore/clock controls, receipt integration and the owner v3 decision are pending. |
| Observed live installation | On 13 November the login page and process health answered. The scanner was unhealthy and the provider relay was stopped/unhealthy. Anonymous readiness returned 401. Signed-in target workflows and exact installed-version parity were unverified in that observation. |

The code and test links show the scope of engineering evidence and where to
verify it. A planned item can link an adjacent foundation without credit for
its proposed capability. For example, the local-provider policy and release
scorer support future R05B work, while the sanitizer, exact approval release,
isolated credential broker and provider adapters remain planned. The live
observation was separate from the audited source and CI receipts.

## Findings

| Severity | Finding and consequence | Evidence |
| --- | --- | --- |
| P0, release gate | The first reviewed contracts corpus and independent legal evidence are outstanding. R01 dossiers, R02 publication contracts, R03 navigation, Graph B staging and R08 scoring can be exercised, but no approved representative corpus, held-out legal results or named independent reviewer acceptance appears in the reviewed evidence. The owner has already selected the private documents and the v3 decision is still pending. The separate source/rights and independence gates remain necessary for a public contracts release. | [Contracts phase and R03 exit](../ROADMAP.md#phases-and-exit-gates), [owner checkpoint and reviews](../MILESTONE_REVIEW_2026-10-20.md#owner-steering-and-private-pilot-checkpoint), [scoring boundary](../EVALUATION.md#run-a-scoped-evaluation) |
| P0, target workflow | Process health leaves critical user actions unavailable or unverified. New intake requires a working scanner, and a stopped relay leaves no current evidence of local inference. The historically demonstrated F00-03 provider and R03-18 scanner packets remain valid scoped engineering history. Today’s signed-in intake-to-export workflow remains unverified. | [Intake behavior and readiness](../DOCUMENT_INTAKE.md), [runtime and offline signature contract](../OPERATIONS.md) |
| P1, release dependency | The R08-05 checklist closure omits F00-04/F00-06 (representative intake and target host), R03-07/R03-08 (Graph A and coverage), R04-05/R05-03 (evidence and independent adverse search), R05A-04/R05A-05 (correction and depth), R06-04/R06-05 (dated calculations and playbooks), and R07-03 (freshness/impact). These gates appear in the higher-level plan. An item-only release rollup could omit them. Reconcile item and milestone prerequisites or give each intentional exception an explicit mode and acceptance boundary. R05B is optional for a local release. | [Workstream exits](../ROADMAP.md#delivery-ledger), [phase exits](../ROADMAP.md#phases-and-exit-gates), [catalog](roadmap-sanity-catalog.json) |
| P1, dependency semantics | R05A-07 has shipped focused-draft engineering while its prerequisite R03-17 awaits owner acceptance. R07-10 has shipped bounded cold-backup restart ordering while its prerequisite R07-04 still waits for signed distribution and target recovery. Keep these engineering completions and mark the two cross-scope dependencies as downstream acceptance gates in the tracker. | [Focused analysis](../FOCUSED_ANALYSIS.md), [owner decision](../MILESTONE_REVIEW_2026-10-20.md#owner-steering-and-private-pilot-checkpoint), [cold backup contract](../OPERATIONS.md) |
| P1, sequence and concentration | The current tracker points to F00-06 engineering while the governing handoff makes accountable human contracts review the next product milestone. F00-06 has 89 linked merged PRs and remains partial. Ten R03 navigation increments are marked done while the corpus itself still waits. Of 86 tracked workbench test files, 77 filenames match handoff, arrival, destination or return. These counts describe where the work is concentrated. Preserve the existing checks and route new work to user acceptance, field failures and bounded target integration. | [Current review milestone](../ROADMAP.md#current-review-milestone--20-october-2026), [handoff exit](../MILESTONE_REVIEW_2026-10-20.md#exit-and-next-development), [catalog](roadmap-sanity-catalog.json) |
| P1, acceptance coverage | Existing synthetic evidence exercises authorization, exact version bindings, extraction, search, review, exports and guarded recovery. Representative parser fidelity (including required supplied UDF), native assistive-technology use, real identity migration, idle/disconnected revocation, target workload limits, five-job case outcomes, production RPO/RTO, independent legal correctness and total lawyer preparation time lack qualifying observations in the reviewed sources. Add each observation to its current gate and retain pass/fail/unmeasured distinctions. | [Document formats and limits](../DOCUMENT_INTAKE.md), [signed-in acceptance checklist](../MILESTONE_REVIEW_2026-10-20.md#lawyer-workflow-checks-after-the-exact-candidate-is-installed), [mandatory security qualification](../SECURITY.md#mandatory-unfinished-qualification), [paired trial protocol](../EVALUATION.md#compare-correction-depth-and-abstraction) |
| P2, traceability and stale criteria | 194 of 295 merged PRs have no explicit curated checklist link. This limits attribution without disputing the merges. R07-07 still cites four older CI margins while the present receipt covers 13 jobs plus separate timed steps. Keep historical criteria intact and point the current row to the applicable job/step profile and both CI observations. | [Tracker attribution policy](../tracker/README.md#delivery-and-readiness-views), [historical four-margin criteria](../COMPLETE_98_EXACT_EVENT.md), [current root-cause CI remediation](../ROADMAP.md#root-cause-ci-remediation--2026-11-13) |
| P2, schedule confidence | The 34–42 week envelope is provisional and the public research dossier lists zero capacity measurements. Keep the estimate as a planning assumption until actual acquisition, reviewer throughput and migration effort are recorded. | [Original assumptions and phase windows](../ROADMAP.md#phases-and-exit-gates), [review effort and evidence contracts](../R01_QUALIFICATION.md#included-contracts) |

## Next milestones

1. **Re-establish current target operation and exercise a bounded candidate.**
   Platform operators verify the scanner's admitted offline signature set and
   extractor readiness, the expected relay/tenant/model and no-fallback posture,
   and the exact installed source and image identities. Run the synthetic signed-in
   workflow against that candidate and record the first blocking failures,
   without assigning legal or production acceptance. Keep the two-worker
   allocation, job deadlines and independent PR/main reserve checks.
2. **Run the pending private owner review and open the public contracts rights
   track.** The owner reviews the already selected exact v3 artifact and retains
   corrections and provenance. In parallel, appoint accountable Turkish source,
   privacy and independent legal reviewers and register a lawful representative
   contracts slice. Review exact use/expiry rights, historical relationships and
   source fidelity, then freeze the rubric, held-out boundaries and actual
   reviewer effort. This is the product critical path for R01/R03.
3. **Qualify the first complete contracts task.** A signed release binds corpus,
   graph, index, model, policy and workflow versions. Two eligible reviewers and
   distinct role accounts exercise intake, historic and adverse retrieval,
   applicability/abstention, versioned lawyer review and export, including a
   revoked or suspended account and a restored session. Record exact references,
   error classes, elapsed and active time, coverage and disagreements.
4. **Qualify target operations and field workflows.** Complete W01–W03 role and
   data migration, assisted/narrow browser use, five simultaneous realistic
   jobs, signed offline delivery, cold recovery/rollback and measured RPO/RTO.
   Verify separately provisioned trust and clock/restore controls with actual
   operators, then bind receipt integration to lawful retention and key policy.
5. **Close the broader release gate.** Extend reviewed commercial and employment
   depth, run the independent held-out and lawyer pilot studies, and obtain
   exact-release signoffs. Qualify any optional BYOK mode separately for each
   provider after its local fidelity/privacy, credential and source-return
   checks pass.

## Repeat the audit

Save the public tracker projection and run the checker from this repository.
Use the exact audited snapshot to reproduce the review. A later curated source
requires explicit catalog reconciliation against its own Git baseline.

```sh
curl -fsS --max-time 15 http://127.0.0.1:9194/snapshot.json -o /tmp/lawyer-roadmap-snapshot.json
python3 scripts/check_roadmap_sanity.py --snapshot /tmp/lawyer-roadmap-snapshot.json --json
python3 -m unittest discover -s tests/quality -p test_roadmap_sanity.py
```

The checker reads the supplied public JSON and pinned Git blobs. It verifies
checklist/milestone membership and rollups, dependency cycles, documented
cross-scope completions, evidence link existence, exact source hashes, and
independent successful PR/main observations with the declared reserve profile.
It reports known readiness and sequence gaps without changing roadmap status,
CI configuration, runtime or any retained evidence. The saved public
projection is supplied by the operator.
