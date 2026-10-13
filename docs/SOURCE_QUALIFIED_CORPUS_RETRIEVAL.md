# Source-qualified corpus retrieval

`POST /api/v1/matters/{matter_id}/corpus/search` searches exact public evidence
passages inside the current authorized release. It complements authority search:
an absent, unreviewed or undated graph relationship cannot hide a released source
passage. It does not search arbitrary URLs, private overlays, quarantined sources,
or unpublished acquired documents.

The closed request accepts a query, optional ISO date, exact passage and source
representation identifiers, and 1–50 results. Turkish lexical normalization only
nominates passages; exact passage lookup does not substitute similar identities.
The date is recorded for review, without inferring an unknown applicability
interval. Authority identifiers and assertion identifiers remain null; citation
treatment, binding force, finality and matter applicability are not inferred.

Each hit preserves the original quote, physical artifact and representation
identifiers, source/text/locator-map/quote hashes, locator, codepoint offsets and
exact release. Snapshot metadata includes serving bytes, ontology and activation
sequence. Existing independent authority search retains its stricter reviewed
relationship and temporal requirements.

One fresh current-release guard spans source discovery, ranking and response
construction. The complete retained A/B sources, component grants, earlier whole
permissions, current keys, epoch, private preparations and active pointer remain
conjunctive dependencies. Entry or exit denial withholds all hits and snapshot
identifiers, with a generic error that excludes private provenance.

Workspace authorization runs before retrieval and again before returning. The
selection and query remain private operation data: no shared inverse links,
query cache, persistence, public index updates or external calls are created.
Responses use `Cache-Control: no-store`.

Coverage counts refer only to released evidence passages. The national corpus
denominator and completeness remain unknown. A scan is bounded to 25,000 passage
nodes, 64 MiB of quote bytes and three seconds of scan work; results are bounded
to 256 KiB without truncating quotes. Partial scans expose limits rather than
inventing totals. Lexical search reports quotes exceeding the normalizer's
12,000-character limit as omitted; exact passage lookup remains available within
the response budget. Result count limits are reported separately from scan
completion. No hits is not evidence that no relevant law exists.

Qualification uses invented documents and TEST-ONLY signatures. Real source
licensing, editorial/legal review, historical population, production key custody,
activation and lawyer-adjudicated retrieval evaluation remain external gates.
The next slice attaches these source nominations to private research output
without promoting them into legal conclusions or bypassing current permission.
