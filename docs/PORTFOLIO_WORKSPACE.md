# Customer, workspace and file organization

The private portfolio has three levels: customers (müvekkiller), workspaces
(çalışma alanları), and uploaded files (dosyalar). Customers and workspaces have
a many-to-many relationship. A file belongs to the workspace where it was
uploaded. Customer links are descriptive tags; they never grant access to a
workspace. Existing matter identities, evidence, reviews and exports are preserved.

The left panel contains navigation, customer selection, date filters and the
workspace/file tree. Selecting several customers uses **any selected customer**
matching (OR). No selection means all accessible workspaces. Date filters apply
to workspace creation, last update, or the legally relevant date, as explicitly
selected. Creation and update dates use Europe/Istanbul; both date endpoints are
inclusive. A missing relevant date does not match a bounded relevant-date filter.
Filtering does not alter customer links or permissions.

The center panel retains document intake, source passage inspection, the fact
ledger, research and versioned lawyer-authored preparation. Workspace comments
are append-only private records with an author and timestamp. They do not become
verified facts or legal authorities. Adding a customer tag or comment updates the
workspace activity timestamp without changing legal evidence or reviewed products.

The right panel follows the current page, selected workspace, section and saved
changes. Local guidance explains the next product step. Daily, weekly and monthly
summaries cover the current Turkey calendar day, Monday-to-date, and month-to-date.
They use authorized workspace records and recorded activity, respecting portfolio
filters. Current file totals are explicitly distinguished from period activity.
These are on-demand summaries; no background notification schedule is created.

Assistant chat can use the configured local model to select quotations from saved
workspace metadata, recent comments and the product guide. Output is accepted only
when quotations match supplied sources; free-form model summaries are not presented
as verified facts. Private documents are not implicitly sent to this side-panel
assistant. Legal document synthesis remains in the evidence-grounded research
workflow. The assistant does not see unsaved editor content or act autonomously.
Unavailable or invalid provider output falls back visibly to local guidance.

Each panel can be collapsed, resized horizontally, and expanded into a focused
fullscreen view with restoration. Layout preferences may persist locally; customer
filters, workspace content and assistant conversation do not persist in browser
local storage. Product state is stored through authenticated, CSRF-protected APIs.

## API compatibility

- `GET/POST /api/v1/customers`: permission-scoped customer catalog and creation.
- `GET/POST /api/v1/workspaces`: workspace list/filtering and creation, including
  `customer_ids`. List query fields: `customer_ids` (comma separated), `date_from`,
  `date_to`, `date_field` (`created_at`, `updated_at`, `relevant_date`).
- `GET /api/v1/workspaces/{id}`: existing matter content with customer tags/comments.
- `PUT /api/v1/workspaces/{id}/customers`: replace tags with expected `revision`.
- `GET/POST /api/v1/workspaces/{id}/comments`: read or append `{text}`.
- `POST /api/v1/assistant/respond`: `mode`, optional `question`, and validated
  `context` identifiers/filter fields. Results include sources, limitations and
  whether a provider was used.

Existing `/api/v1/matters/{id}/…` document, research, governance and export APIs
remain compatible. Customer metadata is visible to its creator or an authorized
member of a linked workspace; workspace counts include only accessible workspaces.
All private records remain encrypted and separate from the public legal graphs.
