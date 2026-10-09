# Reviewed renewal of retained source bindings — R05A

A lawyer can explicitly re-examine inherited public-source bindings against the
current private draft. The resulting version is **Needs review**. Binding freshness
is separate from legal correctness, source approval and resolution of findings.
Unresolved, Not assessed and Needs change observations remain visible.

## Lawyer workflow

In **Çalışma notları → Yapılandırılmış analiz taslakları**, open **Saklanan kaynak
bağlarının yeniden incelenmesi**, then load the current draft and original sources.
Opening tools/history does not invoke inference or mutate the draft.

Inspect the current issue, event date, posture, facts, rules, applications,
alternatives and conclusion. Inspect each retained context's exact original
passages, source/provision versions, temporal limits and original target snapshots.
For every inherited contribution and every source in its context, select existing
current draft targets and record all six review dimensions: applicability, history,
conditions, relationship, adverse authorities and certainty. Record a note and an
optional declared active review time. Unknowns need not be labelled Supported.

Choose explicitly to retain these sources for review and supply a version-change
reason. The server creates an immutable human review and a new draft version;
no model call, automatic legal acceptance, source substitution or graph update
occurs. Ordinary private-draft review is still separate. W03 opinion acceptance
does not renew source lineage or approve the legal analysis.

## Evidence and permission boundaries

Original context/review IDs, source quotes and seals, model identity, proposal job,
accepted response pass and historical contributions remain unchanged. A renewal
is an additional human assessment, never a claim that the historical model used
newer evidence. It binds the exact draft content, all inherited dependency IDs,
observed authority-review heads, review recipes/dimensions, reviewer and time.

Both an active lawyer/admin application marker and `matter.review` permission are
required to preview/save; case access and ordinary action gates still apply.
Authenticated case readers can inspect admitted history. Application roles do not
prove professional identity or independent legal qualification.

Original source permission, graph pin, evidence integrity and completed context,
review and draft admissions are checked on every relevant read/write/export.
Renewal may address changed review heads or the original reviewer's access loss.
It cannot bypass changed/revoked sources, unknown/missing proofs, an incompatible
review contract, or changed private facts/documents. Changed private evidence
requires a new ordinary draft version before renewal.

The latest renewal becomes Stale after substantive private/model changes, changed
inherited dependencies, changed observed heads, recipe/dimension changes, or loss
of the renewal reviewer's case/review access. Another exact human renewal is
required; prior assessments stay immutable. Source denial withholds derived draft
content and renewal notes. Export remains blocked while binding freshness is
Stale; historical versions are assessed using their own retained bindings.

## Transactions, receipts and bounds

The case row serializes draft publication across PostgreSQL connections. Save
requires the exact parent version/revision and preview SHA-256. Inputs are rechecked
before commit, source guards close after commit, and separate admission records
complete before the new version is readable. Competing saves cannot create two
versions from the same observed head. Identical retries return the original receipt;
a concurrent retry may observe a pending admission and receive HTTP 409.

A late guard/permission failure retains committed bytes pending and returns a
`committed_needs_revalidation` receipt. Replaying it cannot complete admission or
silently open the draft. Treat this as an operational incident; preserve the pending
records and diagnose authorization/source state. This packet does not supply an
administrator override or an automatic recovery path.

The existing maximum of eight retained contributions is unchanged. Each context
has at most eight sources, each assessment has six dimensions, requests are bounded
to 256 KiB, sealed records/preview responses to 2 MiB, and each analysis to 20
renewals. Nothing is silently truncated. History expands only the latest assessment
and gives prior seals, authors and version links. DOCX/PDF include original model
contributions plus renewal history and the latest observations; post-render checks
still discard changed-source exports.

All records use the existing encrypted case store and matter lifecycle/retention
rules. No schema migration, live account grant, credential change, provider call,
public-source acquisition or deployment is part of this engineering packet.

## API and remaining gates

Use `/api/v1/matters/{matter_id}/analyses/{analysis_id}/lineage-reviews`:

- `GET /preview`: guarded exact draft, source contexts, current heads and preview seal.
- `POST`: exact version/revision/seal, receipt nonce, explicit `retain_for_review`,
  change reason and complete per-dependency/per-source observations.
- `GET`: admitted bounded renewal history, with the latest assessment expanded.

Existing drafts without renewals retain their previous admission compatibility.
New admissions seal the retained renewal references, so dropping a reference
cannot silently discard provenance. Every reference resolves to its sealed human
record, completed proof and the immutable version it created.

Invented source fixtures, mocked inference, PostgreSQL locks and offline Linux
checks establish engineering behavior only. The latest admitted renewal can now
serve as an explicitly identified input to [registered local-model authority
trials](REGISTERED_AUTHORITY_MODEL_TRIALS.md). It preserves the original review
dependency and uses the renewed human assessment without rewriting former model
responses or declaring the original review current. Lawful reviewed corpus acquisition, representative
Turkish semantic/adverse evaluation, real-model performance, measured lawyer
benefit, deployment and release qualification remain open. See [roadmap](ROADMAP.md)
and [validation](VALIDATION.md).
