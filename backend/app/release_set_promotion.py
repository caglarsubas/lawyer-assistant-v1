"""Pure source-set review conversion, never a signature or publication authority.

The live caller must reconstruct the exact private packet under current source
locks. Only explicit public reviewer metadata, candidate graphs and the verified
public physical-evidence union enter signing inputs; private packet files do not.
"""

import json
import re

from rdflib import URIRef

from .release_preparation import canonical, digest
from .release_promotion import _promoted_graphs

TRANSFORMATION = "reviewed-provision-set-promotion-v1"
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_PACKET_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_FILES = 256
_HASH = re.compile(r"[a-f0-9]{64}")
_PRIVATE_FILE = re.compile(r"private-evidence/[a-f0-9]{64}\.bin")
_BINDING_FIELDS = {"schema_version", "source_id", "source_version_id", "source_artifacts", "firm_id", "operator_id",
                   "source_review_head_id", "mapping_head_id", "source_review_revision", "mapping_revision",
                   "projections_sha256"}
_PRIVATE_JSON = {"binding.json", "registry.json", "resolutions.json", "review-report.json"}


def _invalid():
    return ValueError("Complete exact source-set preparation inputs are required")


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def _bounded(files):
    if (type(files) is not dict or not 1 <= len(files) <= MAX_FILES
            or any(type(name) is not str or type(raw) is not bytes or len(raw) > MAX_FILE_BYTES
                   for name, raw in files.items())
            or sum(len(raw) for raw in files.values()) > MAX_PACKET_BYTES):
        raise _invalid()


def _json(raw):
    if not 0 < len(raw) <= MAX_JSON_BYTES:
        raise _invalid()

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _invalid()
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    if type(value) is not dict or canonical(value) != raw:
        raise _invalid()
    return value


def _inputs(files):
    try:
        _bounded(files)
        if not _PRIVATE_JSON.issubset(files):
            raise _invalid()
        binding = _json(files["binding.json"])
        if (set(binding) != {"schema_version", "firm_id", "operator_id", "sources", "publication_eligible"}
                or binding["schema_version"] != "legal-review-snapshot-set-v1"
                or binding["publication_eligible"] is not False
                or any(type(binding[key]) is not str or not 1 <= len(binding[key]) <= 64
                       for key in ("firm_id", "operator_id"))
                or type(binding["sources"]) is not list or not 2 <= len(binding["sources"]) <= 8):
            raise _invalid()
        sources = {}
        for source in binding["sources"]:
            if (type(source) is not dict or set(source) != _BINDING_FIELDS
                    or source["schema_version"] != "legal-review-snapshot-v1"
                    or not _hash(source["source_id"]) or source["source_id"] in sources
                    or source["firm_id"] != binding["firm_id"] or source["operator_id"] != binding["operator_id"]
                    or type(source["source_artifacts"]) is not dict
                    or any(type(source[key]) is not int or not 1 <= source[key] <= 1000
                           for key in ("source_review_revision", "mapping_revision"))):
                raise _invalid()
            sources[source["source_id"]] = source
        report = _json(files["review-report.json"])
        if (report.get("schema_version") != "provision-source-set-preparation-v1"
                or report.get("rdf_generated") is not True or report.get("blockers") != []
                or report.get("signed") is not False or report.get("publication_eligible") is not False
                or report.get("confidentiality") != "firm_confidential"
                or type(report.get("source_count")) is not int or report["source_count"] != len(sources)
                or report["input_digests"]["binding_sha256"] != digest(files["binding.json"])):
            raise _invalid()
        expected = {f"candidate/sources/{source_id}/{name}" for source_id in sources
                    for name in ("raw.bin", "text.txt", "locators.json")}
        public_paths = expected | {"candidate/sources.json", "candidate/structure.ttl", "candidate/jurisprudence.ttl"}
        if (set(files) - _PRIVATE_JSON - public_paths != {name for name in files if _PRIVATE_FILE.fullmatch(name)}
                or not public_paths.issubset(files)):
            raise _invalid()
        manifest = _json(files["candidate/sources.json"])
        if (set(manifest) != {"schema_version", "files"}
                or manifest["schema_version"] != "provision-source-set-public-candidates-v1"
                or type(manifest["files"]) is not dict or set(manifest["files"]) != expected):
            raise _invalid()
        physical = {}
        for name in sorted(expected):
            raw, info = files[name], manifest["files"][name]
            fingerprint = digest(raw)
            if (not raw or type(info) is not dict or set(info) != {"sha256", "bytes"}
                    or not _hash(info["sha256"]) or type(info["bytes"]) is not int
                    or info != {"sha256": fingerprint, "bytes": len(raw)}):
                raise _invalid()
            if fingerprint in physical and physical[fingerprint] != raw:
                raise _invalid()
            physical[fingerprint] = raw
        for source_id, source in sources.items():
            root = f"candidate/sources/{source_id}/"
            for name in ("raw.bin", "text.txt"):
                if source["source_artifacts"].get(name) != {
                    "sha256": digest(files[root + name]), "bytes": len(files[root + name]),
                }:
                    raise _invalid()
            locators = _json(files[root + "locators.json"])
            if (locators.get("artifact_sha256") != digest(files[root + "raw.bin"])
                    or locators.get("text_sha256") != digest(files[root + "text.txt"])):
                raise _invalid()
        return {URIRef("urn:la:review-preparation:" + source_id) for source_id in sources}, physical
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, UnicodeError):
        raise _invalid() from None


def _convert(files, markers, public_reviewer, reviewed_at):
    try:
        output = _promoted_graphs(files, public_reviewer, reviewed_at, expected_markers=markers)
        _bounded(output)
        return output
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, SyntaxError):
        raise _invalid() from None


def promoted_graphs(files, public_reviewer, reviewed_at):
    """Transform only the exact set's markers; authorization remains external."""
    markers, _ = _inputs(files)
    return _convert(files, markers, public_reviewer, reviewed_at)


def public_evidence(files):
    """Deduplicate verified public bytes by hash; never copy private evidence."""
    return _inputs(files)[1]


def signing_inputs(files, *, ontology_sha256, public_reviewer, reviewed_at):
    if not _hash(ontology_sha256):
        raise _invalid()
    markers, physical = _inputs(files)
    if _json(files["review-report.json"])["input_digests"].get("ontology_sha256") != ontology_sha256:
        raise _invalid()
    graphs = _convert(files, markers, public_reviewer, reviewed_at)
    body = {"reviewer": public_reviewer, "reviewed_at": reviewed_at, "decision": "approve",
            "scope": "national_ontology_and_assertions", "ontology_sha256": ontology_sha256,
            "input_graphs_sha256": {family: digest(raw) for family, raw in graphs.items()}}
    result = {f"inputs/{family}.ttl": raw for family, raw in graphs.items()}
    result.update({f"evidence/{fingerprint}.bin": raw for fingerprint, raw in physical.items()})
    result["public-review-body.json"] = canonical(body)
    result["NOTICE.json"] = canonical({"schema_version": TRANSFORMATION, "signed": False,
                                       "publication_eligible": False, "confidentiality": "firm_confidential",
                                       "purpose": "Independent review input; no publication authorization"})
    _bounded(result)
    return result
