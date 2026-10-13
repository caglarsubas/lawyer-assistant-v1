"""Private read-only recorded inventory and present dependency qualification.

A verified historical signature is not current permission. Receipts never
authorize serving, repair, replay, activation, or infer legal corpus coverage.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Literal

from pydantic import Field
from rdflib import Graph, URIRef
from rdflib import Literal as RDFLiteral

from . import final_release_authorization as final
from .declared_graph_assembly import PACKET_SCHEMA, BasePointer, Declaration, _public_capture
from .final_release_inspection import observation_locks
from .graph_release import _load_serving
from .public_graph_union import ASM
from .release_authorization import AuthorizationError, _packet_tools
from .release_preparation import canonical, digest
from .release_snapshot import REQUIRED_USES, readonly_store
from .retained_graph_assembly import capture_roots
from .source_reviews import StrictInput


class DependencyExpectation(StrictInput):
    schema_version: Literal["legal-retained-dependency-expectation-v1"]
    release_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    serving_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _closed_inventory(inventory):
    tools = _packet_tools()
    if (type(inventory) is not dict or set(inventory) != {"schema_version", "ontology_sha256", "components", "retained_base", "coverage_scope"}
            or inventory["schema_version"] != "declared-public-graph-inventory-v1"
            or inventory["coverage_scope"] != "declared_components_only"
            or type(inventory["components"]) is not list or not 2 <= len(inventory["components"]) <= 32):
        raise ValueError("Closed recorded declared inventory required")
    identifiers = []
    for item in inventory["components"]:
        if (type(item) is not dict or set(item) != {"release_id", "serving_sha256", "input_graphs_sha256"}
                or type(item["input_graphs_sha256"]) is not dict or set(item["input_graphs_sha256"]) != {"structure", "jurisprudence"}
                or any(type(value) is not str or not tools.HASH.fullmatch(value) for value in
                       [item["release_id"], item["serving_sha256"], *item["input_graphs_sha256"].values()])):
            raise ValueError("Closed recorded component required")
        identifiers.append(item["release_id"])
    if identifiers != sorted(set(identifiers)):
        raise ValueError("Complete unique sorted recorded members required")
    base = inventory["retained_base"]
    if base is not None:
        if type(base) is not dict or set(base) != {"pointer", "files"} or type(base["files"]) is not dict:
            raise ValueError("Closed recorded whole base required")
        BasePointer.model_validate(base["pointer"])
        if not 1 <= len(base["files"]) <= tools.MAX_FILES or any(
                type(value) is not str or not tools.HASH.fullmatch(value) for value in base["files"].values()):
            raise ValueError("Complete recorded base file identities required")


def _recorded(settings, store, info, public):
    """Verify recorded bindings without interpreting their current legal status."""
    tools = _packet_tools()
    directory = tools.checked_path(settings.data_dir / "release-authorizations" / info["release_id"])
    retained, retained_hash = tools.read_packet(directory, store)
    if (set(retained) != {"authorization.json", "grant.fernet", "binding.fernet", "NOTICE.json"}
            or retained["NOTICE.json"] != final.NOTICE
            or tools.parse_json(retained["authorization.json"]) != final.route(info["release_id"])):
        raise ValueError("Exact recorded whole-release namespace required")
    raw = canonical(store.decode(SimpleNamespace(payload=retained["grant.fernet"].decode("ascii"))))
    body, key = final.verify_envelope(raw, settings)
    private = store.decode(SimpleNamespace(payload=retained["binding.fernet"].decode("ascii")))
    if type(private) is not dict or set(private) != {"candidate", "permission_sha256", "original_pointer_sha256"}:
        raise ValueError("Exact recorded whole binding required")
    command, candidate, permission, permission_hash, binding, request = final.candidate_inputs(settings, store, private["candidate"])
    if canonical(body) != canonical(final.approval_body(request)) or permission_hash != private["permission_sha256"]:
        raise ValueError("Exact recorded independent whole approval required")
    packet = tools.checked_path(binding["reviewed_packet"])
    reviewed, packet_hash = tools.read_packet(packet, store, schema_version=PACKET_SCHEMA)
    if packet_hash != binding["reviewed_packet_sha256"] or packet_hash != body["reviewed_packet_sha256"]:
        raise ValueError("Recorded independent review binding differs")
    dependency = store.decode(SimpleNamespace(payload=reviewed["dependencies.fernet"].decode("ascii")))
    if (type(dependency) is not dict or set(dependency) != {"schema_version", "selection", "dependencies_sha256", "public_inventory_sha256", "national_release_serving_authorized"}
            or dependency["schema_version"] != PACKET_SCHEMA or dependency["national_release_serving_authorized"] is not False):
        raise ValueError("Closed recorded original dependency binding required")
    Declaration.model_validate(dependency["selection"])
    inventory = tools.parse_json(reviewed["assembly-inputs.json"])
    _closed_inventory(inventory)
    inventory_hash = digest(canonical(inventory))
    if (canonical(inventory) != reviewed["assembly-inputs.json"]
            or inventory_hash != body["public_inventory_sha256"]
            or dependency["public_inventory_sha256"] != inventory_hash
            or dependency["dependencies_sha256"] != body["dependencies_sha256"]
            or body["release_id"] != info["release_id"] or body["serving_sha256"] != info["serving_sha256"]
            or body["ontology_sha256"] != info["ontology_sha256"]
            or body["final_review_key_sha256"] != info["review"]["key_sha256"]
            or body["final_grant_key_sha256"] != key[2]
            or body["scope"] != "complete_declared_release" or body["audience"] != "deployment_shared"
            or body["permitted_uses"] != sorted(REQUIRED_USES)):
        raise ValueError("Recorded inventory or independent trust differs")
    if _public_capture({**info, "bundle_path": candidate / "prepared/bundle"}) != public:
        raise ValueError("Recorded candidate differs from freshly verified installed bytes")
    graph = Graph().parse(data=public["bundle/inputs/structure.ttl"], format="turtle")
    node = URIRef(str(ASM) + inventory_hash)
    if (set(graph.objects(node, ASM.inventorySha256)) != {RDFLiteral(inventory_hash)}
            or set(graph.objects(node, ASM.inventoryJson)) != {RDFLiteral(canonical(inventory).decode())}
            or body["component_release_ids"] != [item["release_id"] for item in inventory["components"]]):
        raise ValueError("Recorded complete inventory is absent from attested graphs")
    for name, value in reviewed.items():
        if name.startswith(("inputs/", "evidence/")) or name == "review-attestation.json":
            if public.get("bundle/" + name) != value:
                raise ValueError("Recorded original review differs from attested installed payload")
    roots = (directory, candidate, packet)
    hashes = capture_roots(roots)
    if (tools.read_packet(directory, store) != (retained, retained_hash)
            or tools.read_packet(candidate / "permission", store) != (permission, permission_hash)
            or tools.read_packet(packet, store, schema_version=PACKET_SCHEMA) != (reviewed, packet_hash)):
        raise ValueError("Recorded bindings changed during inspection")
    return {"inventory": inventory, "inventory_sha256": inventory_hash,
        "dependencies_sha256": body["dependencies_sha256"], "approved_at": body["approved_at"],
        "expires_at": body["expires_at"], "roots": roots, "hashes": hashes, "raw": raw,
        "body": body, "key": key, "command": command}


def inspect_dependencies(settings, expectation):
    expectation = DependencyExpectation.model_validate(expectation.model_dump())
    tools, serving, command = _packet_tools(), _load_serving(), final.commands()
    request = canonical(expectation.model_dump())
    root = tools.checked_path(settings.graph_release_dir)
    location = (settings.data_dir, settings.public_source_dir, settings.database_url)
    if settings.graph_serving_review_role != "final":
        raise ValueError("Explicit final serving review role required")
    key = settings.serving_review_key
    if key is None:
        raise ValueError("Vetted final public review key required")
    key_bytes = tools.read_file(key, 16384)
    target = tools.checked_path(root / "releases" / expectation.release_id)
    with observation_locks(root):
        pointer = serving.read_pointer(root)
        pointer_bytes = tools.read_file(root / "active.json", 4096) if pointer else None
        payload = command.verify_public_payload(target, key)
        info, public = payload.info, payload.files
        if info["release_id"] != expectation.release_id or info["serving_sha256"] != expectation.serving_sha256:
            raise ValueError("Installed release differs from explicit dependency expectation")
        with readonly_store(settings) as reader:
            recorded = _recorded(settings, reader, info, public)
        current = "withheld_or_unavailable"
        try:
            with final.FinalReleaseAuthorization(settings).guard(info, "install"):
                checked_at = datetime.now(timezone.utc).isoformat()
        except AuthorizationError:
            checked_at = datetime.now(timezone.utc).isoformat()
        else:
            current = "verified"
        if (capture_roots(recorded["roots"]) != recorded["hashes"]
                or final.verify_envelope(recorded["raw"], settings) != (recorded["body"], recorded["key"])
                or _public_capture(info) != public or serving.read_pointer(root) != pointer
                or (tools.read_file(root / "active.json", 4096) if pointer else None) != pointer_bytes
                or tools.read_file(key, 16384) != key_bytes or settings.serving_review_key != key
                or settings.graph_serving_review_role != "final" or tools.checked_path(settings.graph_release_dir) != root
                or (settings.data_dir, settings.public_source_dir, settings.database_url) != location
                or canonical(expectation.model_dump()) != request):
            raise ValueError("Dependency observation changed")
    inventory = recorded["inventory"]
    return {"schema_version": "legal-retained-dependency-observation-v1", "confidentiality": "firm_confidential",
        "release_id": expectation.release_id, "serving_sha256": expectation.serving_sha256,
        "observed_at": datetime.now(timezone.utc).isoformat(), "permission_checked_at": checked_at,
        "public_inventory": "verified", "recorded_whole_signature": "verified",
        "recorded_inventory_sha256": recorded["inventory_sha256"], "recorded_dependencies_sha256": recorded["dependencies_sha256"],
        "recorded_approved_at": recorded["approved_at"], "recorded_expires_at": recorded["expires_at"],
        "recorded_components": [item["release_id"] for item in inventory["components"]],
        "recorded_retained_base": inventory["retained_base"]["pointer"] if inventory["retained_base"] else None,
        "active_pointer": pointer, "current_permission": current,
        "activation_authorized": False, "runtime_read_authorized": False, "retry_authorized": False,
        "repair_performed": False, "publication_performed": False, "legal_qualification_granted": False}
