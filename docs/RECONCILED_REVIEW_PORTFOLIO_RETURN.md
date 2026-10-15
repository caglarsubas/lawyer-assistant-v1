# Guarded reconciled-review return to portfolio

R03/R05A engineering continuation of
[read-only independent-review outcome reconciliation](INDEPENDENT_REVIEW_OUTCOME_RECONCILIATION.md).
The lawyer can return directly from a reconciled submission to a fresh portfolio
comparison while retaining the exact historical decision and the initial baseline.

## Workflow and identity contract

1. Reconcile the original submitting actor's exact request, using the existing
   bounded receipt. Unknown or pending outcomes cannot create this handoff.
2. Explicitly choose **Seçilen kararı koruyarak portföy dönüşünü doğrula**.
   Re-observe the complete exact outcome, retrieve fresh authorized historical
   metadata for its event, then re-observe the same outcome. Verify frozen
   version/manifest, event packet, predecessor, scope and admissions. A substituted
   event, changed admission, missing access or retired request closes the action.
3. Create a separate opaque session token. Clone the original return intent and
   change only its selected review ID/packet hash. Keep the original head ID/state,
   head observation time, current-version observation and version observation time
   exactly as captured. Unknown original observations stay unknown. An existing
   selected historical decision cannot be silently replaced by this helper.
4. Explicitly follow **Seçilen tarihsel kararla aynı portföy kuyruğuna dön**.
   Arrival loads intent only. The lawyer must apply the captured filters and
   separately start a fresh bounded authorized queue observation.
5. Compare the initial head/version, selected historical event and currently
   observed head/version separately. A later opposing head and a newer analysis
   version never overwrite the original observations or the frozen evidence.

The distinct exact-event navigation action retains its own fresh navigation
baseline. Its refreshed baseline is not substituted into this queue handoff.
Preparing either action clears a previous follow-up link; failures clear both.
The initial portfolio-selection link remains a separate intentional route.

## Scope, confidentiality and uncertainty

- Preserve exact customer OR, workspace date field/range, source-record date
  range, review bucket, matter/analysis/context and frozen evidence identities.
- Keep tokens in the existing bounded, expiring, principal-bound in-memory book.
  New return intent contains no receipt nonce/digest, notes, quotations, source
  content, old queue results or inherited approval. Routes carry only opaque tokens.
- Retire late responses on filter/revision, scope, principal or expiry changes.
  Tokens convey selection only; current explicit content access remains mandatory.
  Customer tags and administrator status do not grant private matter access.
- Read only the explicitly requested queue window. If the selected target is
  absent, report it unobserved and do not probe its metadata or scan other windows.
  Absence from a window proves neither deletion, lack of access nor corpus coverage.
- A fresh queue comparison checks metadata identity, not source rights or current
  legal applicability. Private-basis readiness and context/review admission remain
  separate. Pending effects withhold consequential preparation; source content,
  export and every later write keep their independent current guards.

No new backend route, schema, inference, graph update, source read, admission
repair or review replay is introduced. Private selection metadata stays outside
shared Graph A/B, public-source requests and browser persistence.

## Qualification and continuation

Pure cases verify all original fields, cloned exact filters, unknown baselines,
selected-versus-current identity, bounded-window absence, substitutions, pending
admission, token expiry and principal isolation. Browser rehearsal uses invented
documents and explicit fixture memberships, with simulated source rights. Real
fixture writes establish an original head, a submitted event, a later opposing
head, a later analysis version and eleven newer contexts placing the selected
target outside the first queue window. Explicit next-window observation retains
the original baseline and frozen evidence. No read-only action resubmits a review.

[Engineering evidence](evidence/reconciled-review-portfolio-return-2026-10-15.json)
records final counts and hashes. Seven CI jobs, two workers, all existing limits
and the exclusive complete backend partition remain unchanged. Exact-head hosted
checks, actual merge/main, deployment and legal qualification are separate states.
R03/R05 remain partial.

Next: an explicit bounded current-head lineage observation from the returned queue,
pinning the selected packet and current head across fresh observations. Establish
only evidenced private predecessor links; truncation or an absent selected event
remains unknown. No legal agreement, authority, source permission or automatic
expansion follows from an observed path.

The bounded metadata observation is now implemented in
[returned review head lineage](RETURNED_REVIEW_HEAD_LINEAGE.md). Its separate action
does not change these return identities or grant source access.
