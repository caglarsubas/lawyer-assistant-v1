"""Versioned identities/mapping for disposable, release-bound lexical indexes."""

import hashlib
import json
import re

SCHEMA = "public-search-index-v1"
MANAGED = re.compile(r"law-public-passages-([a-f0-9]{64})-([a-f0-9]{32})\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
MAX_DOCUMENTS = 2000
MAX_BYTES = 32 * 1024 * 1024
FIELDS = (
    "passage_id", "assertion_id", "document_id", "source_version_id", "source_sha256", "text", "title",
    "source_url", "locator", "authority_id", "release_id", "visibility", "rights_status",
    "review_status", "valid_from", "valid_to", "validity_end_status", "validity_checked_through",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def document_id(source):
    # One passage may support multiple authorities and historical assertions.
    values = [source[key] for key in ("release_id", "passage_id", "assertion_id", "authority_id")]
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("Incomplete search document identity")
    return hashlib.sha256(canonical(values)).hexdigest()


def properties():
    result = {name: {"type": "keyword"} for name in FIELDS}
    for name in ("text", "title"):
        result[name] = {"type": "text", "analyzer": "turkish"}
    for name in ("valid_from", "valid_to", "validity_checked_through"):
        result[name] = {"type": "date", "format": "strict_date"}
    return result


def ready_metadata(index, response, release_id):
    match = MANAGED.fullmatch(index)
    if not match or match[1] != release_id or not isinstance(response, dict) or set(response) != {index}:
        raise ValueError("Search index identity differs")
    item = response[index]
    mapping = item["mappings"]
    meta = mapping["_meta"]
    if (item.get("aliases") != {} or mapping.get("dynamic") != "strict"
            or mapping.get("properties") != properties()
            or item["settings"]["index"].get("blocks", {}).get("write") != "true"
            or meta.get("schema") != SCHEMA or meta.get("status") != "ready"
            or meta.get("release_id") != release_id or meta.get("channels") != ["lexical"]
            or type(meta.get("document_count")) is not int or not 1 <= meta["document_count"] <= MAX_DOCUMENTS
            or not isinstance(meta.get("documents_sha256"), str) or not HASH.fullmatch(meta["documents_sha256"])):
        raise ValueError("Search index is incomplete, writable or incompatible")
    return meta
