"""Private, live publication authorization; never a legal signing authority."""

import base64
import hashlib
import importlib.util
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .config import ROOT
from .graph_release import _load_serving
from .release_preparation import compile_review
from .release_snapshot import REQUIRED_USES, SnapshotError, locked_snapshot

MAX_AUTHORIZATION = 64 * 1024
TRANSFORMATION = "reviewed-provision-promotion-v1"
ACTIONS = frozenset({"install", "activate", "rollback", "read"})
FIELDS = frozenset({"schema_version", "release_id", "serving_sha256", "ontology_sha256", "review_key_sha256",
                    "preparation_manifest_sha256", "source_binding", "audience", "permitted_uses",
                    "audience_evidence_sha256", "publication_epoch", "approved_at", "expires_at", "reviewer", "decision",
                    "transformation"})


class AuthorizationError(ValueError):
    """Safe failure without private source selections, identities or credentials."""


def _packet_tools():
    spec = importlib.util.spec_from_file_location("legal_review_packet_reader", ROOT / "scripts" / "prepare_legal_review.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fail():
    return AuthorizationError("Current private release authorization could not be verified")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise _fail()
    return value


def _instant(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 80:
        raise _fail()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail()
    return parsed.astimezone(timezone.utc)


def _validate_body(body, tools):
    if not isinstance(body, dict) or set(body) != FIELDS:
        raise _fail()
    if (body["schema_version"] != "legal-release-authorization-v1" or body["decision"] != "approve"
            or body["transformation"] != TRANSFORMATION
            or body["audience"] != "deployment_shared" or body["permitted_uses"] != sorted(REQUIRED_USES)
            or not isinstance(body["source_binding"], dict)
            or not isinstance(body["reviewer"], str) or not 1 <= len(body["reviewer"]) <= 300
            or body["reviewer"] != body["reviewer"].strip()
            or any(ord(char) < 32 for char in body["reviewer"])):
        raise _fail()
    for field in ("release_id", "serving_sha256", "ontology_sha256", "review_key_sha256",
                  "preparation_manifest_sha256", "audience_evidence_sha256"):
        if not isinstance(body[field], str) or not tools.HASH.fullmatch(body[field]):
            raise _fail()
    _uuid(body["publication_epoch"])
    approved, expires = _instant(body["approved_at"]), _instant(body["expires_at"])
    now = datetime.now(timezone.utc)
    if approved > now or expires <= now or expires <= approved or expires - approved > timedelta(days=90):
        raise _fail()
    return body


def build_authorization_body(info, packet_files, packet_digest, epoch, reviewer, approved_at, expires_at,
                             audience_evidence_sha256):
    """Build a private unsigned request; never approve, sign or generate a key."""
    try:
        tools = _packet_tools()
        binding = tools.parse_json(packet_files["binding.json"])
        body = {"schema_version": "legal-release-authorization-v1", "release_id": info["release_id"],
                "serving_sha256": info["serving_sha256"], "ontology_sha256": info["ontology_sha256"],
                "review_key_sha256": info["review"]["key_sha256"], "preparation_manifest_sha256": packet_digest,
                "source_binding": binding, "audience": "deployment_shared", "permitted_uses": sorted(REQUIRED_USES),
                "audience_evidence_sha256": audience_evidence_sha256, "publication_epoch": epoch,
                "reviewer": reviewer, "approved_at": approved_at, "expires_at": expires_at, "decision": "approve",
                "transformation": TRANSFORMATION}
        _validate_body(body, tools)
        if _instant(approved_at) < _instant(info["review"]["reviewed_at"]):
            raise _fail()
        evidence = packet_files.get(f"private-evidence/{audience_evidence_sha256}.bin")
        if evidence is None or _hash(evidence) != audience_evidence_sha256:
            raise _fail()
        return body
    except (ValueError, TypeError, KeyError, OSError, ImportError, AttributeError, RecursionError):
        raise _fail() from None


class ReleaseAuthorization:
    def __init__(self, store, source_store, root, trusted_key, ontology_root, epoch_path):
        self.store, self.source_store = store, source_store
        self.root = Path(root) if root else None
        self.trusted_key = Path(trusted_key) if trusted_key else None
        self.ontology_root = Path(ontology_root)
        self.epoch_path = Path(epoch_path) if epoch_path else None

    def __call__(self, info, action):
        return self.guard(info, action)

    def _load(self, info, action, tools):
        if action not in ACTIONS or not self.root or not self.trusted_key or not self.epoch_path:
            raise _fail()
        if not isinstance(info, dict) or not isinstance(info.get("release_id"), str) or not tools.HASH.fullmatch(info["release_id"]):
            raise _fail()
        directory = tools.checked_path(self.root / info["release_id"])
        authorization = tools.read_file(directory / "authorization.json", MAX_AUTHORIZATION)
        envelope = tools.parse_json(authorization)
        if (not isinstance(envelope, dict) or set(envelope) != {"algorithm", "body", "signature"}
                or envelope["algorithm"] != "Ed25519" or not isinstance(envelope["signature"], str)):
            raise _fail()
        body = _validate_body(envelope["body"], tools)
        key_bytes = tools.read_file(self.trusted_key, 16384)
        key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(key, Ed25519PublicKey):
            raise _fail()
        raw_key = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        signature = base64.b64decode(envelope["signature"], validate=True)
        if len(signature) != 64:
            raise _fail()
        key.verify(signature, tools.canonical(body))
        if (info.get("review", {}).get("verified") is not True or body["review_key_sha256"] != _hash(raw_key)
                or body["review_key_sha256"] != info["review"].get("key_sha256")
                or any(body[field] != info.get(field) for field in ("release_id", "serving_sha256", "ontology_sha256"))):
            raise _fail()
        if _instant(body["approved_at"]) < _instant(info["review"]["reviewed_at"]):
            raise _fail()
        epoch_bytes = tools.read_file(self.epoch_path, 37)
        epoch = epoch_bytes.decode("ascii").removesuffix("\n")
        if _uuid(epoch) != body["publication_epoch"]:
            raise _fail()
        files, packet_digest = tools.read_packet(directory / "packet", self.store)
        if packet_digest != body["preparation_manifest_sha256"] or tools.parse_json(files["binding.json"]) != body["source_binding"]:
            raise _fail()
        audience_evidence = files.get(f"private-evidence/{body['audience_evidence_sha256']}.bin")
        if audience_evidence is None or _hash(audience_evidence) != body["audience_evidence_sha256"]:
            raise _fail()
        # Validate prepared public bytes independently; a supplied info dict is
        # not itself an attestation or a complete source-coverage proof.
        bundle = tools.checked_path(info["bundle_path"])
        verified = _load_serving().validate_prepared(bundle.parent, self.trusted_key)
        if any(verified.get(field) != info.get(field) for field in ("release_id", "serving_sha256", "ontology_sha256", "review")):
            raise _fail()
        return {"body": body, "files": files, "authorization": authorization, "epoch_bytes": epoch_bytes,
                "key_bytes": key_bytes, "packet_digest": packet_digest, "bundle": bundle}

    def _public_match(self, current, info, tools):
        # Imported lazily: promotion transforms exact reviewed candidate bytes;
        # it must never receive the private authorization identity or evidence.
        from .release_promotion import promoted_graphs

        files, bundle = current["files"], current["bundle"]
        expected_graphs = promoted_graphs(files, info["review"]["reviewer"], info["review"]["reviewed_at"])
        if set(expected_graphs) != {"structure", "jurisprudence"}:
            raise _fail()
        for family, expected in expected_graphs.items():
            if tools.read_file(bundle / "inputs" / f"{family}.ttl", tools.MAX_FILE) != expected:
                raise _fail()
        evidence = {_hash(files[name]): files[name] for name in ("candidate/raw.bin", "candidate/text.txt", "candidate/locators.json")}
        expected_files = {f"evidence/{digest}.bin" for digest in evidence}
        for digest, raw in evidence.items():
            if tools.read_file(bundle / "evidence" / f"{digest}.bin", tools.MAX_FILE) != raw:
                raise _fail()
        release = _load_serving()._release
        expected_files |= {"ontology/" + str(path.relative_to(self.ontology_root))
                           for path in release.ontology_files(self.ontology_root)}
        expected_files |= {f"inputs/{family}.ttl" for family in expected_graphs}
        expected_files |= {f"graphs/{family}.{partition}.ttl" for family in expected_graphs for partition in ("proposed", "reviewed")}
        expected_files.add("review-attestation.json")
        manifest = tools.parse_json(tools.read_file(bundle / "manifest.json", tools.MAX_JSON))
        if set(manifest["files"]) != expected_files:
            raise _fail()

    @contextmanager
    def guard(self, info, action):
        try:
            tools = _packet_tools()
            # Routing is not authorization: each exact schema independently
            # verifies its signature, packet and live source state. Never retry a
            # rejected source-set authorization through the legacy policy.
            if (self.root and isinstance(info, dict) and isinstance(info.get("release_id"), str)
                    and tools.HASH.fullmatch(info["release_id"])):
                envelope = tools.parse_json(tools.read_file(
                    self.root / info["release_id"] / "authorization.json", MAX_AUTHORIZATION))
                if (isinstance(envelope, dict) and isinstance(envelope.get("body"), dict)
                        and envelope["body"].get("schema_version") == "legal-release-source-set-authorization-v1"):
                    from .release_set_authorization import ReleaseSetAuthorization

                    guard = ReleaseSetAuthorization(self.store, self.source_store, self.root, self.trusted_key,
                                                    self.ontology_root, self.epoch_path)
                    with guard.guard(info, action) as receipt:
                        yield receipt
                    return
            current = self._load(info, action, tools)
            binding = current["body"]["source_binding"]
            with locked_snapshot(self.store, self.source_store, operator_id=binding["operator_id"],
                                 source_id=binding["source_id"],
                                 expected_source_review_revision=binding["source_review_revision"],
                                 expected_mapping_revision=binding["mapping_revision"], shared=action == "read") as snapshot:
                if snapshot["binding"] != binding:
                    raise _fail()
                approved = _instant(current["body"]["approved_at"])
                if any(_instant(event["created_at"]) > approved for event in (
                        *snapshot["source_review"]["assessments"].values(),
                        *(item["last_event"] for item in snapshot["state"]["items"]))):
                    raise _fail()
                files = current["files"]
                evidence = {Path(name).stem: raw for name, raw in files.items() if name.startswith("private-evidence/")}
                rebuilt, summary = compile_review(snapshot, tools.parse_json(files["registry.json"]),
                                                   tools.parse_json(files["resolutions.json"]), evidence, self.ontology_root)
                if files != rebuilt or summary.get("rdf_generated") is not True:
                    raise _fail()
                self._public_match(current, info, tools)
                yield {"release_id": info["release_id"], "current": True}
                final = self._load(info, action, tools)
                if any(final[key] != current[key] for key in ("authorization", "epoch_bytes", "key_bytes", "packet_digest", "files")):
                    raise _fail()
                self._public_match(final, info, tools)
        except (ValueError, TypeError, KeyError, OSError, ImportError, AttributeError, InvalidSignature, SnapshotError,
                RecursionError):
            raise _fail() from None
