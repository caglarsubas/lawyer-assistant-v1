"""Bounded local source discovery, independent of graph paths and legal effects.

Only evidence already in the exact authorized public release is searchable.
Queries and matter selections never enter a shared graph, index, log or cache.
"""

import hashlib
import json
import time
from datetime import date

from pydantic import Field, model_validator
from rdflib import RDF, URIRef

from .graph_release import LA
from .research_qualification import Digest, StrictRecord
from .search import _entity_id
from .search_normalization import MAX_TEXT, tokens

MAX_PASSAGES = 25_000
MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
SCAN_SECONDS = 3
RECIPE = "source-qualified-corpus-v1"
LOOKUP_RECIPE = "source-evidence-lookup-v1"


class EvidenceLookup(StrictRecord):
    passage_id: str = Field(min_length=1, max_length=512)
    source_version_id: str = Field(min_length=1, max_length=512)
    expected_release_id: Digest
    expected_serving_sha256: Digest
    as_of: str | None = None

    @model_validator(mode="after")
    def exact_identifiers(self):
        if not all(_entity_id(value) for value in (self.passage_id, self.source_version_id)):
            raise ValueError("Use exact source identifiers")
        if self.as_of is not None and date.fromisoformat(self.as_of).isoformat() != self.as_of:
            raise ValueError("Use a canonical date")
        return self


def _lookup_empty(as_of):
    return {"status": "unavailable", "hit": None,
        "snapshot": {"recipe": LOOKUP_RECIPE, "release_id": None, "serving_sha256": None, "as_of": as_of},
        "coverage": {"scope": "exact_source_passage_and_representation_only", "completeness": "unknown",
                     "total_expected": None},
        "limitations": ["An exact source identity is not an authority resolution or legal applicability assessment.",
            "Private, absent and wrong-version identities share an unresolved result; no similar or current version is substituted."]}


def _project(release, node):
    graph, one = release._resources, release._one
    artifact, representation = (one(graph, node, p) for p in (LA.artifact, LA.textRepresentation))
    text = str(one(graph, node, LA.quotedText))
    return {
        "passage_id": str(node), "document_id": str(artifact), "source_version_id": str(representation),
        "source_sha256": str(one(graph, artifact, LA.contentHash)),
        "text_sha256": str(one(graph, representation, LA.contentHash)),
        "locator_map_sha256": str(one(graph, representation, LA.locatorMapHash)),
        "locator": str(one(graph, node, LA.locator)), "text": text,
        "start_offset": int(one(graph, node, LA.startOffset)),
        "end_offset": int(one(graph, node, LA.endOffset)), "offset_unit": "unicode_codepoint",
        "quote_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "release_id": release.info["release_id"], "visibility": "public",
        "grounding_status": "verified_release_quote", "source_status": "signed_release_evidence",
        "assertion_id": None, "authority_id": None, "authority_resolution": "not_performed",
        "legal_effect": "not_assessed", "matter_applicability": "not_assessed",
        "temporal_applicability": "not_assessed", "finality": "unknown",
    }


def _empty(as_of):
    return {
        "hits": [], "snapshot": {"recipe": RECIPE, "backend": "local_signed_evidence",
            "release_id": None, "serving_sha256": None, "as_of": as_of},
        "coverage": {"status": "no_qualified_corpus", "scope": "released_evidence_passages_only",
            "completeness": "unknown", "total_expected": None, "eligible_passages": None,
            "scanned_passages": 0, "matched_passages": 0, "returned_hits": 0,
            "oversized_passages": 0,
            "scan_complete": False, "budget_exhausted": False, "result_limit_reached": False},
        "limitations": [
            "Source discovery is independent of graph paths; only released evidence passages are searched, not all acquired documents.",
            "Exact quotes establish source grounding, not applicability, endorsement, binding force or exhaustive issue coverage.",
            "The requested date is retained for lawyer review; unknown temporal applicability does not exclude source evidence.",
            "Turkish lexical matches nominate passages; spelling aliases do not resolve authorities or equivalent legal concepts.",
        ],
    }


class SourceCorpusService:
    def __init__(self, release):
        self.release = release

    def get_evidence(self, request: EvidenceLookup):
        request = EvidenceLookup.model_validate(request.model_dump(warnings=False) if isinstance(request, EvidenceLookup) else request)
        result = _lookup_empty(request.as_of)
        if not self.release.info:
            return result
        try:
            with self.release.current_guard() as info:
                if (request.expected_release_id != info["release_id"]
                        or request.expected_serving_sha256 != info["serving_sha256"]):
                    raise ValueError("Source snapshot differs")
                result["snapshot"].update(release_id=info["release_id"], serving_sha256=info["serving_sha256"],
                    ontology_sha256=info["ontology_sha256"], activation_sequence=info["pointer"]["sequence"])
                node = URIRef(request.passage_id)
                # Direct indexed RDF identity lookup never enumerates passages
                # or depends on lexical budgets, paths or query ordering.
                if (not self.release._evidence_eligible(self.release._resources, node)
                        or str(self.release._one(self.release._resources, node, LA.textRepresentation))
                        != request.source_version_id):
                    result["status"] = "unresolved"
                else:
                    result.update(status="found", hit=_project(self.release, node))
                    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESPONSE_BYTES - 1024:
                        result.update(status="over_budget", hit=None)
                        result["limitations"].append("The exact quote exceeds the response budget; it was withheld without truncation.")
            return result
        except Exception:
            result = _lookup_empty(request.as_of)
            result["limitations"].append("Current source permission, integrity or the requested snapshot could not be established; evidence was withheld.")
            return result

    def search(self, query, *, as_of=None, passage_id=None, source_version_id=None, limit=20):
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError("Use a bounded nonempty query")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Use a bounded result count")
        if as_of is not None and (not isinstance(as_of, str) or date.fromisoformat(as_of).isoformat() != as_of):
            raise ValueError("Use a canonical date")
        for value in (passage_id, source_version_id):
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 512
                                      or any(char.isspace() or ord(char) < 32 for char in value)):
                raise ValueError("Use an exact bounded identifier")
        result = _empty(as_of)
        if not self.release.info:
            return result
        try:
            # One current source transaction spans discovery, ranking and result
            # construction. Guard exit failure discards the complete response.
            with self.release.current_guard() as info:
                result["snapshot"].update(release_id=info["release_id"], serving_sha256=info["serving_sha256"],
                    ontology_sha256=info["ontology_sha256"], activation_sequence=info["pointer"]["sequence"])
                wanted = {token.normalized for token in tokens(query)}
                ranked, matched, scanned, eligible, size, oversized = [], 0, 0, 0, 0, 0
                deadline, complete = time.monotonic() + SCAN_SECONDS, True
                for node in self.release._resources.subjects(RDF.type, LA.EvidencePassage):
                    if scanned >= MAX_PASSAGES or time.monotonic() >= deadline:
                        complete = False
                        break
                    scanned += 1
                    if not self.release._evidence_eligible(self.release._resources, node):
                        continue
                    source = _project(self.release, node)
                    size += len(source["text"].encode())
                    if size > MAX_SCAN_BYTES:
                        complete = False
                        break
                    eligible += 1
                    if passage_id is not None and source["passage_id"] != passage_id:
                        continue
                    if source_version_id is not None and source["source_version_id"] != source_version_id:
                        continue
                    if len(source["text"]) > MAX_TEXT and passage_id is None:
                        oversized += 1
                        continue
                    if passage_id is not None:
                        overlap = set()  # Exact passage identity requires no lexical guess.
                    else:
                        overlap = wanted & {token.normalized for token in tokens(source["text"])}
                    if not overlap and passage_id is None:
                        continue
                    matched += 1
                    ranked.append({**source, "score": len(overlap), "channels": ["source_lexical"]})
                    # Bound retained matching content independently of scan size.
                    ranked.sort(key=lambda item: (-item["score"], item["passage_id"], item["source_version_id"]))
                    del ranked[limit:]
                coverage = result["coverage"]
                coverage.update(status="available" if complete and not oversized else "partial", scan_complete=complete,
                    budget_exhausted=not complete, scanned_passages=scanned,
                    eligible_passages=eligible if complete else None, matched_passages=matched,
                    oversized_passages=oversized,
                    result_limit_reached=matched > len(ranked))
                for hit in ranked:
                    candidate = [*result["hits"], hit]
                    envelope = {**result, "hits": candidate}
                    if len(json.dumps(envelope, ensure_ascii=False).encode()) > MAX_RESPONSE_BYTES - 1024:
                        coverage.update(status="partial", result_limit_reached=True)
                        result["limitations"].append("The response byte budget omitted ranked passages; quotes were not truncated.")
                        break
                    result["hits"] = candidate
                coverage["returned_hits"] = len(result["hits"])
                if not complete:
                    result["limitations"].append("The bounded source scan stopped early; observed matches are not a complete corpus count.")
                if oversized:
                    result["limitations"].append("Oversized quotes were omitted from lexical matching; exact passage identity lookup remains available.")
            return result
        except Exception:
            # Never release partial entry proofs, private provenance or queries
            # when source rights, exact bytes, keys or the active pointer change.
            result = _empty(as_of)
            result["coverage"]["status"] = "unavailable"
            result["limitations"].append("Current source permission or integrity could not be established; results were withheld.")
            return result
