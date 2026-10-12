"""Private signed component-inclusion grants, never national serving authority.

Deployment trust is configured independently of the Graph B review and public
assertion keys. Every use reconstructs all current sources and reviews under
locks. No signature creator, inference, graph transition, or namespace fallback.
"""
import base64
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from .graph_b_publication import (
    PACKET_SCHEMA,
    REQUEST_SCHEMA,
    match_public_component,
    permission_request,
    private_evidence,
    verify_files,
)
from .graph_b_review import configured_key_path
from .graph_b_snapshot import SnapshotRequest, locked_graph_b_snapshot
from .release_authorization import _packet_tools, _uuid
from .release_preparation import canonical
from .release_snapshot import SnapshotError

SCHEMA = "graph-b-component-grant-v1"
MAX_ENVELOPE = 128 * 1024
REQUEST_FIELDS = frozenset({"schema_version", "scope", "decision", "signed", "national_release_serving_authorized",
    "component_release_id", "component_serving_sha256", "ontology_sha256", "public_review_key_sha256",
    "preparation_manifest_sha256", "source_binding", "public_inventory", "publication_epoch",
    "reviewer", "approved_at", "expires_at", "source_permissions"})
NOTICE = canonical({"schema_version": SCHEMA, "confidentiality": "firm_confidential",
    "scope": "component_inclusion_only", "national_release_serving_authorized": False})


class ComponentGrantError(ValueError):
    """Safe failure; no source selections, credential proofs or identities."""


def invalid():
    return ComponentGrantError("Current signed Graph B component inclusion permission could not be verified")


def grant_body(request, key_sha256):
    """Construct unsigned signing INPUTS; this function never creates a signature."""
    if (type(request) is not dict or set(request) != REQUEST_FIELDS or request["schema_version"] != REQUEST_SCHEMA
            or request["scope"] != "component_inclusion_only" or request["signed"] is not False
            or request["national_release_serving_authorized"] is not False):
        raise invalid()
    if type(key_sha256) is not str or not _packet_tools().HASH.fullmatch(key_sha256):
        raise invalid()
    return {**request, "schema_version": SCHEMA, "signed": True, "component_grant_key_sha256": key_sha256}


def verify_envelope(raw, trusted_key):
    tools = _packet_tools()
    if type(raw) is not bytes or len(raw) > MAX_ENVELOPE:
        raise invalid()
    envelope = tools.parse_json(raw)
    if (type(envelope) is not dict or set(envelope) != {"algorithm", "body", "signature"}
            or envelope["algorithm"] != "Ed25519" or type(envelope["signature"]) is not str
            or type(envelope["body"]) is not dict or set(envelope["body"]) != REQUEST_FIELDS | {"component_grant_key_sha256"}
            or envelope["body"]["schema_version"] != SCHEMA or envelope["body"]["signed"] is not True
            or envelope["body"]["national_release_serving_authorized"] is not False):
        raise invalid()
    key_bytes, key, key_sha = configured_key_path(trusted_key)
    signature = base64.b64decode(envelope["signature"], validate=True)
    if len(signature) != 64 or envelope["body"]["component_grant_key_sha256"] != key_sha:
        raise invalid()
    key.verify(signature, canonical(envelope["body"]))
    return envelope, key_bytes, key_sha


def match_grant(raw, trusted_key, files, fingerprint, private, snapshot, info, epoch):
    envelope, key_bytes, key_sha = verify_envelope(raw, trusted_key)
    body = envelope["body"]
    request = permission_request(files, private, snapshot, info, packet_sha256=fingerprint, epoch=epoch,
        reviewer=body["reviewer"], approved_at=body["approved_at"], expires_at=body["expires_at"],
        source_permissions=body["source_permissions"])
    if body != grant_body(request, key_sha):
        raise invalid()
    return envelope, key_bytes


def retained_files(store, packet_files, raw):
    """Retain the original sealed preparation, encrypt the entire signed grant."""
    sealed = _packet_tools().sealed_files(packet_files, store, schema_version=PACKET_SCHEMA)
    return {"grant.fernet": store.seal_preparation(_packet_tools().parse_json(raw)), "NOTICE.json": NOTICE,
            **{"preparation/" + name: value for name, value in sealed.items()}}


class GraphBComponentGrant:
    def __init__(self, store, source_store, *, public_review_key, component_grant_key,
                 graph_b_review_key, ontology_root, epoch_path):
        self.store, self.source_store = store, source_store
        self.public_review_key = Path(public_review_key) if public_review_key else None
        self.component_grant_key = component_grant_key
        self.graph_b_review_key, self.ontology_root, self.epoch_path = graph_b_review_key, ontology_root, epoch_path

    @contextmanager
    def guard(self, info, grant, *, purpose="inspect"):
        """Inspect or include a component. Install/activate/rollback/read are denied.

        The caller must discard dependent output if exit fails. A complete release
        assembler must additionally verify every other component and final review.
        """
        try:
            if purpose not in {"inspect", "include"}:
                raise invalid()
            tools = _packet_tools()
            public_key = tools.read_file(self.public_review_key, 16384)
            graph_key = tools.read_file(self.graph_b_review_key, 16384)
            if len({configured_key_path(path)[2] for path in
                    (self.public_review_key, self.graph_b_review_key, self.component_grant_key)}) != 3:
                raise invalid()
            outer, outer_digest = tools.read_packet(grant, self.store, schema_version=PACKET_SCHEMA)
            raw = canonical(self.store.decode(SimpleNamespace(payload=outer["grant.fernet"].decode("ascii"))))
            envelope, grant_key, _ = verify_envelope(raw, self.component_grant_key)
            files, fingerprint = tools.read_packet(tools.checked_path(grant) / "preparation", self.store, schema_version=PACKET_SCHEMA)
            # Require the complete closed nested inventory, including the exact
            # original preparation seal. Extra encrypted files are not tolerated.
            expected = {"grant.fernet": outer["grant.fernet"], "NOTICE.json": NOTICE,
                **{"preparation/" + name: value for name, value in tools.sealed_files(files, self.store, schema_version=PACKET_SCHEMA).items()}}
            if outer != expected:
                raise invalid()
            private = private_evidence(self.store, files)
            selection = SnapshotRequest.model_validate(private["binding"]["selection"])
            epoch_bytes = tools.read_file(self.epoch_path, 37)
            epoch = _uuid(epoch_bytes.decode("ascii").removesuffix("\n"))
            original_body = canonical(envelope["body"])
            with locked_graph_b_snapshot(self.store, self.source_store,
                    operator_id=private["binding"]["operator_id"], request=selection,
                    trusted_key=self.graph_b_review_key, ontology_root=self.ontology_root, shared=purpose == "inspect") as snapshot:
                private = verify_files(self.store, files, snapshot, self.ontology_root)
                verified = match_public_component(files, info, self.public_review_key, self.ontology_root)
                match_grant(raw, self.component_grant_key, files, fingerprint, private, snapshot, verified, epoch)
                yield {"component_release_id": verified["release_id"], "current": True,
                       "scope": "component_inclusion_only", "national_release_serving_authorized": False}
                final = match_public_component(files, info, self.public_review_key, self.ontology_root)
                checked, final_key = match_grant(raw, self.component_grant_key, files, fingerprint, private, snapshot, final, epoch)
                if (final_key != grant_key or canonical(checked["body"]) != original_body
                        or tools.read_file(self.public_review_key, 16384) != public_key
                        or tools.read_file(self.graph_b_review_key, 16384) != graph_key
                        or tools.read_file(self.epoch_path, 37) != epoch_bytes
                        or tools.read_packet(grant, self.store, schema_version=PACKET_SCHEMA) != (outer, outer_digest)):
                    raise invalid()
            # Expiry, keys and durable bytes can change while exit reconstructs
            # the original source ledgers. Check these again AFTER that work.
            final = match_public_component(files, info, self.public_review_key, self.ontology_root)
            match_grant(raw, self.component_grant_key, files, fingerprint, private, snapshot, final, epoch)
            if (tools.read_file(self.component_grant_key, 16384) != grant_key
                    or tools.read_file(self.public_review_key, 16384) != public_key
                    or tools.read_file(self.graph_b_review_key, 16384) != graph_key
                    or tools.read_file(self.epoch_path, 37) != epoch_bytes
                    or tools.read_packet(grant, self.store, schema_version=PACKET_SCHEMA) != (outer, outer_digest)):
                raise invalid()
        except (ValueError, TypeError, KeyError, AttributeError, OSError, HTTPException, InvalidSignature, InvalidToken, SnapshotError):
            raise invalid() from None
