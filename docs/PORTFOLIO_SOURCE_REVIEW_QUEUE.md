# Authorized portfolio source-review queue

Under **İşlerim**, choose **Portföy kaynak incelemeleri** and explicitly update the
queue. It lists source-review work across the lawyer's currently authorized active
matters. The existing assignment/supervisory view remains a separate workflow.

Left-side customer and workspace-date filters apply. Multiple selected customers
use OR matching: a workspace may match any selected customer. A customer tag,
detail-only assignment, reporting relationship, responsibility or administrator role
does not grant matter access. An explicit client-wide content assignment may provide
access under the existing scope rules.

Source-record creation dates have separate fields in the queue. Both date families
use inclusive Europe/Istanbul calendar days. Workspace created/updated/relevant
dates, source-record dates, event dates and legal deadlines remain distinct.
Unknown relevant dates do not match a bounded relevant-date filter.

## Server contract

`GET /api/v1/work/source-reviews` requires fresh `portfolio.read`, `matter.read`
and existing matter content grants. It accepts:

- `customer_ids`: up to 100 distinct comma-separated identifiers; customer
  validation uses scoped routing without decrypting unrelated workspace inventories.
- `date_field`: `created_at`, `updated_at` or `relevant_date`, plus optional
  `date_from` / `date_to` for workspace dates.
- `source_date_from` / `source_date_to` for source-record creation dates.
- `bucket`: `all` or `action_required`; `window`: 1–10 (default 10);
  `offset`: 0–10000.

Dates must be canonical YYYY-MM-DD. Invalid/reversed/unsupported ranges and
excessive filters are rejected. Missing and inaccessible customer selections share
a generic denial. Customer selection never broadens content grants.

SQL content predicates constrain current firm, active matter, customer association
and source context before joins, counts and decryption. At most ten candidate matter
rows are locked, in sorted identity order. The admitted candidate window is checked
again after locks and before return. An intervening inventory change returns 409
without partial results; the lawyer can explicitly refresh with the same filters.
The firm guard serializes sanctioned account, role and content-grant changes.

Created-date filters use indexed routing metadata. Encrypted updated/relevant dates
are checked only within the bounded candidate window. An empty filtered window can
have more candidates; it does not establish portfolio completion. Chronological
windows are prioritized within that window only. Counts are scoped to the scanned,
returned and locked-matter window; `total_count` is null. Remaining pages and the
supported offset ceiling are explicit.

A request observes at most 256 selected private dependencies and 200 contradiction
records across its selected matters. Budget exhaustion stays unknown. It reuses the
[analysis-level observation contract](SOURCE_REVIEW_READINESS.md), including
private versions/hashes, research records, review heads, pending admissions,
independent reviewer eligibility and renewal-parent dependencies. It performs no
public graph validation, external request, inference, admission repair or review
mutation. Every public-source status is `not_checked`; legal readiness remains
`not_established` and qualification is not granted.

## Confidentiality and navigation

Results include the authorized workspace title for navigation, context/analysis
identities, record times, historical decision metadata and fixed observation reasons.
They contain no old source quotes, target text, nomination/review notes or source
capture content. Foreign dependencies are rejected before decryption. Invalid or
inaccessible analysis routing remains an unavailable row with no analysis link.

**Tam kaynak bağlamını aç** opens the [exact metadata handoff](EXACT_SOURCE_CONTEXT_NAVIGATION.md)
for the authorized matter, analysis and context, including records beyond initial
list pages. Passage inspection, renewal, independent decisions and exports remain
explicit under their original guards. Listing and navigation never inherit source
authorization or decisions, and do not change historical records.

The client verifies the exact echoed filters, closed metadata schema, bounds and
source-status distinctions. Customer/workspace-date changes, refreshes, source-date
changes, mode changes, session changes and navigation retire delayed replies and
clear the queue. No browser storage or cross-matter observation cache is introduced.
An empty action-required view still does not authorize source reads or exports.

Qualification uses invented documents, actual PostgreSQL opposite-window locking
and changed-inventory races, real signed-release withdrawal, and browser exercises
of multi-customer/date selection and late replies. Engineering checks do not qualify
national legal coverage, accuracy, productivity, deployment or lawyer acceptance.

Next: exact historical-review selection with bounded metadata lineage and original
guarded event inspection.
