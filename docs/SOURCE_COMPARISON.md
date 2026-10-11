# Retained source representation comparison

Open **Başka kaynak temsiliyle karşılaştır** in an authorized source review, or
`#/sources/<package-sha256>/compare`. Choose a second retained public-source package
and a passage on each side. Catalog and passage lists are independently paginated;
selection never derives from a title, statute number, citation or similarity score.
Each side has its own passage-relative starting offset. No private matter data,
external URL fetch, original parser, inference or graph query participates.

The comparison preserves exact extracted Unicode code points, CRLF, unusual
glyphs and markup as escaped text. Each window contains at most **2,000** code
points and discloses its full-text coordinates and remaining passage offset.
Original files remain independently inspectable in the existing HTML/PDF source
review or opaque download paths. Extracted wording is not proof of original fidelity.

The O(n) `literal_common_edges_v1` method finds the common prefix and non-overlapping
suffix of the two selected windows. It highlights the remaining ranges, relative
to each window. These ranges can contain unchanged interior text; insertion-only
ranges can be empty. They are not an edit script, paragraph/provision alignment,
omission audit or legal-change classification. Different window cuts or lengths
alone can cause highlights. Complete raw-byte equality and complete extracted-text
equality are reported separately from selected-window equality. None establishes
legal identity, version, current effect or study independence.

## API and reproducible evidence

`GET /api/v1/public-sources/{source_id}/comparison` accepts only two distinct local
package SHA256 IDs, actual passage IDs and bounded offsets:

| Query | Contract |
|---|---|
| `other_source_id` | Required lowercase package SHA256 |
| `passage_id`, `other_passage_id` | Required actual passage identifiers in their respective packages |
| `offset`, `other_offset` | Passage-relative Unicode positions, default 0, strictly inside the passage, at most 20,000 |
| `limit` | 1–2,000, default 2,000 on each side |

The response envelope contains `evidence_json` and `evidence_sha256`. The former
is the exact UTF-8 canonical JSON content to retain; the latter is its SHA256,
excluding the envelope and any newline. Canonical serialization sorts object keys,
uses compact separators and preserves Unicode. Repeated reads of the same packages
and selections return identical bytes. There is no inferred recording timestamp,
reviewer, human effort, assessment or signature.

The `public-source-comparison-v1` record retains both package/version identities,
every package artifact hash/size, original media, source provenance, exact selected
passage identities/locators/ranges/hashes, window text/hash/ranges, bounds and the
literal comparison method. It explicitly retains:

- `normalization: none`;
- `legal_identity_status: unresolved` and `legal_version_status: unresolved`;
- `independent_originals_verified: false`, `current_law_verified: false`, and
  `human_review_recorded: false`.

Both entire packages are verified against their immutable manifests. Fresh live
curator/admin authorization and `source.curate` permission apply before admission,
between package reads and before the final response. Wrong/missing/corrupt artifacts
fail with fixed 409; unavailable passage/windows or same-package selection fail
422; malformed primary package ID fails 404. No partial source text is returned.
Responses use no-store, nosniff and restrictive CSP headers. Nothing is cached,
persisted, promoted or counted as a reviewed relationship.

The browser verifies the exact receipt SHA256, both selected identities, hashes,
coordinates, window wording, scope flags and literal difference ranges before
display. Transfer/validation has a 30-second cancellation deadline. Changing a
package, passage, offset or source page, refresh, unmount and observed authorization
denial abort or discard old work and remove the old result. Download makes a new
authorized comparison read and requires the same evidence digest before saving the
exact receipt bytes. There is no stale-view download fallback or automatic retry.

As with other loaded source text, disconnected clients cannot be retroactively
erased. Keep downloaded evidence within the firm's permitted review handling.
The JSON contains public source data and curator-selected windows, without private
matter links or firm review judgments; it is not a public graph update or permission
to disclose any matter's authority selection.

## Human identity and qualification handoff

Retain the downloaded evidence file and use its exact hash as supporting material
in the existing **Kaynak kimliği** assessment when appropriate. The reviewer must
identify the actual work/version, distinguish representation from authority, check
source omissions/fidelity and independently document rights, history, sensitivity
and legal applicability. A mechanical receipt cannot serve as sole proof of legal
equivalence or study independence. Do not create a second study original merely
because a PDF and HTML package have different hashes.

Source assessments keep their existing individual immutable histories; this tool
does not create a cross-source identity registry, relationship decision, automatic
cross-source revalidation or casebook approval. Independent publication/identity
review and source-linked reference intake must still inspect physical supporting
evidence and retain unresolved or conflicting classifications. Actual shared-work
adjudication and registered paired studies remain open roadmap requirements.

## Engineering verification boundary

The retained Ministry 6101 PDF and TBMM enacted HTML were compared through a
disposable read-only local API/browser. The selected windows were an explicit
engineering sample, not a provision alignment or human legal comparison. Repeated
HTTP evidence and the actual browser download share digest
`5ac16d2b94362e75d6e4211d9f23ef68fa45985cf97a425fca2c4f627e07a1cd`.
Both actual review ledgers remain unassigned at revision 0 with no assessments.

The prior browser block no longer occurred in this invocation: both original PDF
pages rendered in the actual browser worker and switching pages removed the prior
view. The new comparison rendered, downloaded and cleared when selection changed.
Expanded and normal working-frame layouts were inspected with no observed console
errors. No browser policy was overridden. These checks establish this bounded
engineering sample, not legal fidelity, production host acceptance or every browser,
security, error, revocation and disconnected-client scenario.
