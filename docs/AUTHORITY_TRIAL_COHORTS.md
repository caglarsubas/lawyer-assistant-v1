# Confidential human authority-trial groups

This R05A development inventory freezes explicitly selected registered human revision
trials in one authorized workspace. Lawyers can inspect source overlap, differing
reviewer declarations, absent captures and unknown measurements together. The group
contains private matter data and copied public passages. Its currentness concerns
technical dependencies; legal validity and usefulness still require qualification.

## Select, preview and save

Open **Work notebook → Authority trial groups and gap review**. Tools and data load
only after explicit clicks. Select 2–12 existing registrations, give the group a title
and purpose, and optionally enter family labels reserved for a future evaluation.
Labels are hashed like trial registration labels. Blank means no reserved inventory
was supplied. The declaration does not establish independence or a held-out protocol.

Trials without a capture, partial captures and technically stale trials remain in the
preview with named denominators. Source-denied or unavailable ancestor records block
content disclosure. The server obtains the latest retained capture; pasted trial JSON
and cross-workspace joins are not accepted. Selection does not claim to cover all
registrations or establish unbiased sampling.

Saving binds the exact preview digest and nonce. Changed selections, declarations,
trial heads, sources, observations, participants, recipes or dependencies require a
new preview. Workspace row locks serialize saves with existing draft/trial writers.
An identical request replays one record; changed content under that nonce conflicts.
A different nonce creates a distinct group, retaining earlier immutable history.

## Preserve scope and uncertainty

Profiles partition exact trial/review/comparison/adjudication recipes, semantic and
finding rubrics, workflow, registration timing, review/account-separation settings,
effort limits and real/synthetic origin. Incompatible profiles are displayed separately.
These human trials use no model/provider protocol. The baseline predates registration
and its preparation effort is retrospective; registration precedes the revision only.

The report retains:

- Exact original protocols and selected latest captures, source/draft histories,
  observations, original effort declarations and record hashes.
- Repeated fixed case inputs and baseline versions, declared families, private source
  documents shared across declared families, and public authority occurrences with
  exact passage, authority, source-version and byte/text/locator identities. Repeating
  an occurrence does not imply endorsement or equal applicability.
- Six semantic dimensions and every original source-finding dimension, with each
  current assigned account's outcome, note and source/target links. Missing paired
  judgments leave the comparison of outcomes unknown. Differing labels remain separate;
  no voting, consensus or automatic legal verdict is produced.
- Named observation-slot denominators. Missing, unassessed and unresolved observations
  stay explicit even when the upstream capture is record-complete. Stale captures keep
  their original evidence but do not count as current reviewer pairs.
- Original/revised nullable active preparation, verification/review and correction
  seconds. Unknown differs from an explicit zero. The three upstream effort confirmations
  remain in the packet. Separate adjudicator seconds and selected-source adverse-search
  declarations stay separate from workflow effort.

No support score, adverse recall, time gain, GPU compute, benefit or Standard/Deep
comparison is calculated. All qualification, held-out, production, expertise and
benefit flags remain false. Real origin is a declaration, not source-rights approval,
professional independence or consent verification. The same observations can appear
in several selected trials; the repeated case/version/source inventories expose that
selection rather than converting it into independent samples.

## Confidentiality and immutable history

Every route checks current workspace membership before joins. Original source guards
remain open across group construction and serialization/revalidation, using existing
signed-source publication authorization. Encrypted generic matter records cover groups
and their admission records; existing retention inventory, holds, deletion and backups
apply. Public datasets receive no inverse links, updates or matter-derived learning.

Reads compare each live entry seal with the frozen one. A separate live inventory pins
relevant private record revisions, upstream heads/admissions, participants, recipes,
dimensions and workspace status. This detects another change even if the trial already
had the same stale reason. It does not substitute today's text for frozen evidence.

Changes project **Stale** while preserving the frozen report; export closes. Missing,
moved, denied or integrity-failed source ancestry projects **Withheld** with
`manifest: null`, including removal of titles, purpose, reviewer notes and passages.
Group listings expose identity/date metadata only. Candidate titles are returned only
under source authorization. The UI removes cached received views and preview contents
on failures or withholding. Already downloaded copies remain subject to firm handling.

Writes recheck after flush and immediately before commit. Admission is finalized only
after a clean source-guard exit. A late committed failure returns a pending ID/409 and
no copied notes. Retrying does not admit that record. A fresh preview/nonce creates a
new record; a pending group remains withheld.

A latest technically Current group can download an authenticated private JSON packet,
including explicit missing/partial captures. Serialization is followed by dependency,
membership, source-guard and live-seal checks; failures discard attachment bytes.
`no-store`, `nosniff` and same-origin authentication apply. Stale groups remain inspectable
but cannot download. No source permissions, provider/network settings, schema migration,
CI jobs/workers/retries/deadlines or deployment are changed.

## Bounds and API

At most 12 selected trials, 60 immutable groups per workspace, 16 KiB specifications,
16 MiB canonical packet size including a metadata reserve, and 2,048 candidate record
identities per trial are allowed. Oversized operations fail atomically; evidence is not
silently dropped. Listings default to 10 and cap at 20 per page. Existing trial/source
limits remain. There is no background polling or automatic repeated inference.

Prefix: `/api/v1/matters/{matter_id}/authority-trial-cohorts`.

| Route | Contract |
|---|---|
| GET `/candidates?limit=&offset=` | Source-authorized bounded human-trial metadata |
| POST `/preview` | Exact selected latest captures, gaps and reconciliation; read only |
| POST `/` | Lawyer/admin immutable group; preview digest and nonce |
| GET `/?limit=&offset=` | Bounded identity/date metadata |
| GET `/{id}` | Frozen report and separate Current/Stale/Withheld projection |
| GET `/{id}/export` | Revalidated Current private JSON attachment |

R05A remains partial. Representative lawful Turkish sources, historical/effect review,
independent qualified adjudication, held-out evaluation and measured benefits remain
separate gates. Next engineering work is source-bound local authority revision proposals
through the existing bounded queue and explicit lawyer adoption, followed by qualified
public synthesis. See [roadmap](ROADMAP.md), [trials](REGISTERED_AUTHORITY_TRIALS.md),
[evaluation](EVALUATION.md) and [verification](VALIDATION.md).
