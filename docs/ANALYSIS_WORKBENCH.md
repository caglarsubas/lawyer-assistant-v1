# Private legal-analysis workbench

The first R05A runtime slice lets a lawyer write a private, source-linked rationale:
**issue → premises → rule candidates → conditions → application → alternatives →
provisional conclusion**. It produces a reviewable work product and immutable
revisions. The checks inspect declared structure; they do not prove that an
interpretation follows from a passage or that a legal rule applies.

This slice uses authorized private documents and the fact ledger. It does not run
inference, search public authorities, execute a correction loop or dispatch BYOK
research. The existing quotation research workflow remains separate.

## Lawyer workflow

Open a workspace's **Çalışma notları**, expand **Yapılandırılmış analiz taslakları**,
and create a draft for one question.

1. State the issue, procedural posture and event date; an unknown date stays unknown.
2. Select original document passages and exact Unicode ranges. Link selections
   separately to the rule candidates and asserted alternatives they support.
3. Use fact-ledger premises or explicit assumptions/unknowns. Ledger text and roles
   come from the server; a draft cannot turn a party allegation into an established fact.
4. Write rule candidates, conditions and exceptions. Declare whether a condition
   must be met or not met, then assess it in each application and link its premises.
5. Record competing arguments, classifications, distinctions or an explicit research
   gap. A research gap does not constitute an adverse authority.
6. Link the conclusion's application and alternative dependencies; record uncertainty
   and the next action. Preview checks or save the draft.
7. Inspect original passages and check details. Revise with a change note, preserving
   earlier content and checks. Download a selected version as DOCX or PDF.

Incomplete drafts can be saved. Invalid, duplicate, cross-step or inaccessible
references cannot. Opening a new version populates missing condition assessments
as **unknown**, without altering the saved version. It uses the visible current
fact revisions; changed source passages require explicit reselection. Review the
text and assessments again when their dependencies have changed.

## Check and state semantics

`private-rationale-checks-v1` inspects the conclusion's declared dependencies.
Unlinked work is exposed separately rather than suppressing an unrelated branch.

| Finding | Result |
|---|---|
| Missing application, rule evidence, conditions, premises or alternative | Withhold the dependent conclusion |
| Unassessed condition, definite assessment without a premise, or required-polarity conflict | Withhold the dependent conclusion |
| Open recorded contradiction among used facts; documented premise without its original evidence | Withhold the dependent conclusion |
| `legal_norm` candidate supported only through this private-document workbench | Withhold; exact public authority/version/time/competence remain unqualified |
| Allegation, disputed fact, inference, assumption or unknown condition | Expose uncertainty; assessment remains conditional unless another critical check withholds it |
| Search gap, unlinked steps or missing uncertainty | Expose review requirements |
| A request for `supported_candidate` | Retain the request, cap the effective result at conditional |

Every result retains `legal_approval: not_granted` and a semantic-review requirement.
No automatic path produces Reviewed. Removing a check by deleting a node or changing
its type is not proof of correction. Revision comparison records changed sections,
dependency groups and check identifiers; it does not adjudicate the change.

An otherwise structurally complete draft can still misinterpret a clause, omit an
unstated exception or make an invalid deduction. Conditions, source interpretation,
chronology, authority treatment, jurisdiction and legal applicability require lawyer
review and the remaining R03–R05A qualification work.

## Binding, freshness and confidentiality

- Each selected passage requires its full-passage SHA-256 and document revision
  observed by the editor. Each ledger premise requires its observed fact revision.
  A mismatch returns HTTP 409 before preview/save; it never silently binds a newer
  source. After a refresh during editing, a changed fact requires an explicit rebind.
- Source spans use zero-based Unicode code points with an exclusive end; whitespace,
  line endings and original text are preserved. Retained snapshots include quote,
  passage and document digests, locators and revisions.
- Fact, source, recorded-contradiction and check-recipe changes project **Stale** at
  listing, history and export. Reads preserve the immutable version and its original
  checks. This scope covers selected private dependencies, not public-law impact.
- The refresh control reloads the matter and analysis list; previously loaded history
  is cleared so its freshness must be obtained again. A source button opens the
  current document representation; the saved quote remains visible for comparison.
- Records and versions use the existing encrypted matter store. Authentication,
  active sessions, firm membership and matter access apply before reads, joins,
  writes and export. Client/customer tags do not confer access.
- Writes serialize on the matter row and require `expected_revision` for revisions.
  Competing revisions return 409; no losing revision is appended. Writes invalidate
  existing preparation products and add a minimal audit event. The research snapshot
  records analysis IDs/revisions; authored rationale is not added to the quotation
  provider's prompt.
- Export selects an exact immutable version. Stale exports retain the authored text
  but mark it stale and withhold its assessment. Access and freshness are rechecked
  after rendering; changes during rendering reject the response. The audit records
  preparation of an export, not delivery or legal approval.

## Runtime API and bounds

All routes are relative to `/api/v1/matters/{matter_id}/analyses`.

| Method / path | Purpose |
|---|---|
| `POST /check` | Resolve private inputs and preview checks without saving or inference |
| `GET` | List current drafts with effective freshness; default 20, maximum 100 |
| `POST` | Create first immutable version and current draft |
| `GET /{id}/versions` | Read immutable history and its current freshness; default 20, maximum 100 |
| `POST /{id}/versions` | Save a new version with `expected_revision` and `change_note` |
| `GET /{id}/export?version_id=…&format=docx` | Export exact DOCX version; `pdf` is also supported |

Inputs forbid extra fields and invented legal/review states. Limits are 20 passage
selections, 4,000 code points per selection, 20,000 selected code points, 20 premises,
12 rules/applications/alternatives, 12 conditions per rule, 20 references per step
and 100,000 serialized UTF-8 input bytes. Ordinary step text is capped at 4,000
characters. Lists and history use offset pagination.

Private source lookup scans at most 500 documents, 2,000 passages and 2,000,000
code points. Ambiguous identities, missing references and an exceeded scan budget
fail closed; the lookup never silently accepts an unexamined match. Contradiction
inspection scans at most 1,000 records. These are bounded engineering defaults,
not capacity qualification for a large portfolio.

The new record kind is `practice_analysis`, with history in `practice_version`;
no schema migration, provider permission, new dependency or CI job is introduced.
The strict R01 offline analysis contract remains a separate qualification artifact.

## Qualification and next work

Synthetic checks exercise exact quotes, source pins, roles, declared conditions,
immutable corrections, stale projections, firm/matter isolation, export races and
real PostgreSQL revision contention. Browser checks use invented documents and
the model is disabled. See [verification](VALIDATION.md) and
[the roadmap](ROADMAP.md).

R05A remains partial. Qualified public authorities and historical applicability,
semantic/adverse checks, automated bounded correction, Standard/Deep budgets,
checkpoints and lawyer-adjudicated benefit comparisons remain pending. This slice
does not establish Turkish legal accuracy or the product's negligible-error target.
