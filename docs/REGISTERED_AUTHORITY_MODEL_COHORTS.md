# Confidential registered model-authority trial groups

R05A engineering contract, 10 October 2026. This extends registered same-input
local-model authority trials with a private, immutable inventory of **2–12 explicitly
selected trials from one authorized workspace**. It makes no model call and adopts
no candidate. A complete inventory does not establish legal correctness, a held-out
benchmark, reviewer expertise or model benefit.

## Lawyer workflow

In **Çalışma notları → Yerel model dayanak denemeleri ve grup incelemesi**, open the
panel explicitly, fetch metadata, select admitted protocols, supply a title and
purpose, and preview the group. No protocols are selected automatically. Optional
reserved-family labels use the same SHA-256 convention as registered trial families;
only declared exact overlaps are reported.

Inspect the original protocols, exact private baseline, source passages, original
human assessment, any admitted renewal, both candidate arms and their retained
passes. Source-linked reviewer observations, disagreements, adverse-search limits,
review time and declared active effort remain separate. Freeze the exact preview,
then retrieve immutable history or download a confidential JSON packet while its
bindings are Current. Opening or freezing a group neither runs trials nor changes
private draft versions or human legal decisions.

## Exact profiles and honest reconciliation

Groups preserve complete captures, including registration, protocol/job/event
admissions, full evidence and all observation/effort history. Per-viewer action flags
and retrieval timestamps are excluded from the stable manifest. Profiles separate
original-review from admitted-renewal input, declared real/synthetic origin, full
rubric digest, dimension contracts, provider/tenant/model policy pin, research budget,
arm modes/pass limits and declared effort policy. Different profiles are displayed
separately; outcomes and timings are not pooled into accuracy or benefit scores.

The inventory reports exact full-input duplicates, repeated baseline versions,
declared families and reserved-family overlaps, private documents shared across
families, and identical public passage/source representations. It does not discover
near duplicates or prove statistical independence. Public passage sharing does not
imply endorsement, applicability or equivalent legal interpretation.

Each arm retains six semantic dimensions and six finding dimensions for **every**
original selected source, including findings outside the selected model feedback.
Only current, execution/comparison-bound observations from the two assigned accounts
fill observation slots. Missing, unresolved and not-assessed values remain unknown;
a missing pair has an unknown disagreement result. Different labels remain visible
without adjudication. Counts describe selected records only, with explicit denominators.

Elapsed wall time includes queueing; provider round-trip time is separate. Declared
active preparation/verification/correction, shared setup and full review are retained
without overlapping phases. Unknown timing remains null. GPU compute, corpus-wide
adverse recall and preparation-time gain remain unknown. Account separation does
not prove independent expertise or blind review. No qualification flags become true.

## Private access, source guards and freshness

All private parents are authorized before any public-source join. Selection is
restricted to this workspace; metadata lists contain IDs/dates/admission state only,
never quoted protocol titles or evidence. Full manifests, participation metadata,
selected public authorities and exports remain confidential encrypted case records.
Named public graphs gain no inverse matter links or usage counts.

Freshness pins all referenced private records, sealed admissions, evidence versions,
source/release identities, current participant access, recipe/dimension contracts,
provider policy and matter status. A changed run, observation, effort, fact, draft,
review or model pin makes the old snapshot Stale without rewriting it. Its authorized
original history can be inspected; export is closed. A source or admission denial
withholds the entire manifest, including candidates, quotes and observations. A
later restoration permits only the same unchanged authorized snapshot, never an
automatic reseal. Workspace permission denial prevents access entirely.

Preview, freeze, read and export hold existing case/public-source guards. Freeze
serializes on the workspace row and rechecks the exact preview and legal-write
permission before commit. A separate admission stays pending until guard exit and a
second exact guarded check under the workspace lock succeed. Exact nonce replay
returns the same record; a different payload conflicts. Export rechecks freshness
and permissions after serialization and through source-guard exit, discarding bytes
on failure. UI failures clear received manifests, selections and quoted content.

A committed late failure returns HTTP 409 with `committed_needs_revalidation` and
the opaque group ID. Retain that receipt: retry cannot complete pending admission.
There is no manual bit-flipping, administrator override or automatic repair.

## API and operating limits

`/api/v1/matters/{matter_id}/authority-model-cohorts` exposes metadata candidates,
preview, freeze, paginated history, guarded detail and guarded JSON export. Inputs
are typed IDs and explained selection; pasted captures, arbitrary queries and
extra fields are rejected. Recipe: `local-model-authority-trial-cohort-v1`.
Encrypted record kinds: `authority_model_cohort` and `authority_model_cohort_admission`.

Limits: 2–12 distinct trials, 60 groups/workspace, 16 KiB specification, 16 MiB full
packet with serialization reserve, 2,048 referenced records/trial, and listing pages
of 10 by default/20 maximum. Oversized inventories fail closed without truncating
evidence. Archived workspaces prohibit writes. Existing retention, legal holds,
erasure inventory and deletion apply; no schema migration or new service is needed.

Synthetic original/renewal fixtures, authorization/export mutations, real PostgreSQL
row-lock races, a restricted offline Linux rehearsal and browser persistence checks
verify engineering behavior. See [verification](VALIDATION.md) and [operations](OPERATIONS.md).
Representative lawful Turkish samples, independent legal review, actual model
benefit, Standard/Deep qualification, deployment and pilot acceptance remain open.
