# Workspace-group placement and PostgreSQL reserve

The independent main run 40661329285 for PR #242 completed the PostgreSQL job
functionally in 281 of 300 seconds. Its 19-second reserve fails the retained
30-second qualification gate. The completed final-release job retained 75
seconds. Cancel the remaining ineligible run rather than spend its backend tail;
keep its completed receipts and cancellation state as diagnostic history.

Move the complete 49-case workspace permission/proposal group from the
PostgreSQL job to the final-release job, after its whole-release group exits.
Preserve the exact pytest command, both source files, two workers and two-minute
step cap. Its database URL remains step scoped: workspace fixtures retain their
existing isolated data configuration. The real 95-case PostgreSQL race group
continues unchanged with its original service, durability checks and job cap.

Keep ten jobs, all deadlines, the complete 1,018-method manifest and assignments,
139 frontend files/10,532 cases, all backend groups and the single frontend build.
No testcase is removed or duplicated. The placement contract and actual logs
must establish all 49 workspace cases in final-release, all 95 race cases in
PostgreSQL, all 32 human-review cases in frontend and the unchanged remainder.

Require fresh exact-head and independent-main qualification and fixed job/step
reserve gates. A cancelled or near-deadline baseline is diagnostic evidence,
never clearance. Originals, exact evidence versions, review history, source pins
and private runtime remain unchanged. Native receipt packaging and owner review
remain separate readiness requirements.
