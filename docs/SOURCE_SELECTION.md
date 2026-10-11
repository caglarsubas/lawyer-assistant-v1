# Confidential source-selection review handoff

On **Kaynak kapsamı**, select two to six retained source packages under
**Çalışma öncesi kaynak seçimi**. Inspect their direct human relationship opinions
before authoring independent references or enrolling study originals. The selection,
reviewer identities, notes, hashes, counts and shared-work declarations are
firm-confidential operational metadata, even though the originals are public.

Every unordered pair is reported explicitly: **missing**, **unresolved**, **stale**
or **resolved**. Six sources produce fifteen direct pairs. Missing edges are not
completed through transitive inference, matching wording, filenames or statute
numbers. A current resolved opinion is a human declaration, not a verified legal
identity. Different versions of the same work do not automatically become independent
originals. No grouping, independent-sample count or study qualification is inferred.

Conflicting work/version references for one source across current resolved pair
opinions appear separately, with all contributing pair IDs. Stale/unresolved
opinions are retained in their pair history but do not supply current identities
for this consistency check. Different reference spellings remain different; the
tool does not normalize aliases or adjudicate the conflict. The latest conflicting
opinion is not silently chosen as authoritative. Historical classification counts
and changes describe recorded declarations, not a finding about reviewer quality.

Separate source-review gaps remain visible for rights, identity, fidelity and legal
version suitability. Pair coverage does not fill those gaps. Even when every pair
is currently resolved and every source assessment is accepted, independent legal,
rights, privacy, reviewer-independence, historical-applicability and study review
remain required. `independent_original_count` remains null; independence, study,
publication and current-law qualification flags remain false.

## Exact snapshot and export

The local server verifies the complete originals and encrypted source/pair ledgers,
including historical opinions beyond the pair screen's last-fifty window. A read-only
snapshot binds selected IDs, full artifact hashes/lengths, current source-review
revisions, pair revisions, exact latest opinion inputs, comparison hashes, latest
event hashes and complete pair-history hashes. It summarizes the full history rather
than copying comparison passages. Complete historical records remain in each
[pair dossier](SOURCE_RELATIONSHIPS.md).

Full packages, encrypted heads and source/pair event fingerprints are freshly
checked after assembling the snapshot. A changed/deleted event, revision, ownership,
original or authorization withholds the result. No selection row, new assessment,
identity registry, source grant, model request, source acquisition, graph update,
reference answer or study record is written. Existing curator/admin, live
`source.curate`, firm isolation, CSRF and authorization guards apply.

Endpoints accept only strict `{ "source_ids": ["<exact package SHA256>", "..."] }`:

- `POST /api/v1/public-sources/selection-review`: read-only evidence envelope.
- `POST /api/v1/public-sources/selection-review/export`: freshly checked unsigned
  `source-selection-dossier-v1` envelope for confidential JSON download.

The SHA256 covers the exact canonical UTF-8 `evidence_json` bytes, including the
opaque firm-scope fingerprint. Reordering selection IDs produces the same snapshot.
Snapshots contain no guessed recording time and are reproducible while inputs are
unchanged. They are not signatures, current-authorization tokens, trusted timestamps
or proof against a privileged host. Downloaded snapshots cannot detect later changes.
Exports do not enter public legal graphs or become evaluation authorization.

Limits: two to six distinct packages, fifteen direct pairs, at most 200 total pair
events and 512 KiB of receipt bytes. Source ledgers retain their existing 1,000-event
bound. A cooperative twenty-second server work budget is checked between bounded
steps; it is not a hard interrupt of an individual database/filesystem operation.
The browser cancels at thirty seconds. Over-budget or failed checks produce no
partial dossier. Reduce the selection or use individual pair dossiers; no automatic
retry, truncation of the verified ledger or increased CI deadline is added.

The browser verifies receipt hashes, exact selection, artifact inventories, every
direct pair, counts, current declaration conflicts and source-review gaps. Changing
selection, refreshing the catalog, leaving the page or an observed access denial
discards the prior result and cancels work. Downloads always request a new checked
snapshot and show its new state; they never fall back to the previous result.
Metadata renders as escaped text. Pair links explicitly preselect both exact IDs;
the curator still chooses the comparison passages manually.

## Qualification boundary

Synthetic engineering cases and a disposable browser demonstrate missing/conflicting
edges, stale projection, confidential export and cancellation. An actual PostgreSQL
race rejects an export when a second connection commits a new pair opinion during
the read. These checks do not adjudicate any retained 6101/TBMM original or establish
independent study sources. Actual references, witnessed registration, legal source
review, lawful RG/MBS/judicial intake and target-host/pilot qualification remain
roadmap gates. [Reference intake](REFERENCE_CASE_INTAKE.md) and calibration tools do
not automatically consume this handoff or count its selected packages as independent
samples; accountable reviewers must author and bind their own inventories.
