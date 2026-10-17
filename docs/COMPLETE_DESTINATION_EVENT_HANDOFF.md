# Complete destination exact-event handoff

The new fixed-depth handoff retains the complete59-observation destination return
unchanged, adds one fresh queue observation and one preparation, and therefore
contains61 observations. Its exact fields are `recipe`, `observation`, `queue`,
`prepared`, and `observed_at`. Older event purposes are not projected from it.

Preparation is explicit. A fresh authorized bounded containing queue must resolve
the selected event. Two exact-event metadata GETs use `window=1`; identity and
admission must remain stable, with session/scope/token fences before and after
each awaited read. The first failure prevents the second read. There are no
writes, retries, fallback searches, automatic reads, or implicit refreshes.
Omitted windows expose no saved history and dispatch no target metadata read.

Opening the prepared destination makes one fresh exact-event metadata GET.
Preparation/current and separately saved destination/current comparisons remain
independent. Nested metadata disclosures preserve every earlier observation.
Unknown identities and pending admissions remain explicit and grant no authority.
An explicit verified return restores the original59-observation return unchanged
with zero action reads/writes; this new arrival is not separately captured.
Both unavailable inputs yield selection only. Partial, conflicting, or redirected
observations reject, including redirects attempted before the initial read.

Every public operation validates complete history afresh using private checks
local to that operation. All59 retained selected-packet pins, known and saved-only
head packets, frozen evidence version/manifest, chronology/revisions, relation
flags, admissions and independent review history stay bound. Seven exact customer,
date, source-date and bucket fields retain the original customer OR semantics.
There is no unchecked history export, persistent verdict cache, or recursive
history abstraction. Validation precedes nonce allocation and eviction.

The session book remains eight entries/30minutes, with opaque URLs, no browser
persistence, and principal/session/reload/expiry closure. Failures, denial, new
windows, changed filters/scope/token/target, and retired replies clear every
comparison/panel/link. Active same-firm explicit matter membership is required;
administrator status and customer tags do not bypass membership. Private metadata
stays outside public graphs, provider prompts, shared caches and telemetry.

Qualification adds147 cases to all4,607 previous cases across101 byte-identical
files:4,754 cases/102 files in total. Independent cloned baselines cover every59
pin, saved-only heads, strict schemas/undefined keys, chronology, flags, filters
before allocation, first/second-read failures and fences, clones, independent
comparisons, original return, no weaker projections, TTL/principal/reload and
metadata-only rendering. The fresh synthetic two-lawyer browser uses actual
independent reviews before private edits, early/late preparation and arrival,
redirects, unknown/pending, denial, stale replies, zero-IO return, exact filters
and reload. Source rights are simulated and providers disabled.

All4,521 backend identities and disjoint partitions, eight CI jobs, workers,
architectures, caps, PostgreSQL durability semantics and existing tests remain
unchanged. Require eight exact-head successes and at least30s margin for frontend,
backend job, backend test step and graph runtime before ordinary matching-head
merge. No publication workload is added; profile before adding any. Main-push CI,
deployment and legal/corpus/source-rights/lawyer acceptance remain separate.
R03/R05 remain partial. No backend/provider/credential/deployed-runtime change.
