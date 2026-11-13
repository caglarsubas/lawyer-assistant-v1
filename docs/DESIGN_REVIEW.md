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
