"""Externally signed WHOLE declared release permission and live serving guards.

No signer or remotely exposed mutation API. A public signature alone, a candidate
request, component grant or private MAC never authorizes serving. Every operation
reconstructs the complete original corpus in one ordered transaction.
"""
import base64
import fcntl
import importlib.util
import os
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .config import ROOT
from .declared_graph_assembly import VerifiedServingContext, _public_capture
from .graph_b_review import configured_key_path
from .graph_release import _load_serving
from .release_authorization import ACTIONS, AuthorizationError, _packet_tools
from .release_preparation import canonical
from .release_snapshot import SnapshotError, readonly_store

SCHEMA = "legal-final-release-authorization-v1"
NOTICE = canonical({"schema_version": SCHEMA, "confidentiality": "firm_confidential"})


def commands():
    spec = importlib.util.spec_from_file_location("legal_final_candidate_commands", ROOT / "scripts/prepare_final_graph_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route(ident):
    return {"schema_version": SCHEMA, "release_id": ident}


def approval_body(request):
    """Unsigned external signing input only. Acceptance verifies every field."""
    command = commands()
    if (type(request) is not dict or request.get("schema_version") != command.SCHEMA
            or request.get("decision") != "request" or request.get("signed") is not False
            or request.get("national_release_serving_authorized") is not False):
        raise ValueError("Exact unsigned whole-release request required")
    return {**request, "schema_version": SCHEMA, "decision": "approve", "signed": True,
            "national_release_serving_authorized": True}


def verify_envelope(raw, settings):
    tools, command = _packet_tools(), commands()
    envelope = tools.parse_json(raw)
    if (type(envelope) is not dict or set(envelope) != {"algorithm", "body", "signature"}
            or envelope["algorithm"] != "Ed25519" or type(envelope["signature"]) is not str):
        raise ValueError("Independent whole-release envelope required")
    key = command.grant_trust(settings)[1]
    signature = base64.b64decode(envelope["signature"], validate=True)
    if len(signature) != 64:
        raise ValueError("Exact external Ed25519 signature required")
    load_pem_public_key(key[1]).verify(signature, canonical(envelope["body"]))
    return envelope["body"], key


def candidate_inputs(settings, store, candidate):
    command, io = commands(), _packet_tools()
    candidate = io.checked_path(candidate)
    command._outer(candidate)
    files, packet_hash = io.read_packet(candidate / "permission", store)
    if set(files) != {"binding.fernet", "request.fernet", "NOTICE.json"} or files["NOTICE.json"] != command.NOTICE:
        raise ValueError("Exact candidate permission inventory required")
    binding = store.decode(SimpleNamespace(payload=files["binding.fernet"].decode("ascii")))
    request = store.decode(SimpleNamespace(payload=files["request.fernet"].decode("ascii")))
    if type(binding) is not dict or set(binding) != {"reviewed_packet", "reviewed_packet_sha256"}:
        raise ValueError("Exact original assembly binding required")
    return command, candidate, files, packet_hash, binding, request


def match(settings, command, candidate, request, files, loaded, info, packet_hash, verified_public):
    command.verify_captured_attestation(files, loaded, verified_public)
    candidate_info = verified_public.info
    if any(candidate_info[name] != info[name] for name in ("release_id", "serving_sha256", "ontology_sha256", "review", "graphs")):
        raise ValueError("Complete serving payload differs from approved candidate")
    expected = command.request_body(settings, files, loaded, candidate_info, packet_hash,
                                   request["reviewer"], request["approved_at"], request["expires_at"])
    if canonical(request) != canonical(expected):
        raise ValueError("Whole-release permission request differs")
    return _public_capture(candidate_info)


class FinalReleaseAuthorization:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def guard(self, info, action):
        try:
            with self._guard(info, action) as result:
                yield result
        except (ValueError, TypeError, KeyError, OSError, ImportError, AttributeError, InvalidSignature, SnapshotError,
                RecursionError):
            # Do not reveal selections, identities, paths, DB state or envelope.
            raise AuthorizationError("Current whole-release permission could not be verified") from None

    @contextmanager
    def _guard(self, info, action):
        settings, tools, serving = self.settings, _packet_tools(), _load_serving()
        if action not in ACTIONS or not tools.HASH.fullmatch(info["release_id"]):
            raise ValueError("Unsupported final release operation")
        root = tools.checked_path(settings.graph_release_dir)
        directory = settings.data_dir / "release-authorizations" / info["release_id"]
        with readonly_store(settings) as reader:
            retained, retained_hash = tools.read_packet(directory, reader)
            if set(retained) != {"authorization.json", "grant.fernet", "binding.fernet", "NOTICE.json"}:
                raise ValueError("Exact whole-release authorization inventory required")
            if retained["NOTICE.json"] != NOTICE or tools.parse_json(retained["authorization.json"]) != route(info["release_id"]):
                raise ValueError("Unknown whole-release namespace")
            raw = canonical(reader.decode(SimpleNamespace(payload=retained["grant.fernet"].decode("ascii"))))
            body, key = verify_envelope(raw, settings)
            private = reader.decode(SimpleNamespace(payload=retained["binding.fernet"].decode("ascii")))
            if type(private) is not dict or set(private) != {"candidate", "permission_sha256", "original_pointer_sha256"}:
                raise ValueError("Exact retained whole-release binding required")
            command, candidate, permission, permission_hash, binding, request = candidate_inputs(settings, reader, private["candidate"])
            if permission_hash != private["permission_sha256"] or canonical(body) != canonical(approval_body(request)):
                raise ValueError("Whole-release signature must approve the exact original request")
        verified_public = command.verify_public_payload(candidate / "prepared", command.grant_trust(settings)[0][0][3])
        transition = info.get("_transition")
        if action in {"activate", "rollback"}:
            if type(transition) is not dict or set(transition) != {"before", "after", "action", "descriptor"} or transition["action"] != action:
                raise ValueError("Publisher transition context required")
            descriptor = transition["descriptor"]
            if type(descriptor) is not int or descriptor < 0:
                raise ValueError("Held publication descriptor required")
            before, after = transition["before"], transition["after"]
            wanted = {"format_version": 1, "release_id": info["release_id"], "serving_sha256": info["serving_sha256"],
                      "previous_release_id": before["release_id"] if before else None, "sequence": before["sequence"] + 1 if before else 1}
            if (after != wanted or (before and before["release_id"] == info["release_id"])
                    or (action == "rollback" and (before is None or before["previous_release_id"] != info["release_id"]))):
                raise ValueError("Exact monotonic transition required")
            publication = nullcontext(descriptor)
        else:
            if transition is not None:
                raise ValueError("Unexpected transition context")
            publication = serving.publication_lock(root, shared=True)
            before = after = None
        with publication as descriptor:
            actual_lock, held = (root / "publication.lock").stat(), os.fstat(descriptor)
            if (actual_lock.st_dev, actual_lock.st_ino) != (held.st_dev, held.st_ino):
                raise ValueError("Publication lock differs")
            if transition is not None:
                # A descriptor alone does not prove publisher exclusivity. A
                # separately opened SH probe must conflict with the held EX
                # lock. Never unlock or change the publisher's descriptor.
                probe = os.open(root / "publication.lock", os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    try:
                        fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        raise ValueError("Exclusive publication lock is not held")
                finally:
                    os.close(probe)
            pointer = serving.read_pointer(root)
            if transition is None:
                before = after = pointer
            if pointer != before:
                raise ValueError("Current publication pointer differs")
            if action == "read":
                if (settings.graph_serving_review_role != "final" or pointer is None or pointer["release_id"] != info["release_id"]
                        or pointer["serving_sha256"] != info["serving_sha256"]
                        or info["bundle_path"].parent != root / "releases" / info["release_id"]
                        or ("pointer" in info and info["pointer"] != pointer)):
                    raise ValueError("Runtime reads require the exact active installed release")
            original_public = _public_capture(info)
            context = VerifiedServingContext(info["release_id"], private["original_pointer_sha256"],
                                             canonical(before), canonical(after), descriptor)
            # No nested family guards: current_packet reconstructs BOTH families
            # under a single globally ordered transaction, including exit reads.
            with command.current_packet(settings, tools.checked_path(binding["reviewed_packet"]), reviewed=True,
                    serving_context=context, shared=action == "read", verified_public=verified_public) as (store, files, loaded):
                packet = tools.checked_path(binding["reviewed_packet"])
                _, packet_hash = tools.read_packet(packet, store, schema_version="legal-declared-graph-assembly-v1")
                if packet_hash != binding["reviewed_packet_sha256"] or canonical(body) != canonical(approval_body(request)):
                    raise ValueError("Original independent final review differs")
                public_candidate = match(settings, command, candidate, request, files, loaded, info, packet_hash, verified_public)
                if info["review"]["key_sha256"] != configured_key_path(loaded["paths"][3])[2]:
                    raise ValueError("Final serving review trust differs")
                def recheck():
                    if ((action == "read" and settings.graph_serving_review_role != "final")
                            or tools.read_packet(directory, store) != (retained, retained_hash)
                            or tools.read_packet(candidate / "permission", store) != (permission, permission_hash)
                            or _public_capture(info) != original_public
                            or _public_capture({**info, "bundle_path": candidate / "prepared/bundle"}) != public_candidate
                            or verify_envelope(raw, settings) != (body, key)
                            or command.request_body(settings, files, loaded, info, packet_hash,
                                request["reviewer"], request["approved_at"], request["expires_at"]) != request):
                        raise ValueError("Whole-release grant, trust, lifetime or bytes changed")
                    command._outer(candidate)
                recheck()
                yield {"release_id": info["release_id"], "current": True, "scope": "complete_declared_release"}
                recheck()
            # Original-ledger exit reconstruction completed. No cached verdict.
            recheck()
            if serving.read_pointer(root) != after:
                raise ValueError("Publication pointer changed at final validation")


def accept(settings, *, candidate, authorization):
    tools, created = _packet_tools(), None
    raw = tools.read_file(authorization, 64 * 1024)
    body, key = verify_envelope(raw, settings)
    output = settings.data_dir / "release-authorizations" / body["release_id"]
    try:
        with readonly_store(settings) as reader:
            command, candidate, permission, permission_hash, binding, request = candidate_inputs(settings, reader, candidate)
        if canonical(body) != canonical(approval_body(request)):
            raise ValueError("Exact external whole-release approval required")
        verified_public = command.verify_public_payload(candidate / "prepared", command.grant_trust(settings)[0][0][3])
        with command.current_packet(settings, tools.checked_path(binding["reviewed_packet"]), reviewed=True,
                verified_public=verified_public) as (store, files, loaded):
            _, packet_hash = tools.read_packet(binding["reviewed_packet"], store, schema_version="legal-declared-graph-assembly-v1")
            if canonical(body) != canonical(approval_body(request)) or packet_hash != binding["reviewed_packet_sha256"]:
                raise ValueError("Exact external whole-release approval required")
            info = verified_public.info
            public = match(settings, command, candidate, request, files, loaded, info, packet_hash, verified_public)
            private = {"candidate": str(candidate), "permission_sha256": permission_hash,
                       "original_pointer_sha256": loaded["pointer_sha256"]}
            outputs = {"authorization.json": canonical(route(info["release_id"])), "NOTICE.json": NOTICE,
                       "binding.fernet": store.seal_preparation(private),
                       "grant.fernet": store.seal_preparation(tools.parse_json(raw))}
            created = tools.atomic_packet(output, tools.sealed_files(outputs, store))
            if (tools.read_packet(candidate / "permission", store) != (permission, permission_hash)
                    or _public_capture(info) != public or verify_envelope(raw, settings) != (body, key)
                    or tools.read_file(authorization, 64 * 1024) != raw
                    or tools.read_packet(output, store)[0] != outputs):
                raise ValueError("Whole-release approval changed during acceptance")
        # The enclosing transaction already reconstructed all original ledgers
        # on exit. Repeat retained bytes/trust/lifetimes here; publication's NEXT
        # use performs its own full transaction, never reuses this verdict.
        if (tools.read_file(authorization, 64 * 1024) != raw or verify_envelope(raw, settings) != (body, key)
                or _public_capture(info) != public
                or command.request_body(settings, files, loaded, info, packet_hash,
                    request["reviewer"], request["approved_at"], request["expires_at"]) != request):
            raise ValueError("External approval changed after acceptance")
        with readonly_store(settings) as reader:
            if tools.read_packet(output, reader)[0] != outputs:
                raise ValueError("Retained approval changed after acceptance")
    except BaseException:
        tools._remove_own_output(output, created)
        raise
    return {"whole_release_authorization_accepted": True, "release_id": info["release_id"],
            "signature_created": False, "publication_performed": False}
