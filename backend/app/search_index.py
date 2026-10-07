"""Build a new immutable lexical index from current, signed public evidence.

Never switches an alias, modifies an existing index, reads a matter, or promotes
quarantine. Failed/ambiguous builds remain for inspection; they are not retried.
"""

import hashlib
import json
import secrets
import time

import httpx

from .citation_occurrences import PROFILE as CITATION_PROFILE
from .citation_occurrences import derived_fields as citation_fields
from .graph_release import _load_serving
from .search import PublicSearchService, _bounded_structure, _validate_origin
from .search_index_contract import (
    CHANNELS,
    FIELDS,
    HASH,
    MAX_BYTES,
    MAX_DOCUMENTS,
    SCHEMA,
    canonical,
    document_id,
    properties,
    ready_metadata,
)
from .search_normalization import derived_fields, normalization_metadata

BATCH_SIZE = 50
MAX_BATCH_BYTES = 1024 * 1024
BUILD_SECONDS = 60


class IndexBuildError(RuntimeError):
    def __init__(self, index, stage):
        super().__init__("Index build did not complete; reconcile the retained index before any use")
        self.index, self.stage = index, stage


class IndexTransport:
    def __init__(self, base_url, index, deadline):
        _validate_origin(base_url)
        self.url, self.index, self.deadline = base_url.rstrip("/"), index, deadline

    def request(self, method, suffix="", *, body=None, ndjson=None):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Index build budget exhausted")
        raw = ndjson if ndjson is not None else canonical(body) if body is not None else None
        if raw is not None and len(raw) > 2 * 1024 * 1024:
            raise ValueError("Index request exceeds its bounded budget")
        with httpx.Client(timeout=httpx.Timeout(5, connect=2), follow_redirects=False, trust_env=False) as client:
            with client.stream(method, f"{self.url}/{self.index}{suffix}", content=raw,
                               headers={"Accept-Encoding": "identity", "Content-Type": "application/x-ndjson" if ndjson is not None else "application/json"}) as response:
                if response.status_code not in {200, 201} or response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError("Index request failed")
                output = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() >= self.deadline or len(output) + len(chunk) > 2 * 1024 * 1024:
                        raise ValueError("Index response exceeds its bounded budget")
                    output.extend(chunk)
        result = json.loads(output)
        _bounded_structure(result)
        if not isinstance(result, dict):
            raise ValueError("Invalid index response")
        return result


def inventory(release, index, deadline):
    """Derive source fields independently; omit provenance/private ledger objects."""
    validator = PublicSearchService(index=index, release_id=release.info["release_id"], graph_release=release)
    rows, total = {}, 0
    for projected in release.iter_search_documents():
        if time.monotonic() >= deadline:
            raise TimeoutError("Index preparation budget exhausted")
        source = {name: projected.get(name) for name in FIELDS}
        ident = document_id(source)
        if ident in rows:
            if {name: rows[ident][name] for name in FIELDS} != source:
                raise ValueError("Conflicting signed search identity")
            continue
        if len(rows) >= MAX_DOCUMENTS:
            raise ValueError("Index document budget exceeded")
        # Reuse the reader's identifier/interval limits and independent exact
        # passage projection. No truncation or guessed dates/URLs are permitted.
        verified = validator._project({"_index": index, "_id": ident, "_source": source}, None, source["authority_id"])
        if source != {name: verified.get(name) for name in FIELDS}:
            raise ValueError("Search projection differs from signed evidence")
        indexed = {**source, **derived_fields(source), **citation_fields(source)}
        total += len(canonical(indexed))
        if total > MAX_BYTES:
            raise ValueError("Index byte budget exceeded")
        rows[ident] = indexed
    if not rows:
        raise ValueError("No eligible signed public evidence to index")
    return dict(sorted(rows.items()))


def _ack(response):
    if response.get("acknowledged") is not True:
        raise ValueError("Index operation was not acknowledged")


def batches(entries):
    """Bound derived-field writes and their larger per-document readback envelope."""
    batch, size = [], 0
    for ident, source in entries:
        length = len(canonical({"create": {"_id": ident}})) + len(canonical(source)) + 2
        if length > MAX_BATCH_BYTES:
            raise ValueError("Search document exceeds bulk budget")
        if batch and (len(batch) == BATCH_SIZE or size + length > MAX_BATCH_BYTES):
            yield batch
            batch, size = [], 0
        batch.append((ident, source))
        size += length
    if batch:
        yield batch


def build_index(release, base_url, expected_release):
    if not isinstance(expected_release, str) or not HASH.fullmatch(expected_release):
        raise ValueError("Expected release must be a full SHA-256 ID")
    index = f"law-public-passages-{expected_release}-{secrets.token_hex(16)}"
    stage, deadline = "authorization", time.monotonic() + BUILD_SECONDS
    transport = IndexTransport(base_url, index, deadline)
    try:
        # Same ordering as graph transitions: publication lock before review-row
        # locks. Readers may continue; activation cannot change the source snapshot.
        with _load_serving().publication_lock(release.root, shared=True), release.current_guard() as info:
            if info["release_id"] != expected_release:
                raise ValueError("Active graph release differs from operator expectation")
            stage = "prepare"
            documents = inventory(release, index, deadline)
            meta = {"schema": SCHEMA, "release_id": expected_release, "status": "building", "channels": CHANNELS,
                    "normalization": normalization_metadata(),
                    "citation_profile": CITATION_PROFILE,
                    "document_count": len(documents), "documents_sha256": hashlib.sha256(canonical(documents)).hexdigest()}
            stage = "create"
            # Create-only, unique concrete index. A collision is an error, never
            # permission to change mappings, overwrite documents or remove data.
            _ack(transport.request("PUT", body={"settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {"dynamic": "strict", "_meta": meta, "properties": properties()}}))
            entries = list(documents.items())
            stage = "write"
            for batch in batches(entries):
                raw = b"".join(canonical({"create": {"_id": ident}}) + b"\n" + canonical(source) + b"\n" for ident, source in batch)
                result = transport.request("POST", "/_bulk", ndjson=raw)
                items = result.get("items")
                if result.get("errors") is not False or not isinstance(items, list) or len(items) != len(batch):
                    raise ValueError("Incomplete bulk create")
                for item, (ident, _) in zip(items, batch, strict=True):
                    if set(item) != {"create"}:
                        raise ValueError("Unexpected bulk operation")
                    created = item["create"]
                    if created.get("status") != 201 or created.get("_id") != ident or created.get("_index") != index or "error" in created:
                        raise ValueError("Bulk document was not created exactly")
            stage = "seal"
            _ack(transport.request("PUT", "/_settings", body={"index.blocks.write": True}))
            refreshed = transport.request("POST", "/_refresh")
            if refreshed.get("_shards", {}).get("failed") != 0:
                raise ValueError("Index refresh incomplete")
            stage = "verify"
            count = transport.request("POST", "/_count", body={"query": {"match_all": {}}})
            if type(count.get("count")) is not int or count["count"] != len(documents) or count.get("_shards", {}).get("failed") != 0:
                raise ValueError("Index inventory is incomplete")
            for batch in batches(entries):
                result = transport.request("POST", "/_mget", body={"ids": [ident for ident, _ in batch]})
                docs = result.get("docs")
                if not isinstance(docs, list) or len(docs) != len(batch):
                    raise ValueError("Index readback incomplete")
                for actual, (ident, source) in zip(docs, batch, strict=True):
                    if (actual.get("found") is not True or actual.get("_id") != ident
                            or actual.get("_index") != index or actual.get("_source") != source or "error" in actual):
                        raise ValueError("Index readback differs from signed inventory")
            stage = "ready"
            meta = {**meta, "status": "ready"}
            _ack(transport.request("PUT", "/_mapping", body={"_meta": meta}))
            if ready_metadata(index, transport.request("GET"), expected_release) != meta:
                raise ValueError("Index seal verification differs")
            stage = "authorization_exit"
        # Only return success after the live authorization guard's exit check.
        return {"index": index, **meta, "selected_for_search": False, "bytes": sum(len(canonical(row)) for row in documents.values())}
    except Exception:
        raise IndexBuildError(index, stage) from None
