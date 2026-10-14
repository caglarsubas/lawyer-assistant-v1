# Private source-review observations and work queue

The source-review panel now offers **İnceleme kuyruğunu güncelle** for the current
analysis. It helps a lawyer find pending decisions, requested changes and confirmed
private dependency changes. It does not mark a matter legally ready.

## Read contract

`GET /api/v1/matters/{matter_id}/analyses/{analysis_id}/source-contexts/readiness`
accepts `window` (1–10; default 10), `offset` (0–10000), `bucket` (`all` or
`action_required`) and optional canonical `date_from` / `date_to` (YYYY-MM-DD).
Dates filter the source-context record's creation time, inclusively by calendar
day in Europe/Istanbul. They are not legal deadlines or event/applicability dates.
An invalid/reversed/unsupported range is rejected.

Current action permissions and matter/content grants are required before querying,
decrypting, joining dependencies, sorting or counting records. This first slice
covers one authorized analysis; it does not aggregate portfolios or infer access
from customer tags, reporting hierarchy, responsibility or record ownership.
A supplied inaccessible matter or analysis returns denial without inventory counts.
Foreign dependency payloads are never decrypted.

A response separates:

- **Historical review:** the latest immutable recorded decision ID/state/time,
  without its notes. A positive recorded decision remains historical.
- **Private observation:** changed, unchanged for the observed private subset, or
  unknown, with fixed reason codes. It checks exact analysis version/content,
  selected encrypted dependency hashes, analysis-review head, bounded contradiction
  records, research revision/full capture digest, independent reviewer eligibility,
  context/review admissions and the immediate renewal parent manifest/head.
- **Public-source verification:** always `not_checked`. Listing invokes no graph
  source guard, source read, inference, external request or cached authorization.
- **Legal readiness:** always `not_established`; qualification is not granted.

States are `pending`, `unavailable`, `needs_renewal`, `changes_requested`,
`awaiting_review` and `inspection_required`. None means ready or exportable.
`action_required` hides records whose private subset showed no change and whose
historical decision was positive; those records still require current public-source
inspection. An empty filtered window does not prove completion.

## Bounds and concurrency

Chronological windows contain at most ten context records. Priorities sort only
within the current window; this is not a globally prioritized portfolio. Counts
refer only to the scanned/returned window. `total_count` is deliberately null.
`has_more`, `next_offset` and `pagination_limit_reached` make remaining coverage
and the supported offset ceiling explicit; narrow dates at the ceiling.

Each request checks at most 256 selected private dependencies and 100 matter
contradiction records. Exhausted observation budgets report unknown rather than
borrowing a prior decision. Context size remains bounded by the existing 2 MiB
immutable-packet contract. Missing admissions or invalid packet seals remain
unavailable; listing never finalizes or repairs them. Metadata returns no source
quotes, target text, client text, titles or free-text nomination/review notes.

The request holds the matter row lock used by sanctioned private edits and reviews,
then rechecks matter/analysis access before returning. The existing firm guard
serializes role/content-grant changes. Real PostgreSQL tests cover a queue waiting
behind an independent review and a private-version edit waiting behind a queue.

## Lawyer actions and client lifecycle

Each row provides explicit current inspection and preparation of a new context.
Inspection, independent review and export keep their complete original source,
private, exact-hash/head, distinct-actor and post-commit guards. Renewing does not
inherit a positive decision or restore withdrawn source rights. Pending/unavailable
rows cannot start renewal from the queue; inspect the original record first.

The panel loads on request, uses same-origin no-store reads, retains no browser
storage, and does not aggregate or cache across matters. Filter/scope changes retire
late replies; source/private/permission errors clear protected quotes, review forms,
notes, renewal inputs and the queue. An unchanged observation does not authorize
subsequent reads: every consequential action obtains its own fresh verification.

This delivery qualifies engineering behavior with invented documents, actual
PostgreSQL concurrency and browser rehearsal. National legal coverage, current
law, legal correctness, productivity and production activation remain separate.
Next: a bounded portfolio source-review queue with explicit customer/date selection,
authorization before every matter join, and coverage that never implies completion.
