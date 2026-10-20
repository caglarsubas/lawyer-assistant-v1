# Explicit, budgeted private focus analysis

R05A-07 provides a separate focused analysis when a full private draft cannot fit
the configured local model. It changes neither the original draft nor its
documents, frozen quotations, attempts, review decisions or version history.

## Lawyer flow

Open **Çalışma notları → Yapılandırılmış analiz taslakları → Bağlama sığan ayrı
odak analizi** on a current saved analysis. Enter a short question and title,
select one application step, and explain the scope exclusions. All alternatives
and quotations start selected. Review them explicitly; any narrower quotation
must stay inside its parent's exact frozen Unicode range. The rule, its complete
conditions, assessment states, premise roles and event date are retained. All
evidence referenced by the retained rule, selected alternatives and ledger facts
is mandatory. A missing selection must first be added to the parent analysis.

The parent's general issue, posture, application rationale and complete conclusion
are not copied into a reduced prompt. The preview identifies these replacements
explicitly. It initializes a new rationale awaiting examination and a withheld
conclusion, with the scope limitation and lawyer's omission note. Original text,
including all uncertainties and adverse material, remains in the parent version.
This is an explicit partial task, not an assertion that omitted material is
irrelevant. Source selection cannot establish semantic completeness.

Choose **Odak kapsamını ve bütçeyi önizle** to inspect the entire prospective
child, exact quotations, omissions, ranges, immutable parent identity and measured
first-pass envelope. This is a local read-only operation: no provider probe,
inference, queue reservation or record write. It returns private prose solely
within the authorized matter under `Cache-Control: no-store`.

Save is enabled only for a fitting fresh preview and explicit partial-scope
acknowledgement. Saving creates a separate unreviewed version-one analysis and
an idempotency receipt; it never starts inference. The usual local suggestion
flow requires its own fresh saved-version budget preview before a model request.
Each subsequent repair envelope is checked independently. An oversized focus is
withheld without trimming, increased limits or fallback. Static accounting units
are conservative UTF-8 bytes plus the unchanged framing and completion reserves,
not observed tokenizer usage or a generation guarantee.

## Exact source and review contracts

`POST /api/v1/matters/{matter_id}/analyses/{analysis_id}/focus/preview` and
`POST /api/v1/matters/{matter_id}/analyses/{analysis_id}/focus` accept typed
identifiers, parent revision/version, exact evidence selectors, scope text and
explicit acknowledgement. Save also requires the measured context fingerprint.
Duplicate IDs, invented or foreign references, out-of-parent ranges, missing
required sources and unsupported source types fail closed. Public-contribution
analyses and already focused parents are outside this first narrowing flow;
retained public rights, admissions and grant dependencies cannot be stripped to
fit a prompt.

Preview and save resolve matter permissions, source freshness, current parent
version and review head, immutable snapshot identity and provider configuration
again. The fingerprint also binds the requesting user, complete choices, exact
outgoing envelope and existing provider pin. Changed scope, review, source,
model/configuration or access requires a new preview. The browser rejects late
responses and stores no scope, excerpts or preview in URLs or browser persistence.
Normal CSRF and matter-write gates apply to both operations; export retains its
separate permission. Customer/date filters and queue-navigation history are not
modified by this flow.

The encrypted child retains `private-analysis-focus-v1` lineage: parent analysis,
immutable version/content digest, revision and review identity; excluded node and
evidence IDs; narrower quotation ranges; replaced sections; scope note; inherited
AI-origin flag; and an explicit false review-transfer flag. This creation record
survives later human edits, model patches, exports and immutable child history;
it describes the original focus selection, not all later edits. Parent snapshot
loss or mismatch makes dependent work stale. Later parent edits do not rewrite
the pinned historical origin or transfer their reviews to the child. Freshness
otherwise covers the child's selected dependencies, not the excluded corpus.

The model receives the complete selected quotations and fixed draft, plus scope
limitations and exclusion counts; no parent-record/reviewer identities or parent
prose are added merely for lineage. The actual measured envelope contains those
warnings. The child starts without parent review events, findings or resolutions.
Derived AI origin still requires fresh AI-contribution assessment. Conditional
private review cannot qualify independent legal/source publication review.

## Verification and remaining gates

Synthetic tests cover fit/one-unit overflow, an oversized parent with a fitting
focus, no hidden quotation changes, exact preview-to-first-pass reproduction,
zero-write previews, idempotent saving, unchanged parent/document/history bytes,
changed version/review/source/model/access rejection, explicit omissions, nested
and public-contribution withholding, AI attribution, export and subsequent edits.
An isolated browser rehearsal demonstrates an oversized parent's separate
5,452/8,192-unit focus, scope-change invalidation, disabled unpreviewed save and a
new unreviewed child while retaining both parents. No real provider is available
to that rehearsal. See the [engineering record](evidence/focused-analysis-2026-10-21.json).

The nine CI jobs, worker counts, complete case allocation, deadlines and five
30-second reserve gates remain unchanged. Hosted checks, guarded merge, new main
CI, installation, actual private-case execution and owner acceptance are separate
receipts. R03-17 owner review, independent source/legal qualification and all
unmeasured legal-quality metrics remain open.
