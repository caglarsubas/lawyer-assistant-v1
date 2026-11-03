# Disposable operator inspection preview

This unregistered ASGI wrapper adds a Turkish inspection screen to the staged
checksum handoff. It accepts only the existing disposable-identity service and
one host-selected source with an independently pinned handoff checksum. It is
not installed in the live workbench and never opens the private matter store.

## Workflow

1. Open the generic screen at `/firm-admin/operator-preview`. It contains no
   source identifiers, expected checksums, actor data or credentials.
2. Choose **Hazırlanan aktarımı görüntüle**. A same-origin cookie bootstrap checks
   the current assigned reviewer using the real disposable session/RBAC code.
   Its CSRF token stays in browser memory; it is never displayed or persisted.
3. A CSRF-protected POST inspects the exact prepared handoff. Its source ID,
   handoff/provenance checksums and original preparation/expiry times appear in
   a collapsible disclosure. The expected receipt checksum is deliberately absent.
4. Enter the receipt's 64-character lowercase SHA-256 value from a separately
   retained record. The screen never fills that value from the incoming packet,
   URL, preview, earlier result or browser storage.
5. Compare through the unchanged receipt re-observation endpoint. The browser
   checks the exact source/handoff/provenance binding and SHA-256 of the returned
   metadata before displaying it. A new preparation clears the previous result
   and entry; failures and page departure clear private browser state.

A conflict can mean a wrong checksum, changed preparation or expired context.
Check the separate record and inspect again. There is no automatic retry. A
successful comparison is a repeatable read, not a new review decision, recovered
acknowledgement, grant, installation or authority renewal. SHA-256 establishes
byte identity; it does not authenticate the sender or prove channel independence.

## Server boundaries

The public GET serves fixed generic HTML only. The session GET requires an
assigned current reviewer cookie and a custom same-origin fetch header; foreign
origins, duplicate cookies and bearer credentials are refused. No CORS allowance,
login, account creation, password change or session creation is provided. CSRF
bootstrapping uses the current existing session, rechecks it before returning and
never inspects private provenance. The firm guard is released on every path.

The preview POST accepts only an empty JSON object. Real current cookie, firm,
role, origin and CSRF checks precede body or provenance inspection. Both original
pins, the independently assigned reviewer and preparer, original five-minute
window and source binding are validated before and after preparation. Time is
sampled again after final authorization: a clock advance during validation cannot
release expired metadata. Late errors, revocation, rollback, replacement and
cancellation withhold the entire preview and its checksum.

The wrapper narrows the original handoff adapter to its one selected source;
requests cannot select another host source, store, profile, path or principal.
The old re-observation implementation and all original source/history bytes stay
unchanged. Negative/stale reviews and missing acknowledgements keep their exact
meaning through that endpoint.

## UI and budgets

The screen follows the existing restrained workbench typography, colors and
keyboard controls, with a narrow-screen layout and no external assets. Hash-only
script/style CSP, no framing, no referrer, no-store and nosniff protect the page.
All metadata is rendered as text; credentials never enter a URL, visible field,
HTML attribute, report, console, local storage or session storage. The only
entered checksum is cleared after submission. Browser aborts and sequence guards
prevent a late response from rendering in a replaced or departed context.

The preview retains the two-second/eight-frame/2-KiB input limits, a 20-second
cooperative authorization workflow and 4-KiB preview ceiling. The unchanged
comparison endpoint retains its 8-KiB ceiling. The browser has a 22-second abort
window; no response is sent before server validation completes. These are
cooperative processing bounds, not a network delivery SLA.

Tests and browser checks use invented records and disposable accounts. They do
not establish genuine operator appointments, external trust, key custody, native
inference, production use, legal correctness or independent human review. The
owner's focused-analysis-v3 review remains pending.
