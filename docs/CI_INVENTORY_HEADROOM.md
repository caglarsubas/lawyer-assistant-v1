# Inventory CI follow-up qualification

PR #237's source tree passed its ten PR checks and reserve gates. The following
main release job also passed functionally, but retained only 24 seconds against
the unchanged 30-second reserve requirement. Preserve that result separately
from merge, functional success and performance qualification.

Balance existing capacity across three jobs. Return complete deployment
assignment 6 to the backend (26 cases, two workers, one-minute cap). Move the
complete 49-case workspace permission/proposal group from the backend into the
PostgreSQL job's reserve, after its existing real race tests. Its exact command,
two workers and two-minute cap remain. The single frontend build stays before
backend workers. Whole-release tests stay together. No new job, retry, longer
deadline, extra peak worker or omitted test is introduced.

The retained main observations provide 80 PostgreSQL reserve seconds and a
roughly 25-second workspace group, while assignment 6 takes roughly 37 seconds.
These measurements guide placement; they are not runtime guarantees. Qualify
the new exact head and the subsequent complete main run against every job's
30-second reserve, the backend test-step reserve and existing short-phase gates.
Actual receipts must prove all 1,018 deployment methods once, all 139 frontend
files and 10,532 cases, the unchanged 4,042-pass/97-skip backend remainder, all
49 workspace cases in their new job and all 20 release cases. Keep any further
insufficient results visible. Invoiced billing remains unmeasured.

The collector and its ten test parents remain exact, including all negative
subtest assertions; xdist does not emit their local subtest-count summary. All
103 qualified recovery source pins and 96 earlier dependencies remain exact.
No private original, evidence version, review, credential, session or runtime
service changes. Owner review and genuine deployment qualification remain open.

This closes CI capacity qualification only when the measured gates pass. Exact
private inventory receipt handoff with fresh destination authorization remains
the next product-engineering slice; it is not implemented by this CI change.
