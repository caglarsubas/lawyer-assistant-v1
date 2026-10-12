"""Encrypted Graph B preparation and unsigned component-permission requests.

Never signs, accepts a grant, installs a graph, or authorizes national serving.
Only trusted deployment-host readers may call these functions with a live locked
snapshot. All private bindings, credential evidence and audience proof bytes are
encrypted; public graph bytes remain exact independently reviewed inputs.
"""
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from .graph_b_signing import compile_inputs
from .graph_b_snapshot import SnapshotRequest
from .graph_release import _load_serving
from .release_authorization import _instant, _packet_tools, _uuid
from .release_preparation import canonical, digest
from .release_snapshot import REQUIRED_USES

PACKET_SCHEMA = "legal-review-graph-b-packet-v1"
PRIVATE_SCHEMA = "graph-b-private-publication-evidence-v1"
REQUEST_SCHEMA = "graph-b-component-permission-request-v1"
MAX_PRIVATE = 8 * 1024 * 1024
PRIVATE_FILE = "private-evidence.fernet"
FIELDS = {"schema_version", "binding", "signed_review_event", "public_input_paths", "public_inventory", "audience_evidence"}
PERMISSION_FIELDS = {"source_id", "audience", "permitted_uses", "evidence_sha256", "expires_at"}


class PublicationPreparationError(ValueError):
    """Private material is withheld behind a generic local-operator failure."""


def invalid():
    return PublicationPreparationError("Current Graph B component preparation or source-specific permission evidence could not be verified")


def public_inputs(snapshot, ontology_root):
    result = compile_inputs(snapshot["packages"], snapshot["decisions"], snapshot["captured"], snapshot["bound"],
        snapshot["equivalence_history"][-1], snapshot["signed_review_history"][-1], ontology_root)
    data = _packet_tools().parse_json(result["evidence_json"].encode())
    files = {name: base64.b64decode(item["data"], validate=True) for name, item in data["files"].items()}
    return files, data["public_input_paths"]


def _rights(snapshot):
    return {key: next(event for event in source["source_history"] if event.get("category") == "rights")
            for key, source in snapshot["captured"]["sources"].items()}


def _audience_evidence(snapshot, evidence):
    if type(evidence) is not dict or not 1 <= len(evidence) <= 30:
        raise invalid()
    permitted = {item["sha256"] for rights in _rights(snapshot).values() for item in rights["evidence_refs"]}
    if (not set(evidence).issubset(permitted) or any(type(raw) is not bytes or not raw or digest(raw) != key
            for key, raw in evidence.items()) or sum(len(raw) for raw in evidence.values()) > MAX_PRIVATE // 2):
        raise invalid()
    if any(not set(evidence).intersection(item["sha256"] for item in rights["evidence_refs"])
           for rights in _rights(snapshot).values()):
        raise invalid()
    return {key: base64.b64encode(raw).decode() for key, raw in sorted(evidence.items())}


def prepare_files(store, snapshot, evidence, ontology_root):
    """Compile from original sources; accepts no client RDF or review override."""
    try:
        files, public_paths = public_inputs(snapshot, ontology_root)
        private = {"schema_version": PRIVATE_SCHEMA, "binding": snapshot["binding"],
            "signed_review_event": snapshot["signed_review_history"][-1], "public_input_paths": public_paths,
            "public_inventory": _packet_tools()._inventory(files), "audience_evidence": _audience_evidence(snapshot, evidence)}
        if len(canonical(private)) > MAX_PRIVATE:
            raise invalid()
        files[PRIVATE_FILE] = store.seal_preparation(private)
        _packet_tools()._inventory(files)
        return files
    except (HTTPException, ValueError, TypeError, KeyError, AttributeError, OSError):
        raise invalid() from None


def private_evidence(store, files):
    try:
        raw = files[PRIVATE_FILE]
        if type(raw) is not bytes or len(raw) > MAX_PRIVATE * 2:
            raise invalid()
        value = store.decode(SimpleNamespace(payload=raw.decode("ascii")))
        if type(value) is not dict or set(value) != FIELDS or value["schema_version"] != PRIVATE_SCHEMA:
            raise invalid()
        if len(canonical(value)) > MAX_PRIVATE:
            raise invalid()
        SnapshotRequest.model_validate(value["binding"]["selection"])
        return value
    except (InvalidToken, ValueError, TypeError, KeyError, AttributeError):
        raise invalid() from None


def verify_files(store, files, snapshot, ontology_root):
    """Compare to freshly reconstructed review, never merely a packet MAC."""
    try:
        private = private_evidence(store, files)
        expected, paths = public_inputs(snapshot, ontology_root)
        if (set(files) != {*expected, PRIVATE_FILE} or any(files[name] != raw for name, raw in expected.items())
                or private["binding"] != snapshot["binding"] or private["signed_review_event"] != snapshot["signed_review_history"][-1]
                or private["public_input_paths"] != paths or private["public_inventory"] != _packet_tools()._inventory(expected)):
            raise invalid()
        evidence = {key: base64.b64decode(raw, validate=True) for key, raw in private["audience_evidence"].items()}
        if _audience_evidence(snapshot, evidence) != private["audience_evidence"]:
            raise invalid()
        return private
    except (HTTPException, ValueError, TypeError, KeyError, AttributeError, OSError):
        raise invalid() from None


def match_public_component(files, info, trusted_review_key, ontology_root):
    """Verify the public attestation, exact six-edge inputs and full inventory.

    This is a reviewed COMPONENT, with an empty Graph A. A national release must
    assemble its other reviewed components and require all current grants.
    """
    try:
        tools, serving = _packet_tools(), _load_serving()
        verified = serving.validate_prepared(info["bundle_path"].parent, trusted_review_key)
        if any(info.get(field) != verified.get(field) for field in ("release_id", "serving_sha256", "ontology_sha256", "review")):
            raise invalid()
        bundle = tools.checked_path(info["bundle_path"])
        expected = {name: raw for name, raw in files.items() if name.startswith(("inputs/", "evidence/"))}
        if any(tools.read_file(bundle / name, tools.MAX_FILE) != raw for name, raw in expected.items()):
            raise invalid()
        names = set(expected) | {"review-attestation.json"}
        names |= {"ontology/" + str(path.relative_to(ontology_root)) for path in serving._release.ontology_files(ontology_root)}
        names |= {f"graphs/{family}.{partition}.ttl" for family in ("structure", "jurisprudence") for partition in ("proposed", "reviewed")}
        manifest = tools.parse_json(tools.read_file(bundle / "manifest.json", tools.MAX_JSON))
        template = tools.parse_json(files["public-review-body.json"])
        if (set(manifest["files"]) != names or verified["ontology_sha256"] != template["ontology_sha256"]
                or verified["review"]["verified"] is not True or _instant(verified["review"]["reviewed_at"]) < _instant(template["reviewed_at"])):
            raise invalid()
        return verified
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        raise invalid() from None


def permission_request(files, private, snapshot, info, *, packet_sha256, epoch, reviewer, approved_at, expires_at, source_permissions):
    """A closed UNSIGNED inclusion request, never a runtime authorization schema."""
    try:
        tools = _packet_tools()
        approved, expires = _instant(approved_at), _instant(expires_at)
        body = snapshot["signed_review_history"][-1]["envelope"]["body"]
        review_event = snapshot["signed_review_history"][-1]
        if (private["binding"] != snapshot["binding"] or private["signed_review_event"] != review_event
                or info["review"]["verified"] is not True or info["ontology_sha256"] != body["ontology_sha256"]
                or private["public_inventory"] != tools._inventory({name: raw for name, raw in files.items() if name != PRIVATE_FILE})
                or any(type(value) is not str or not tools.HASH.fullmatch(value) for value in
                       (info["release_id"], info["serving_sha256"], info["review"]["key_sha256"]))):
            raise invalid()
        appointment_until = datetime.fromisoformat(body["appointment"]["valid_until"]).replace(tzinfo=timezone.utc)
        if (approved > datetime.now(timezone.utc) or expires <= datetime.now(timezone.utc) or expires <= approved
                or expires - approved > timedelta(days=90) or expires > appointment_until
                or approved < _instant(review_event["created_at"]) or approved < _instant(info["review"]["reviewed_at"])
                or type(reviewer) is not str or not 3 <= len(reviewer) <= 160 or reviewer != reviewer.strip()
                or any(ord(char) < 32 for char in reviewer) or not tools.HASH.fullmatch(packet_sha256)):
            raise invalid()
        _uuid(epoch)
        # Copy and validate every source independently. Matching bytes across
        # sources never imply a permission that the other source has not retained.
        permissions = tools.parse_json(canonical(source_permissions))
        identifiers = sorted(snapshot["packages"])
        if type(permissions) is not list or len(permissions) != 3:
            raise invalid()
        permissions.sort(key=lambda value: value["source_id"])
        if [value["source_id"] for value in permissions] != identifiers:
            raise invalid()
        rights = _rights(snapshot)
        for permission in permissions:
            if (type(permission) is not dict or set(permission) != PERMISSION_FIELDS
                    or permission["audience"] != "deployment_shared" or permission["permitted_uses"] != sorted(REQUIRED_USES)
                    or not expires <= _instant(permission["expires_at"]) <= approved + timedelta(days=90)
                    or permission["evidence_sha256"] not in {item["sha256"] for item in rights[permission["source_id"]]["evidence_refs"]}
                    or permission["evidence_sha256"] not in private["audience_evidence"]):
                raise invalid()
        if any(_instant(event["created_at"]) > approved for source in snapshot["captured"]["sources"].values()
               for event in source["source_history"] + source["mapping_history"]):
            raise invalid()
        result = {"schema_version": REQUEST_SCHEMA, "scope": "component_inclusion_only", "decision": "approve",
            "signed": False, "national_release_serving_authorized": False,
            "component_release_id": info["release_id"], "component_serving_sha256": info["serving_sha256"],
            "ontology_sha256": info["ontology_sha256"], "public_review_key_sha256": info["review"]["key_sha256"],
            "preparation_manifest_sha256": packet_sha256, "source_binding": private["binding"],
            "public_inventory": private["public_inventory"], "publication_epoch": epoch,
            "reviewer": reviewer, "approved_at": approved_at, "expires_at": expires_at,
            "source_permissions": permissions}
        if len(canonical(result)) > 64 * 1024:
            raise invalid()
        return result
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        raise invalid() from None
