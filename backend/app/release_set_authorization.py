"""Exact, independently signed publication permission for a reviewed source set.

All source permissions are conjunctive. A missing, expired or revoked member
invalidates the entire dependent release. This module never signs or renews an
authorization, changes source reviews, or broadens deployment audience rights.
"""

import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .graph_release import _load_serving
from .release_authorization import (
    ACTIONS,
    MAX_AUTHORIZATION,
    ReleaseAuthorization,
    _fail,
    _hash,
    _instant,
    _packet_tools,
    _uuid,
)
from .release_authorization import (
    AuthorizationError as AuthorizationError,
)
from .release_preparation import canonical
from .release_set_preparation import compile_review_set
from .release_snapshot import REQUIRED_USES, SnapshotError
from .release_snapshot_set import SnapshotSetRequest, locked_snapshot_set

SCHEMA = "legal-release-source-set-authorization-v1"
PACKET_SCHEMA = "legal-review-source-set-packet-v1"
TRANSFORMATION = "reviewed-provision-set-promotion-v1"
FIELDS = frozenset({"schema_version", "release_id", "serving_sha256", "ontology_sha256", "review_key_sha256",
                    "preparation_manifest_sha256", "source_binding", "audience", "permitted_uses",
                    "source_permissions", "publication_epoch", "approved_at", "expires_at", "reviewer", "decision",
                    "transformation"})
PERMISSION_FIELDS = frozenset({"source_id", "audience", "permitted_uses", "evidence_sha256", "expires_at"})
BINDING_FIELDS = frozenset({"schema_version", "source_id", "source_version_id", "source_artifacts", "firm_id",
                          "operator_id", "source_review_head_id", "mapping_head_id", "source_review_revision",
                          "mapping_revision", "projections_sha256"})


def _selection(binding, tools):
    if (type(binding) is not dict or set(binding) != {
            "schema_version", "firm_id", "operator_id", "sources", "publication_eligible"}
            or binding["schema_version"] != "legal-review-snapshot-set-v1"
            or binding["publication_eligible"] is not False or type(binding["sources"]) is not list
            or not 2 <= len(binding["sources"]) <= 8
            or any(type(binding[field]) is not str or not 1 <= len(binding[field]) <= 64
                   for field in ("firm_id", "operator_id"))):
        raise _fail()
    for source in binding["sources"]:
        if (type(source) is not dict or set(source) != BINDING_FIELDS
                or source["schema_version"] != "legal-review-snapshot-v1"
                or source["firm_id"] != binding["firm_id"] or source["operator_id"] != binding["operator_id"]
                or type(source["projections_sha256"]) is not str
                or not tools.HASH.fullmatch(source["projections_sha256"])):
            raise _fail()
    request = SnapshotSetRequest.model_validate({
        "schema_version": "legal-review-source-selection-v1", "sources": [
            {"source_id": source["source_id"], "expected_source_review_revision": source["source_review_revision"],
             "expected_mapping_revision": source["mapping_revision"]} for source in binding["sources"]]})
    identifiers = [source.source_id for source in request.sources]
    if identifiers != sorted(identifiers):
        raise _fail()
    return request


def _validate_body(body, tools):
    if type(body) is not dict or set(body) != FIELDS:
        raise _fail()
    if (body["schema_version"] != SCHEMA or body["decision"] != "approve"
            or body["transformation"] != TRANSFORMATION or body["audience"] != "deployment_shared"
            or body["permitted_uses"] != sorted(REQUIRED_USES)
            or type(body["reviewer"]) is not str or not 1 <= len(body["reviewer"]) <= 300
            or body["reviewer"] != body["reviewer"].strip() or any(ord(char) < 32 for char in body["reviewer"])):
        raise _fail()
    for field in ("release_id", "serving_sha256", "ontology_sha256", "review_key_sha256", "preparation_manifest_sha256"):
        if type(body[field]) is not str or not tools.HASH.fullmatch(body[field]):
            raise _fail()
    _uuid(body["publication_epoch"])
    approved, expires = _instant(body["approved_at"]), _instant(body["expires_at"])
    now = datetime.now(timezone.utc)
    if approved > now or expires <= now or expires <= approved or expires - approved > timedelta(days=90):
        raise _fail()
    request = _selection(body["source_binding"], tools)
    permissions = body["source_permissions"]
    if type(permissions) is not list or len(permissions) != len(request.sources):
        raise _fail()
    for source, permission in zip(request.sources, permissions, strict=True):
        if (type(permission) is not dict or set(permission) != PERMISSION_FIELDS
                or permission["source_id"] != source.source_id or permission["audience"] != "deployment_shared"
                or permission["permitted_uses"] != sorted(REQUIRED_USES)
                or type(permission["evidence_sha256"]) is not str
                or not tools.HASH.fullmatch(permission["evidence_sha256"])
                or not expires <= _instant(permission["expires_at"]) <= approved + timedelta(days=90)):
            raise _fail()
    return body


def _permission_bytes(body, files):
    for permission in body["source_permissions"]:
        evidence = files.get(f"private-evidence/{permission['evidence_sha256']}.bin")
        if type(evidence) is not bytes or _hash(evidence) != permission["evidence_sha256"]:
            raise _fail()


def build_set_authorization_body(info, packet_files, packet_digest, epoch, reviewer, approved_at, expires_at,
                                 source_permissions):
    """Build unsigned private signing input; live checks remain mandatory."""
    try:
        tools = _packet_tools()
        if type(source_permissions) is not list or not 2 <= len(source_permissions) <= 8:
            raise _fail()
        permissions = sorted(tools.parse_json(canonical(source_permissions)), key=lambda item: item["source_id"])
        body = {"schema_version": SCHEMA, "release_id": info["release_id"],
                "serving_sha256": info["serving_sha256"], "ontology_sha256": info["ontology_sha256"],
                "review_key_sha256": info["review"]["key_sha256"], "preparation_manifest_sha256": packet_digest,
                "source_binding": tools.parse_json(packet_files["binding.json"]), "audience": "deployment_shared",
                "permitted_uses": sorted(REQUIRED_USES), "source_permissions": permissions,
                "publication_epoch": epoch, "reviewer": reviewer, "approved_at": approved_at,
                "expires_at": expires_at, "decision": "approve", "transformation": TRANSFORMATION}
        _validate_body(body, tools)
        if info["review"].get("verified") is not True or _instant(approved_at) < _instant(info["review"]["reviewed_at"]):
            raise _fail()
        _permission_bytes(body, packet_files)
        raw = canonical(body)
        if len(raw) + 256 > MAX_AUTHORIZATION:  # Reserve the strict Ed25519 envelope overhead.
            raise _fail()
        return tools.parse_json(raw)  # Caller mutation cannot alter retained input structures.
    except (ValueError, TypeError, KeyError, OSError, ImportError, AttributeError, RecursionError):
        raise _fail() from None


def validate_source_permissions(body, snapshot_set):
    """Bind every permission to that source's current rights and review time."""
    try:
        _validate_body(body, _packet_tools())
        if canonical(snapshot_set["binding"]) != canonical(body["source_binding"]):
            raise _fail()
        snapshots = {item["binding"]["source_id"]: item for item in snapshot_set["snapshots"]}
        if len(snapshots) != len(snapshot_set["snapshots"]) or set(snapshots) != {
                item["source_id"] for item in body["source_permissions"]}:
            raise _fail()
        approved = _instant(body["approved_at"])
        for permission in body["source_permissions"]:
            source = snapshots[permission["source_id"]]
            rights = source["source_review"]["assessments"]["rights"]
            if (rights["decision"] != "accepted" or not REQUIRED_USES.issubset(rights["permitted_uses"])
                    or permission["evidence_sha256"] not in {item["sha256"] for item in rights["evidence_refs"]}):
                raise _fail()
            if any(_instant(event["created_at"]) > approved for event in (
                    *source["source_review"]["assessments"].values(),
                    *(item["last_event"] for item in source["state"]["items"]))):
                raise _fail()
    except (ValueError, TypeError, KeyError, OSError, ImportError, AttributeError, RecursionError):
        raise _fail() from None


def match_public_bundle(files, info, ontology_root):
    """Match an independently validated public bundle to exact private inputs."""
    from .release_set_promotion import promoted_graphs, public_evidence

    try:
        tools = _packet_tools()
        ontology_root = Path(ontology_root)
        release = _load_serving()._release
        ontology_sha = release.ontology_digest(ontology_root)
        report = tools.parse_json(files["review-report.json"])
        if (report["input_digests"]["ontology_sha256"] != ontology_sha
                or info["ontology_sha256"] != ontology_sha):
            raise _fail()
        bundle = tools.checked_path(info["bundle_path"])
        graphs = promoted_graphs(files, info["review"]["reviewer"], info["review"]["reviewed_at"])
        if set(graphs) != {"structure", "jurisprudence"}:
            raise _fail()
        for family, raw in graphs.items():
            if tools.read_file(bundle / "inputs" / f"{family}.ttl", tools.MAX_FILE) != raw:
                raise _fail()
        evidence = public_evidence(files)
        expected_files = {f"evidence/{fingerprint}.bin" for fingerprint in evidence}
        for fingerprint, raw in evidence.items():
            if tools.read_file(bundle / "evidence" / f"{fingerprint}.bin", tools.MAX_FILE) != raw:
                raise _fail()
        expected_files |= {"ontology/" + str(path.relative_to(ontology_root)) for path in release.ontology_files(ontology_root)}
        expected_files |= {f"inputs/{family}.ttl" for family in graphs}
        expected_files |= {f"graphs/{family}.{partition}.ttl" for family in graphs for partition in ("proposed", "reviewed")}
        expected_files.add("review-attestation.json")
        manifest = tools.parse_json(tools.read_file(bundle / "manifest.json", tools.MAX_JSON))
        if set(manifest["files"]) != expected_files:
            raise _fail()
    except (ValueError, TypeError, KeyError, OSError, ImportError, AttributeError, RecursionError):
        raise _fail() from None


class ReleaseSetAuthorization(ReleaseAuthorization):
    """The existing guard interface, with conjunctive source-set authorization."""

    def _load(self, info, action, tools):
        if action not in ACTIONS or not self.root or not self.trusted_key or not self.epoch_path:
            raise _fail()
        if type(info) is not dict or type(info.get("release_id")) is not str or not tools.HASH.fullmatch(info["release_id"]):
            raise _fail()
        directory = tools.checked_path(self.root / info["release_id"])
        authorization = tools.read_file(directory / "authorization.json", MAX_AUTHORIZATION)
        envelope = tools.parse_json(authorization)
        if (type(envelope) is not dict or set(envelope) != {"algorithm", "body", "signature"}
                or envelope["algorithm"] != "Ed25519" or type(envelope["signature"]) is not str):
            raise _fail()
        body = _validate_body(envelope["body"], tools)
        key_bytes = tools.read_file(self.trusted_key, 16384)
        key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(key, Ed25519PublicKey):
            raise _fail()
        signature = base64.b64decode(envelope["signature"], validate=True)
        if len(signature) != 64:
            raise _fail()
        key.verify(signature, canonical(body))
        raw_key = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if (info.get("review", {}).get("verified") is not True or body["review_key_sha256"] != _hash(raw_key)
                or body["review_key_sha256"] != info["review"].get("key_sha256")
                or any(body[field] != info.get(field) for field in ("release_id", "serving_sha256", "ontology_sha256"))
                or _instant(body["approved_at"]) < _instant(info["review"]["reviewed_at"])):
            raise _fail()
        epoch_bytes = tools.read_file(self.epoch_path, 37)
        if _uuid(epoch_bytes.decode("ascii").removesuffix("\n")) != body["publication_epoch"]:
            raise _fail()
        files, packet_digest = tools.read_packet(directory / "packet", self.store, schema_version=PACKET_SCHEMA)
        if (packet_digest != body["preparation_manifest_sha256"]
                or canonical(tools.parse_json(files["binding.json"])) != canonical(body["source_binding"])):
            raise _fail()
        _permission_bytes(body, files)
        bundle = tools.checked_path(info["bundle_path"])
        verified = _load_serving().validate_prepared(bundle.parent, self.trusted_key)
        if any(verified.get(field) != info.get(field) for field in ("release_id", "serving_sha256", "ontology_sha256", "review")):
            raise _fail()
        return {"body": body, "files": files, "authorization": authorization, "epoch_bytes": epoch_bytes,
                "key_bytes": key_bytes, "packet_digest": packet_digest, "bundle": bundle}

    def _public_match(self, current, info, tools):
        match_public_bundle(current["files"], info, self.ontology_root)

    @contextmanager
    def guard(self, info, action):
        try:
            tools = _packet_tools()
            current = self._load(info, action, tools)
            body, files = current["body"], current["files"]
            request = _selection(body["source_binding"], tools)
            with locked_snapshot_set(self.store, self.source_store,
                                     operator_id=body["source_binding"]["operator_id"], request=request,
                                     shared=action == "read") as snapshot:
                validate_source_permissions(body, snapshot)
                evidence = {Path(name).stem: raw for name, raw in files.items() if name.startswith("private-evidence/")}
                rebuilt, summary = compile_review_set(snapshot, tools.parse_json(files["registry.json"]),
                                                       tools.parse_json(files["resolutions.json"]), evidence,
                                                       self.ontology_root)
                if files != rebuilt or summary.get("rdf_generated") is not True:
                    raise _fail()
                self._public_match(current, info, tools)
                yield {"release_id": info["release_id"], "current": True}
                final = self._load(info, action, tools)
                if any(final[key] != current[key] for key in ("authorization", "epoch_bytes", "key_bytes", "packet_digest", "files")):
                    raise _fail()
                validate_source_permissions(final["body"], snapshot)
                self._public_match(final, info, tools)
            # Public-byte and snapshot revalidation can consume time. Expiry must
            # still hold when those checks finish, not just when the last file
            # read began. This grants no reservation beyond guard completion.
            _validate_body(current["body"], tools)
        except (ValueError, TypeError, KeyError, OSError, ImportError, AttributeError, InvalidSignature, SnapshotError,
                RecursionError):
            raise _fail() from None
