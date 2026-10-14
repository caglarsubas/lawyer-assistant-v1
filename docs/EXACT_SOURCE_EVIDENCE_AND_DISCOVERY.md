# Exact source evidence and discovery comparison

`POST /api/v1/matters/{matter_id}/corpus/evidence` accepts a closed request with
an exact passage ID, exact source representation ID, expected full release and
serving hashes, and an optional ISO review date. It performs indexed RDF identity
lookup inside one fresh current-release guard. Lexical scan limits, spelling
aliases and missing graph paths cannot hide a known released identity.

The result is `found`, `unresolved`, `unavailable` or `over_budget`. Found evidence
preserves the original quote, source/text/locator-map/quote hashes, codepoint
offsets and exact snapshot. Authority, legal effect, finality and temporal
applicability remain unassessed. Private, absent, synthetic and wrong-version
identities produce the same unresolved response. Snapshot drift or guard entry/
exit failure withholds all evidence; oversized quotes are withheld whole.

The endpoint requires the read action plus current workspace membership before
and after lookup, uses `Cache-Control: no-store`, and never retrieves a URL,
executes arbitrary SPARQL, writes a graph/index or creates a shared matter link.
All retained original sources and grants remain mandatory dependencies.

`retrieval_benchmark.py` now also provides closed development schemas and
`capture_discovery`/`score_discovery`, alongside the existing lexical benchmark.
The comparison runs three independently bounded profiles:

- Released source lexical discovery, without authority resolution.
- Ordinary public authority search, with exact source and historical checks.
- Graph-grounded discovery through the typed `locate_issues` tool.

Every profile uses the same frozen release, serving/ontology hashes, activation
sequence, sealed index receipt, normalization, source recipe and policy version.
Graph and authority candidates use an explicit knowledge cutoff and event date.
Graph relationships and quotes are checked against signed inputs before recording
their IDs. Graph endpoints nominate candidates; citation treatment, endorsement,
binding force and applicability are not inferred. Source passages remain
independent of graph paths and are never converted into authority identities.

Passage relevance/adverse passage recall and candidate-entity recall have separate
gold sets and coverage denominators. Source-only entity metrics are unmeasured.
Unknown/outside coverage and empty positive gold remain unmeasured; unavailable
and unexecuted covered cells count as misses. Every planned profile/query cell
must appear exactly once, including cells skipped by the total execution budget.
Channel order rotates across queries. Current authorization and the exact index
receipt are checked at the beginning, between operations and at the end; changed
rights, pointers, receipts, source bytes or evidence discard the capture.

The existing `scripts/benchmark_retrieval.py` scores either schema with captured
input hashes and rechecks file bytes before emitting a report. `--schemas` also
exposes the discovery schemas. Offline scoring does not authenticate supplied
observations or reviewer labels. Reports omit query text and confer no runtime,
legal or production permission. These development artifacts belong in protected
operator storage; they are not a public matter-usage graph.

Qualification uses invented RDF and TEST-ONLY signatures, including actual
signed-source/private-ledger capture with local graph query execution and actual
retained-source withdrawal. The fixtures do not establish nationwide recall,
lawyer productivity, legal correctness or the held-out release targets. Licensed
population, independent judgments and lawyer acceptance remain external gates.

Next: accountable source nomination review against specific private analysis
targets, with supporting/adverse/unresolved distinctions and dated review records;
expand development strata and independent gold evidence without promoting
supplied labels into legal authority.
