"""Read-only, release-bound retrieval over a separately qualified public corpus.

This module neither indexes private matter data nor promotes quarantined sources.
OpenSearch is a candidate retriever, not a legal applicability verifier.
"""

import ipaddress
import json
import math
import re
import time
from datetime import date
from urllib.parse import urlsplit

import httpx

from .search_index_contract import FIELDS, MANAGED, SCHEMA, document_id, ready_metadata
from .search_normalization import match_spans, terms

ALLOWED_INDEXES = frozenset({"law-public-passages"})
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
))
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SOURCE_FIELDS = FIELDS
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_CANDIDATES = 200


class SearchUnavailable(Exception):
    """A channel produced no safely usable retrieval result."""


def _identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def _entity_id(value):
    """Preserve local identifiers and absolute RDF IRIs without normalization."""
    if not isinstance(value, str) or len(value.encode("utf-8")) > 512:
        return False
    if _identifier(value):
        return True
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        return False
    if re.fullmatch(r"urn:[A-Za-z0-9][A-Za-z0-9-]{0,31}:[^\s]+", value):
        return True
    try:
        uri = urlsplit(value)
        return (uri.scheme in ("https", "http") and bool(uri.hostname)
                and not uri.username and not uri.password and uri.port != 0)
    except ValueError:
        return False


def _bounded_structure(value):
    remaining = [(value, 0)]
    visited = 0
    while remaining:
        item, depth = remaining.pop()
        visited += 1
        if visited > 20000 or depth > 24:
            raise SearchUnavailable("search_structure_too_large")
        if isinstance(item, dict):
            remaining.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            remaining.extend((child, depth + 1) for child in item)


def _iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Expected ISO date")
    return date.fromisoformat(value)


def _validate_origin(base_url):
    try:
        url = urlsplit(base_url)
        if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ("", "/") or url.port == 0
                or base_url != base_url.strip() or "\\" in base_url
                or any(ord(char) < 32 or ord(char) == 127 for char in base_url)):
            raise ValueError("Invalid private search origin")
        # The sole DNS name is this deployment's private Docker service name.
        # Other sites must use a vetted private IP until pinned DNS/TLS exists.
        if url.hostname != "opensearch":
            address = ipaddress.ip_address(url.hostname)
            if (not (address.is_loopback or any(address in network for network in PRIVATE_NETWORKS))
                    or address.is_link_local or address.is_unspecified or address.is_multicast
                    or (address.is_reserved and not address.is_loopback)
                    or getattr(address, "ipv4_mapped", None) is not None or "%" in url.hostname):
                raise ValueError("Search origin must remain private")
    except ValueError as error:
        raise ValueError("Search origin must be the private opensearch service or a vetted IP") from error


class PublicSearchService:
    def __init__(self, base_url="", index="law-public-passages", release_id="", graph_release=None):
        self.managed = MANAGED.fullmatch(index)
        if index not in ALLOWED_INDEXES and (not self.managed or self.managed[1] != release_id):
            raise ValueError("Index is not in the public-corpus allowlist")
        if release_id and not _identifier(release_id):
            raise ValueError("Invalid corpus release identifier")
        if base_url:
            _validate_origin(base_url)
        self.base_url = base_url.rstrip("/")
        self.index = index
        self.release_id = release_id
        self.graph_release = graph_release

    def _authorized(self):
        try:
            return (self.graph_release is not None
                    and self.graph_release.require_current()['release_id'] == self.release_id)
        except Exception:
            return False

    @property
    def configured(self):
        return bool(self.base_url and self.release_id)

    def _filters(self, as_of, authority_id):
        filters = [{"term": {key: value}} for key, value in (
            ("release_id", self.release_id), ("visibility", "public"),
            ("rights_status", "permitted"), ("review_status", "legally_reviewed"),
        )]
        if authority_id is not None:
            filters.append({"term": {"authority_id": authority_id}})
        if as_of is not None:
            filters.extend([
                {"range": {"valid_from": {"lte": as_of}}},
                {"bool": {"minimum_should_match": 1, "should": [
                    {"range": {"valid_to": {"gt": as_of}}},
                    {"bool": {"filter": [{"term": {"validity_end_status": "open_ended"}},
                                           {"range": {"validity_checked_through": {"gte": as_of}}}],
                              "must_not": [{"exists": {"field": "valid_to"}}]}},
                ]}},
            ])
        return filters

    def _read_json(self, method, suffix, body, deadline):
        if time.monotonic() >= deadline:
            raise SearchUnavailable("retrieval_deadline")
        try:
            with httpx.Client(timeout=httpx.Timeout(5, connect=2), follow_redirects=False,
                              trust_env=False) as client:
                with client.stream(method, f"{self.base_url}/{self.index}{suffix}", json=body,
                                   headers={"Accept-Encoding": "identity"}) as response:
                    if response.status_code != 200:
                        raise SearchUnavailable("search_http_error")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise SearchUnavailable("compressed_response_not_admitted")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise SearchUnavailable("retrieval_deadline")
                        if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise SearchUnavailable("search_response_too_large")
                        raw.extend(chunk)
            result = json.loads(raw)
            _bounded_structure(result)
            return result
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, RecursionError) as error:
            raise SearchUnavailable("search_transport_or_payload_invalid") from error

    def _request(self, body, deadline):
        try:
            result = self._read_json("POST", "/_search", body, deadline)
            if not isinstance(result, dict) or result.get("timed_out") is not False:
                raise SearchUnavailable("incomplete_search_response")
            shards = result.get("_shards")
            if not isinstance(shards, dict) or shards.get("failed") != 0:
                raise SearchUnavailable("incomplete_search_shards")
            hits = result.get("hits", {}).get("hits")
            if not isinstance(hits, list) or len(hits) > body["size"]:
                raise SearchUnavailable("invalid_search_shape")
            return hits
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, RecursionError) as error:
            raise SearchUnavailable("search_transport_or_payload_invalid") from error

    def _project(self, hit, as_of, authority_id):
        if not isinstance(hit, dict) or hit.get("_index") != self.index:
            raise ValueError("Unexpected index")
        source = hit.get("_source")
        if not isinstance(source, dict):
            raise ValueError("Missing source")
        if any(source.get(key) != value for key, value in (
            ("release_id", self.release_id), ("visibility", "public"),
            ("rights_status", "permitted"), ("review_status", "legally_reviewed"),
        )):
            raise ValueError("Result did not satisfy mandatory prefilters")
        for key in ("passage_id", "document_id", "source_version_id", "authority_id"):
            if not _entity_id(source.get(key)):
                raise ValueError("Missing immutable source identity")
        if self.managed and not _entity_id(source.get("assertion_id")):
            raise ValueError("Missing assertion identity")
        if hit.get("_id") != (document_id(source) if self.managed else source["passage_id"]):
            raise ValueError("Passage identity mismatch")
        if not isinstance(source.get("source_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", source["source_sha256"]):
            raise ValueError("Missing physical-source hash")
        for key, maximum in (("text", 12000), ("title", 500), ("locator", 400), ("source_url", 2048)):
            value = source.get(key)
            if key == "source_url" and self.managed and value is None:
                continue  # Signed source RDF currently has no authoritative URL.
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError("Invalid projected field")
        url = urlsplit(source["source_url"] or "")
        if source["source_url"] is not None and (url.scheme != "https" or not url.hostname or url.username or url.password
                or any(ord(char) < 32 for char in source["source_url"])):
            raise ValueError("Invalid public source URL")
        start, end = source.get("valid_from"), source.get("valid_to")
        if start is not None:
            _iso_date(start)
        if end is not None:
            _iso_date(end)
        end_status, through = source.get("validity_end_status"), source.get("validity_checked_through")
        if end is not None:
            if not start or end <= start or end_status not in {None, "closed"} or through is not None:
                raise ValueError("Invalid closed version interval")
        else:
            if not start or end_status != "open_ended" or through is None:
                raise ValueError("Unknown end is not an open-ended declaration")
            _iso_date(through)
            if through < start:
                raise ValueError("Observation horizon precedes validity")
        if as_of is not None and (start > as_of or (end is not None and end <= as_of)
                                  or (end is None and through < as_of)):
            raise ValueError("Result outside requested version interval or observation horizon")
        if authority_id is not None and source["authority_id"] != authority_id:
            raise ValueError("Authority mismatch")
        if self.graph_release is None:
            raise ValueError('Search evidence requires a verified graph release')
        try:
            return self.graph_release.project_search_hit(source, as_of=as_of, authority_id=authority_id)
        except Exception:
            # Neither arbitrary index fields nor private authorization errors may
            # escape through candidate text, metadata or diagnostics.
            raise ValueError('Search evidence is outside the authorized signed source') from None

    def search(self, query, as_of=None, limit=20, vector=None, authority_id=None):
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError("Search query must contain 1–4000 characters")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise ValueError("Search limit must be between 1 and 50")
        if as_of is not None:
            _iso_date(as_of)
        if authority_id is not None and not _entity_id(authority_id):
            raise ValueError("Invalid authority identifier")
        if vector is not None and (not isinstance(vector, list) or not 1 <= len(vector) <= 4096
                                   or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                          or not abs(v) <= 3.4e38 or not math.isfinite(v) for v in vector)):
            raise ValueError("Vector must contain 1–4096 finite numbers from a qualified local model")
        snapshot = {"backend": "opensearch", "index": self.index, "release_id": self.release_id or None,
                    "as_of": as_of, "fusion": "rrf-k60-v1"}
        channels = {"lexical": "not_run", "vector": "not_requested" if vector is None else "not_run"}
        coverage = {"status": "no_qualified_corpus", "channels": channels,
                    "completeness": "unknown", "corpus_size": "unknown", "rejected_hits": 0}
        limitations = ["Retrieval candidates do not establish legal applicability or complete issue coverage.",
                       "Only exact signed evidence passages and their evidenced authorities are returned; index-only chunks and metadata are excluded."]
        if not self.configured:
            limitations.append("No release-bound qualified public corpus is configured; no request was sent.")
            return {"hits": [], "coverage": coverage, "snapshot": snapshot, "limitations": limitations}
        if not self._authorized():
            coverage['status'] = 'unavailable'
            limitations.append('Current authorization for the matching public graph release is unavailable; no request was sent.')
            return {"hits": [], "coverage": coverage, "snapshot": snapshot, "limitations": limitations}
        if as_of is None:
            limitations.append("No historical version interval was requested; currency is not established.")
        deadline = time.monotonic() + 12
        meta = None
        if self.managed:
            try:
                meta = ready_metadata(self.index, self._read_json("GET", "", None, deadline), self.release_id)
                snapshot["index_schema"] = meta["schema"]
                snapshot["documents_sha256"] = meta["documents_sha256"]
                coverage["indexed_candidates"] = meta["document_count"]
            except (SearchUnavailable, ValueError, KeyError, TypeError, AttributeError):
                coverage["status"] = "unavailable"
                limitations.append("The selected public index is not a sealed, ready release index; no search was sent.")
                return {"hits": [], "coverage": coverage, "snapshot": snapshot, "limitations": limitations}
        normalized_index = meta is not None and meta["schema"] == SCHEMA
        if normalized_index:
            snapshot["normalization"] = meta["normalization"]
            limitations.append("Folded aliases can conflate distinct Turkish terms; they nominate candidates, never authority identities or equivalent legal concepts.")
        filters = self._filters(as_of, authority_id)
        candidate_limit = min(MAX_CANDIDATES, limit * 4)
        common = {"size": candidate_limit, "timeout": "3s", "track_total_hits": False,
                  "_source": list(SOURCE_FIELDS)}
        lexical_query = ({"match_all": {}} if authority_id is not None else
                         {"multi_match": {"query": query, "fields": ["text", "title"]}})
        requests = {"lexical": {**common, "query": {"bool": {
            "filter": filters, "must": [lexical_query],
        }}}}
        if normalized_index:
            for variant, text in terms(query).items():
                channel = "lexical_" + variant
                channels[channel] = "not_requested" if authority_id is not None else "not_run"
                if authority_id is None:
                    query_clause = ({"multi_match": {"query": text, "fields": [f"text_{variant}", f"title_{variant}"]}}
                                    if text else {"match_none": {}})
                    requests[channel] = {**common, "query": {"bool": {"filter": filters, "must": [query_clause]}}}
        if authority_id is not None:
            snapshot["resolution"] = "exact_authority_identifier"
            channels["vector"] = "not_requested"
        if vector is not None and authority_id is None:
            # Native filtered kNN requires a qualified Lucene/Faiss vector mapping.
            # A bool post-filter is insufficient: it can lose authorized candidates.
            requests["vector"] = {**common, "query": {"knn": {"embedding": {
                "vector": vector, "k": candidate_limit, "filter": {"bool": {"filter": filters}},
            }}}}
        if normalized_index:
            # Extra channels share one candidate budget, not one budget each.
            candidate_limit = min(candidate_limit, MAX_CANDIDATES // len(requests))
            for body in requests.values():
                body["size"] = candidate_limit
                if "knn" in body["query"]:
                    body["query"]["knn"]["embedding"]["k"] = candidate_limit
            snapshot["candidate_budget"] = {"total": MAX_CANDIDATES, "per_channel": candidate_limit}
        combined, conflicts = {}, set()
        for channel, body in requests.items():
            if not self._authorized():
                break
            try:
                raw_hits = self._request(body, deadline)
                channels[channel] = "complete"
            except SearchUnavailable as error:
                channels[channel] = "unavailable"
                limitations.append(f"{channel} channel unavailable: {error}.")
                continue
            seen = set()
            for rank, raw_hit in enumerate(raw_hits, 1):
                try:
                    item = self._project(raw_hit, as_of, authority_id)
                except (ValueError, TypeError):
                    coverage["rejected_hits"] += 1
                    continue
                identity = (item["passage_id"], item["authority_id"], item.get("assertion_id") if self.managed else None)
                if identity in seen:
                    coverage["rejected_hits"] += 1
                    continue
                seen.add(identity)
                previous = combined.get(identity)
                if previous and previous["source"] != item:
                    conflicts.add(identity)
                    continue
                entry = combined.setdefault(identity, {"source": item, "score": 0.0, "channels": []})
                entry["score"] += 1 / (60 + rank)
                entry["channels"].append(channel)
        for identity in conflicts:
            combined.pop(identity, None)
        if conflicts:
            limitations.append("Conflicting source versions for the same passage were excluded.")
            coverage["rejected_hits"] += len(conflicts)
        if coverage["rejected_hits"]:
            limitations.append("Some returned candidates failed identity, release or qualification checks.")
        completed = sum(channels[name] == "complete" for name in requests)
        coverage["status"] = "available" if completed == len(requests) else "partial" if completed else "unavailable"
        if coverage["status"] == "available" and coverage["rejected_hits"]:
            coverage["status"] = "partial"
        ranked = sorted(combined.values(), key=lambda item: (
            -item["score"], item["source"]["passage_id"], item["source"]["authority_id"], item["source"].get("assertion_id", "")))
        hits = [{**item["source"], "score": item["score"], "channels": item["channels"]}
                for item in ranked[:limit]]
        if normalized_index and authority_id is None:
            for hit in hits:
                hit["matches"] = match_spans(hit, query)
        if self.managed:
            try:
                if ready_metadata(self.index, self._read_json("GET", "", None, deadline), self.release_id) != meta:
                    raise ValueError("Index receipt changed")
            except (SearchUnavailable, ValueError, KeyError, TypeError, AttributeError):
                hits = []
                coverage["status"] = "unavailable"
                channels.update({name: "unavailable" for name in requests})
                limitations.append("The selected index changed or could not be revalidated; all candidates were discarded.")
        if not self._authorized():
            hits = []
            coverage['status'] = 'unavailable'
            coverage['rejected_hits'] = 0
            channels.update({name: 'unavailable' for name in requests})
            limitations.append('Public release authorization changed during retrieval; all candidates were discarded.')
        coverage["returned_hits"] = len(hits)
        return {"hits": hits, "coverage": coverage, "snapshot": snapshot, "limitations": limitations}
