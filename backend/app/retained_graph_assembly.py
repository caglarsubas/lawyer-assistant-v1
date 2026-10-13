"""Operation-local retained mixed dependencies, never recursive serving guards.

Frozen reviewed bases are distinct from the live CAS pointer. Every parent still
needs its original, currently valid fifth-key permission and fourth-key review.
Only original ledgers inside the enclosing single transaction can qualify use.
"""
from types import SimpleNamespace

from .decision_equivalence import context_ids
from .graph_release import _load_serving
from .mixed_graph_snapshot import RetainedGraphRequest
from .release_authorization import _packet_tools
from .release_preparation import canonical, digest

MAX_DEPTH = 4
MAX_COMPONENTS = 32
MAX_FILES = 2048
MAX_BYTES = 256 * 1024 * 1024


def nodes(loaded):
    parent = loaded.get("retained")
    return [*nodes(parent["loaded"]), loaded] if parent else [loaded]


def fingerprint(parent):
    from .declared_graph_assembly import _fingerprint
    return {"dependencies": _fingerprint(parent["loaded"]), "binding": parent["binding"],
        "files": parent["hashes"], "grant": digest(parent["raw"]), "key": digest(parent["key"][1]),
        "selection": parent["declaration"].model_dump()}


def reserve(captures, roots):
    """Charge physical bytes BEFORE recursive decoding or RDF validation.

    Only operation-local byte identities are deduplicated. No legal/source
    permission verdict is stored here. Revisited changed bytes fail closed.
    """
    tools, serving = _packet_tools(), _load_serving()
    inventory = captures.setdefault("physical_inventory", {})
    total = sum(size for _, size in inventory.values())
    for root in roots:
        root = tools.checked_path(root)
        for name in sorted(serving._files(root)):
            path = str(root / name)
            if path not in inventory and len(inventory) >= MAX_FILES:
                raise ValueError("Complete retained file budget exceeded")
            raw = tools.read_file(root / name, tools.MAX_FILE)
            identity = (digest(raw), len(raw))
            if path in inventory:
                if inventory[path] != identity:
                    raise ValueError("Retained physical dependency changed during discovery")
            else:
                total += len(raw)
                if total > MAX_BYTES:
                    raise ValueError("Complete retained byte budget exceeded")
                inventory[path] = identity


def budget(loaded):
    """Bound the COMPLETE distinct physical inventory, never truncate a chain."""
    tools, serving = _packet_tools(), _load_serving()
    seen, count, total, components = set(), 0, 0, set()
    for node in nodes(loaded):
        roots = [(node["a_info"]["bundle_path"].parent, False),
                 (tools.checked_path(node["declaration"].structure.grant), True)]
        for component, item in zip(node["declaration"].jurisprudence, node["jurisprudence"], strict=True):
            roots.extend([(item["info"]["bundle_path"].parent, False), (tools.checked_path(component.grant), True)])
        components.update([node["a_info"]["release_id"], *(item["info"]["release_id"] for item in node["jurisprudence"])])
        if node.get("retained"):
            roots.extend((root, False) for root in node["retained"]["roots"])
        for root, _ in roots:
            for name in sorted(serving._files(root)):
                path = root / name
                if path in seen:
                    continue
                seen.add(path)
                count += 1
                if count > MAX_FILES:
                    raise ValueError("Complete retained file budget exceeded")
                total += len(tools.read_file(path, tools.MAX_FILE))
                if total > MAX_BYTES:
                    raise ValueError("Complete retained byte budget exceeded")
        if len(components) > MAX_COMPONENTS:
            raise ValueError("Complete retained component budget exceeded")


def load(settings, store, pointer, ontology_root, *, stack, cache):
    # Imports are lazy: the serving guard calls this assembler, never vice versa.
    from . import final_release_authorization as final
    from .declared_graph_assembly import (
        PACKET_SCHEMA,
        Declaration,
        VerifiedServingContext,
        _load,
        _public_capture,
    )
    tools, serving = _packet_tools(), _load_serving()
    ident = pointer["release_id"]
    if ident in stack or len(stack) >= MAX_DEPTH:
        raise ValueError("Retained mixed base cycle or depth budget exceeded")
    root = tools.checked_path(settings.graph_release_dir)
    directory = tools.checked_path(settings.data_dir / "release-authorizations" / ident)
    reserve(cache, [directory, root / "releases" / ident])
    retained, _ = tools.read_packet(directory, store)
    if (set(retained) != {"authorization.json", "grant.fernet", "binding.fernet", "NOTICE.json"}
            or retained["NOTICE.json"] != final.NOTICE or tools.parse_json(retained["authorization.json"]) != final.route(ident)):
        raise ValueError("Original whole retained base permission required")
    raw = canonical(store.decode(SimpleNamespace(payload=retained["grant.fernet"].decode("ascii"))))
    body, key = final.verify_envelope(raw, settings)
    private = store.decode(SimpleNamespace(payload=retained["binding.fernet"].decode("ascii")))
    if type(private) is not dict or set(private) != {"candidate", "permission_sha256", "original_pointer_sha256"}:
        raise ValueError("Exact original retained mixed binding required")
    command, candidate, _, permission_hash, candidate_binding, request = final.candidate_inputs(settings, store, private["candidate"])
    if permission_hash != private["permission_sha256"] or canonical(body) != canonical(final.approval_body(request)):
        raise ValueError("Retained grant must approve its exact original request")
    packet = tools.checked_path(candidate_binding["reviewed_packet"])
    reserve(cache, [candidate, packet])
    files, packet_hash = tools.read_packet(packet, store, schema_version=PACKET_SCHEMA)
    if packet_hash != candidate_binding["reviewed_packet_sha256"]:
        raise ValueError("Original retained final review packet differs")
    binding = store.decode(SimpleNamespace(payload=files["dependencies.fernet"].decode("ascii")))
    declaration = Declaration.model_validate(binding["selection"])
    # Only this authenticated original grant can nominate a frozen pointer hash.
    # No source or schema API can manufacture an alternate historical baseline.
    context = VerifiedServingContext(ident, private["original_pointer_sha256"],
        canonical(serving.read_pointer(root)), canonical(serving.read_pointer(root)), -1)
    loaded = _load(settings, store, declaration, ontology_root, context, _stack=(*stack, ident), _cache=cache)
    payload = command.verify_public_payload(candidate / "prepared", loaded["paths"][3])
    if payload.info["release_id"] != ident or payload.info["serving_sha256"] != pointer["serving_sha256"]:
        raise ValueError("Retained complete public identity differs")
    installed_info = {**payload.info, "bundle_path": root / "releases" / ident / "bundle"}
    if _public_capture(installed_info) != payload.files:
        raise ValueError("Whole installed retained base differs from original reviewed payload")
    roots = (directory, candidate, packet, installed_info["bundle_path"].parent)
    hashes = capture_roots(roots)
    result = {"loaded": loaded, "declaration": declaration, "files": files, "binding": binding,
        "raw": raw, "body": body, "key": key, "request": request, "command": command,
        "candidate": candidate, "packet_hash": packet_hash, "payload": payload, "roots": roots, "hashes": hashes,
        "settings": settings}
    budget(loaded)
    return result


def capture_roots(roots):
    tools, serving = _packet_tools(), _load_serving()
    result, total = {}, 0
    for root in roots:
        for name in sorted(serving._files(root)):
            path = root / name
            if str(path) in result:
                continue
            if len(result) >= MAX_FILES:
                raise ValueError("Retained file budget exceeded")
            raw = tools.read_file(path, tools.MAX_FILE)
            total += len(raw)
            if total > MAX_BYTES:
                raise ValueError("Retained byte budget exceeded")
            result[str(path)] = digest(raw)
    return result


def plan(loaded):
    structures, contexts, components = {}, {}, {}
    for node in nodes(loaded):
        if node["declaration"].operator_id != loaded["declaration"].operator_id:
            raise ValueError("One exact owner for every retained source is required")
        for component in [node["declaration"].structure, *node["declaration"].jurisprudence]:
            encoded = canonical(component.model_dump())
            if component.release_id in components and components[component.release_id] != encoded:
                raise ValueError("Retained component location or grant alias differs")
            components[component.release_id] = encoded
        structure = node["request"].structure
        structures[canonical(structure.model_dump())] = structure
        for item in node["request"].jurisprudence:
            context = context_ids(*item.decision_source_ids, item.register_source_id)[1]
            if context in contexts and contexts[context] != item:
                raise ValueError("Retained decision context pins differ")
            contexts[context] = item
    return RetainedGraphRequest(schema_version="legal-retained-mixed-selection-v1",
        structures=[item for _, item in sorted(structures.items())],
        jurisprudence=[item for _, item in sorted(contexts.items())])


def snapshot_for(node, request, snapshot):
    structures = {canonical(group.model_dump()): value for group, value in zip(request.structures, snapshot["structures"], strict=True)}
    selected = {canonical(item.model_dump()) for item in node["request"].jurisprudence}
    return {"structure": structures[canonical(node["request"].structure.model_dump())],
        "jurisprudence": [item for item in snapshot["jurisprudence"] if canonical(item["binding"]["selection"]) in selected]}


def verify(parent, store, files, inventory):
    from .declared_graph_assembly import _fingerprint
    loaded, command, declaration = parent["loaded"], parent["command"], parent["declaration"]
    expected_binding = {"schema_version": "legal-declared-graph-assembly-v1", "selection": declaration.model_dump(),
        "dependencies_sha256": _fingerprint(loaded), "public_inventory_sha256": digest(files["assembly-inputs.json"]),
        "national_release_serving_authorized": False}
    if canonical(parent["binding"]) != canonical(expected_binding) or canonical(inventory) != files["assembly-inputs.json"]:
        raise ValueError("Complete original retained dependency inventory differs")
    original = parent["files"]
    body = _packet_tools().parse_json(original["public-review-body.json"])
    expected = {**files, "public-review-body.json": canonical(command.review_body(files, loaded, declaration, body["reviewer"], body["reviewed_at"])),
        "NOTICE.json": command.ASSEMBLY_NOTICE, "dependencies.fernet": original["dependencies.fernet"],
        "review-attestation.json": original["review-attestation.json"]}
    if original != expected:
        raise ValueError("Original retained reviewed assembly differs")
    command.verify_captured_attestation(original, loaded, parent["payload"])
    request = parent["request"]
    expected_request = command.request_body(parent["settings"], original, loaded, parent["payload"].info,
        parent["packet_hash"], request["reviewer"], request["approved_at"], request["expires_at"])
    if canonical(expected_request) != canonical(request):
        raise ValueError("Original retained whole permission differs")


def recheck(parent):
    from . import final_release_authorization as final
    if (capture_roots(parent["roots"]) != parent["hashes"]
            or final.verify_envelope(parent["raw"], parent["settings"]) != (parent["body"], parent["key"])):
        raise ValueError("Complete retained mixed artifacts or trust changed")
    request = parent["request"]
    command = parent["command"]
    if canonical(command.request_body(parent["settings"], parent["files"], parent["loaded"], parent["payload"].info,
            parent["packet_hash"], request["reviewer"], request["approved_at"], request["expires_at"])) != canonical(request):
        raise ValueError("Original retained whole permission lifetime changed")
