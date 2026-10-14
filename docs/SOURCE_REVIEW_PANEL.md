# Lawyer-facing source selection and independent review

The analysis workspace now exposes the private source-review contracts through
**Çalışma notları → Yapılandırılmış analiz taslakları → Kaynak seçimi ve bağımsız
inceleme**. The panel opens on request, inside the existing middle workspace;
the navigation, assistant, local fonts and adjustable three-pane layout stay.

## Workflow

1. Choose an authorized saved research product and open its independent source
   passages. No graph authority/assertion alias is created from a source match.
2. Select up to eight exact passages, explain their roles and select existing
   analysis targets. Source identities and versions are read-only. Preview the
   complete nomination; editing any input invalidates that preview.
3. Freeze the preview using its exact hash and a request nonce. Saved context
   history lists only IDs/timestamps until a guarded record is opened.
4. A different authorized lawyer opens fresh review inputs and records their
   own relationship interpretation plus explained observations on quote
   identity, target alignment and temporal/coverage limits. No role, outcome or
   final decision is prefilled as confirmed. The server enforces independence
   from the selector, original analysis owner and exact version author.
5. Inspect the nomination and reviewer interpretation separately, including
   preserved earlier decisions. Only the latest current independent positive
   review enables guarded JSON/DOCX/PDF export. Source review does not change the
   analysis's text, structural blockers or legal approval.

The original quote, locator and offsets sit beside the action using them.
Representation, source, quote and release hashes and private targets remain in
collapsible disclosures. Unknown applicability/finality and corpus limitations
stay visible. Original author, selector and reviewer IDs remain distinct.

## Exact versions and private state

Before rendering fetched quotes, the client verifies SHA-256 over their exact
UTF-8 text, Unicode codepoint ranges, source/representation identities and release
pins. CRLF is not normalized. Preview and saved responses must match their
selected inputs and hashes. These client checks supplement the authoritative
server source/grant/private-basis guards; they do not establish legal truth.

Permission, stale-basis, source-version, digest or export failures clear the
parent's displayed quotes, review notes, editors and previews. Scope changes
unmount the panel; generation checks and abort signals retire delayed replies
and attachment downloads. Source text is inert React text, without HTML/Markdown
execution or remote resource fetching. No browser storage, cross-matter cache,
cloud inference or new external queries are introduced.

An ambiguous network failure hides protected content and preserves the exact
payload/nonce only in the current panel's memory. An explicit user action can
retry that same idempotent request. It is not replayed automatically. An explicit
`committed_needs_revalidation` receipt retains its history ID and stays pending;
it does not become a completed review or an unsaved-write assertion. Navigating
away clears the in-memory panel state.

## Qualification and next packet

Engineering checks cover typed payload bounds, version/hash/matter mismatch,
independent interpretation, complete review dimensions, inert source markup,
pending receipt parsing, scope retirement and guarded attachments. Synthetic
browser workflows exercise preview invalidation, self-review denial, separate
reviewer decisions, exact exports, withdrawal, narrow layout and recovery.
Browser source rights and pending-receipt faults are simulated. Existing actual
signed-source/private-ledger and real PostgreSQL race tests remain separate.

These are engineering fixtures, not national corpus, legal accuracy, independent
professional expertise, productivity or production qualification. Deployment is
separate. Next: explicit source-context renewal and version comparison after
changed evidence/research, preserving original history, exact target mapping and
fresh independent decisions. R03/R05 remain partial.
