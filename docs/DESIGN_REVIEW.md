# Workspace design review — 13 November 2026

The review covers shared components and the lawyer's primary workflow: overview,
documents, facts, research, saved analyses, evidence, review, history, comparisons,
notes and comments. Shared controls also serve source curation and administration.
This changes presentation and navigation, not saved case content or legal decisions.

## Findings and corrections

| Priority | Finding | Correction |
|---|---|---|
| High | An open browser tab still displayed the former interface; navigation HTML had no cache policy. | HTML and API responses receive `no-store`; successful fingerprinted assets retain long caching. Missing assets return 404 instead of HTML. Existing open tabs need one refresh after preserving unsaved input. |
| High | Quotations mixed long filename buttons, offsets and unstructured text. | A reusable excerpt separates document/page identity, source action, quotation and optional provenance. Current/historical analyses, revision comparisons, review source lists and qualified public-source review use it. |
| High | Extracted line breaks fragmented reading; rewriting them would weaken evidence integrity. | Reading and original-line modes change presentation only. Exact text, Unicode ranges, hashes and document revisions remain intact, without truncation or normalization. |
| High | Expanded reasoning was visually indistinguishable paragraphs. | Five numbered sections distinguish premises, candidate rules/conditions, applications, alternatives and provisional conclusions. Missing steps and unknowns remain explicit. |
| Medium | Expanded disclosures inherited small, muted text and lacked internal spacing. | Shared headers have visible open, hover and keyboard-focus states. Body text uses normal contrast and consistent spacing; technical disclosures have secondary emphasis. |
| Medium | Before/after values and review forms were difficult to scan. | Comparison columns distinguish versions and stack in narrow panels. Definition lists, field groups, checkboxes and references share readable dimensions. Submission and freshness rules are unchanged. |
| Medium | Opening a source below a long analysis could go unnoticed. | The source inspector receives focus and scrolls into view; closing restores focus to its originating control when still present. |
| Medium | Long labels and actions were fragile in narrow panels. | Source headers wrap, quotation controls stay reachable, references wrap and comparison columns stack through container queries. The three adjustable panels remain available. |

## Design rules

- Continue local fonts and the calm green/paper theme. Add no remote fonts,
  decorative media, telemetry or UI dependencies.
- Make document text readable and keep metadata in supporting disclosures.
  Distinguish saved quotations from the current document opened by a source action.
- Keep allegations, unknowns, model contributions, stale records and review
  outcomes explicit. A cleaner display never implies legal approval.
- Preserve labels, keyboard operation and visible focus. Keep mobile controls
  available and unsaved review text intact when changing sections.
- Fix shared components and relevant historical/comparison renderers, rather
  than only styling the initial screen.

## Validation and release evidence

The complete frontend suite passes **10,539 tests in 139 files**, with two workers.
Tests retain review/evidence guards and add exact-character, escaped-text,
metadata-only source and complete-reasoning checks. The TypeScript/Vite build
passes. Browser checks cover expanded quotations/reasoning, original-line
switching, source focus/return, incomplete review guards and workspace sections
at desktop, 900px and 390px widths. Personal data and screenshots stay outside Git.

Release also requires all existing PR and independent `main` checks, including
the 30-second reserve floor. Web-only installation verifies original documents,
evidence, review history and other service identities against the prior state.
The living roadmap records those delivery states separately from broader readiness.

This review does not certify every populated administrative data state or complete
legal UAT. The owner's saved pilot review remains pending.

## Remaining browse and status screens — 14 November 2026

| Finding | Delivered correction |
|---|---|
| Coverage mixed a long register with narrow nested columns and repeated generic disclosures. | Added a keyboard-focusable section index that preserves the route; records stack to the available work-pane width; nested disclosures name their field. |
| The graph offered only a diagram with shortened labels. | Added a keyboard-operable list of exactly the same bounded results, with full labels, review status and identity-based selection. |
| An unavailable graph was described as an empty search. | Service/version failures now have a distinct explanation and retry action. Known service diagnostics use Turkish labels; unknown messages remain visible. No substitute legal data is introduced. |
| Client records exposed IDs prominently and offered no name lookup. | Added Turkish-aware local name search, a clear no-match state and an optional assignment-reference disclosure. Workspace navigation keeps the existing date filters. |
| Work view selection and filters lacked hierarchy; narrow registers cramped actions. | Added visible selected-view styling, readable filter controls and stacked actions at narrow pane widths. |
| Decorative page titles made navigation less direct. | Coverage, graph, clients and system screens now use the same names as navigation. System metadata wraps without crowding values. |

Validation: 10,543 frontend tests in 140 files pass with two workers; the production
build passes. Read-only browser checks cover client search/reset, preservation of
customer/date selection, coverage focus/route preservation, unavailable graph
feedback, and all five screens at desktop and 390px widths. A disposable synthetic
list verifies duplicate-name identity selection by keyboard and long labels.

The live graph currently reports unavailable access; populated graph records were
therefore tested with synthetic data only. This UI delivery does not repair or
qualify the graph service, grant legal approval, or certify every populated curator
and administrator workflow. No case, original, evidence version or review was saved
or changed during the walkthrough. Remaining visual qualification includes populated
curation, exceptional administration states and richer research/review workflows.


## Curator, administration and research — 14 November 2026

| Finding | Delivered correction |
|---|---|
| Long curator pages mixed assignment, passages, proposals, decisions and history. | Source, provision and decision pages now have named section indexes and focusable destinations. Existing ownership, exact-version and independent-review gates remain intact. |
| Administration compressed employee identity, role information and editing into tables. | Readable registers, Turkish-aware name/username search, separate editor sections and inspectable starter-role permissions. Draft assignment changes are clearly distinguished from saved access. |
| Research mixed new work, running jobs, saved output and external-query controls. | Named sections, clearer empty states/date guidance, wrapped actions and readable original-source quotation controls. |
| Section navigation moved the outer page and hid the application header. | Focus is restored without automatic document scrolling; only the containing pane scrolls. Positioned pane boundaries contain hidden accessibility labels. |
| Narrow forms and registers crowded labels and actions. | Forms, roles, assignment rows and research actions adapt to work-pane width, including 390px screens. |

Validation: all **10,549 frontend tests in 142 files** pass with two workers;
TypeScript/Vite production build passes. Tests cover Turkish-aware lookup,
inactive/duplicate-name identity retention, starter/custom-role boundaries,
escaped labels and pane-local focus. Browser checks cover admin search,
unsaved draft retention, curator assignment guards and section navigation,
research question retention, desktop and 390px layouts without horizontal
overflow or outer-page jumps. No permission change, source acceptance,
research job or legal decision was submitted.

The observed source is unassigned; its disabled review controls are intentional.
These checks do not certify every populated administrative or curator state,
or establish corpus, graph-service or legal-research readiness. Exact source
content, request payloads, evidence versions and review history are unchanged.
All PR/main checks and the 30-second reserve gate must pass before web installation.


## Populated records and asynchronous selection — 14 November 2026

| Finding | Correction and boundary |
|---|---|
| A failed research-output load could redisplay the prior output beneath the new selection; late reads could overwrite it. | Clear the prior body/actions immediately, bind every response to matter/output/version, discard closed or superseded reads, and expose same-selection retry. Review refreshes cannot replace another selected output. |
| Native output choices obscured repeated titles, versions and stale state. | A keyboard-operable register shows title, version, date, status and selection; it stacks at narrow pane widths. |
| Curator decision history mixed prose, raw fields and long hashes. | Read-only event records separate saved rationale, reviewer, revision and evidence. Labeled decision fields retain unknowns and zero offsets; original field values remain inspectable. |
| Same-name accounts were ambiguous in assignments and manager choices. | Include usernames while keeping user-ID operations, inactive-account restrictions and draft-versus-saved scope unchanged. |

All **10,560 tests in 144 frontend files** and the production build pass with two
workers. Disposable real-component browser checks cover failure/retry, delayed
responses, stale controls, exact quotations, historical disagreements, duplicate
account keyboard selection and desktop/390px layouts. These synthetic records
contain no private cases; the harness blocks all writes and never forwards reads.
No actual source acceptance, assignment, research run or legal decision was made.

This is populated presentation/selection qualification, not acceptance of live
curation mutations or legal research. Existing owner review and operational
qualification remain pending. CI workers, complete coverage and reserve gates
are unchanged; PR/main and installed verification remain separate.
