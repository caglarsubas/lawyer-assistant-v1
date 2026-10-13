"""Complete declared A/B inputs under current, conjunctive component permission.

No independent guard nesting, public graph mutation or serving authorization.
The existing retained structural base must be included whole. Unsupported base
namespaces fail closed rather than treating a missing inventory as empty.
"""
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import Field

from . import graph_b_component_grants as b_grants
from . import graph_b_publication as b_public
from .graph_b_review import configured_key_path
from .graph_b_snapshot import SnapshotRequest
from .graph_release import _load_serving
from .mixed_graph_snapshot import MixedGraphRequest, locked_mixed_snapshot
from .public_graph_union import compile_union
from .release_authorization import _packet_tools, _uuid
from .release_preparation import canonical, digest
from .release_set_authorization import (
    ReleaseSetAuthorization,
    _selection,
    _validate_body,
    match_public_bundle,
    validate_source_permissions,
)
from .release_set_preparation import compile_review_set
from .source_reviews import StrictInput

PACKET_SCHEMA = "legal-declared-graph-assembly-v1"


class Component(StrictInput):
    release_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared: str = Field(min_length=1, max_length=4096)
    grant: str = Field(min_length=1, max_length=4096)


class BasePointer(StrictInput):
    format_version: Literal[1]
    release_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    serving_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    previous_release_id: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    sequence: int = Field(ge=1)


class Declaration(StrictInput):
    schema_version: Literal["legal-declared-graph-selection-v1"]
    operator_id: str = Field(min_length=1, max_length=64)
    expected_base: BasePointer | None
    structure: Component
    jurisprudence: list[Component] = Field(min_length=1, max_length=8)


def trust(settings):
    paths = tuple(_packet_tools().checked_path(path) for path in (
        settings.graph_trusted_review_key, settings.graph_b_review_trusted_key,
        settings.graph_b_component_trusted_key, settings.graph_final_review_trusted_key))
    keys = tuple(configured_key_path(path) for path in paths)
    if len({key[2] for key in keys}) != 4:
        raise ValueError("Four independently configured public trust roles are required")
    return paths, tuple((key[0], key[2]) for key in keys)


def _b_load(store, component, paths, epoch, ontology_root):
    tools = _packet_tools()
    info = _load_serving().validate_prepared(tools.checked_path(component.prepared), paths[0])
    if info["release_id"] != component.release_id:
        raise ValueError("Declared decision component differs")
    outer, outer_hash = tools.read_packet(component.grant, store, schema_version=b_public.PACKET_SCHEMA)
    raw = canonical(store.decode(SimpleNamespace(payload=outer["grant.fernet"].decode("ascii"))))
    envelope, _, _ = b_grants.verify_envelope(raw, paths[2])
    files, packet_hash = tools.read_packet(tools.checked_path(component.grant) / "preparation", store,
                                          schema_version=b_public.PACKET_SCHEMA)
    expected = {"grant.fernet": outer["grant.fernet"], "NOTICE.json": b_grants.NOTICE,
        **{"preparation/" + name: value for name, value in tools.sealed_files(
            files, store, schema_version=b_public.PACKET_SCHEMA).items()}}
    if outer != expected or envelope["body"]["publication_epoch"] != epoch:
        raise ValueError("Retained inclusion grant inventory or epoch differs")
    private = b_public.private_evidence(store, files)
    b_public.match_public_component(files, info, paths[0], ontology_root)
    return {"info": info, "files": files, "packet_hash": packet_hash, "private": private,
            "raw": raw, "outer_hash": outer_hash, "selection": SnapshotRequest.model_validate(private["binding"]["selection"])}


def _load(settings, store, declaration, ontology_root):
    tools, serving = _packet_tools(), _load_serving()
    paths, keys = trust(settings)
    epoch_bytes = tools.read_file(settings.data_dir / "publication-epoch", 37)
    epoch = _uuid(epoch_bytes.decode("ascii").removesuffix("\n"))
    root = tools.checked_path(settings.graph_release_dir)
    if not root.is_dir() or not tools.checked_path(root / "releases").is_dir():
        raise ValueError("An initialized publication root is required")
    pointer = serving.read_pointer(root)
    pointer_bytes = tools.read_file(root / "active.json", 4096) if pointer else None
    if pointer and tools.parse_json(pointer_bytes) != pointer:
        raise ValueError("Retained pointer is not strict JSON")
    expected_base = declaration.expected_base.model_dump() if declaration.expected_base else None
    if pointer != expected_base:
        raise ValueError("Retained publication base changed")
    base = None
    if pointer:
        # This packet qualifies the first mixed release from a retained A source
        # set. A prior mixed assembly needs its own complete serving grant and
        # dependency reconstruction; never route it through an A-only fallback.
        if pointer["release_id"] != declaration.structure.release_id:
            raise ValueError("The whole retained structural base must be declared")
        active = serving.load_active(root, paths[0])
        base_root = active["bundle_path"].parent
        base = {"pointer": pointer, "files": {name: digest(tools.read_file(base_root / name, tools.MAX_FILE))
                for name in sorted(serving._files(base_root))}}
    a_info = serving.validate_prepared(tools.checked_path(declaration.structure.prepared), paths[0])
    if a_info["release_id"] != declaration.structure.release_id:
        raise ValueError("Declared structural component differs")
    auth_root = tools.checked_path(settings.data_dir / "release-authorizations")
    expected_grant = auth_root / declaration.structure.release_id
    if tools.checked_path(declaration.structure.grant) != tools.checked_path(expected_grant):
        raise ValueError("Structural permission must use the configured retained namespace")
    a_gate = ReleaseSetAuthorization(store, None, auth_root, paths[0], ontology_root,
                                     settings.data_dir / "publication-epoch")
    a_current = a_gate._load(a_info, "read", tools)  # Stateless; no Session/guard nesting.
    if a_current["body"]["source_binding"]["operator_id"] != declaration.operator_id:
        raise ValueError("Exact common source owner is required")
    b_values = [_b_load(store, component, paths, epoch, ontology_root) for component in declaration.jurisprudence]
    identifiers = [declaration.structure.release_id, *(item.release_id for item in declaration.jurisprudence)]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Every component must be declared exactly once")
    if any(value["private"]["binding"]["operator_id"] != declaration.operator_id for value in b_values):
        raise ValueError("Exact common source owner is required")
    request = MixedGraphRequest(schema_version="legal-mixed-graph-selection-v1",
        structure=_selection(a_current["body"]["source_binding"], tools),
        jurisprudence=[value["selection"] for value in b_values])
    lock_stat = (root / "publication.lock").stat()
    return {"paths": paths, "keys": keys, "epoch_bytes": epoch_bytes, "epoch": epoch,
            "location": (str(root), str(auth_root), str(tools.checked_path(settings.public_source_dir))),
            "pointer_sha256": digest(pointer_bytes) if pointer_bytes else None,
            "lock_identity": (lock_stat.st_dev, lock_stat.st_ino),
            "base": base, "structure": a_current, "a_info": a_info, "jurisprudence": b_values, "request": request}


def _fingerprint(value):
    a = value["structure"]
    def file_hashes(files):
        return {name: digest(raw) for name, raw in files.items()}
    def info_hash(info):
        return digest(canonical({key: str(item) if isinstance(item, Path) else item for key, item in info.items()}))
    return digest(canonical({"keys": [digest(key[0]) for key in value["keys"]], "epoch": digest(value["epoch_bytes"]),
        "paths": [str(path) for path in value["paths"]],
        "base": value["base"], "location": value["location"], "pointer": value["pointer_sha256"],
        "lock_identity": value["lock_identity"], "request": value["request"].model_dump(),
        "a_authorization": digest(a["authorization"]), "a_packet": a["packet_digest"],
        "a_body": a["body"], "a_files": file_hashes(a["files"]), "a_info": info_hash(value["a_info"]),
        "b_packets": sorted((item["info"]["release_id"], item["outer_hash"], item["packet_hash"], digest(item["raw"]),
                             digest(canonical(file_hashes(item["files"]))), digest(canonical(item["private"])), info_hash(item["info"]))
                            for item in value["jurisprudence"])}))


def _match(store, loaded, snapshot, ontology_root):
    tools = _packet_tools()
    a = loaded["structure"]
    validate_source_permissions(a["body"], snapshot["structure"])
    evidence = {Path(name).stem: raw for name, raw in a["files"].items() if name.startswith("private-evidence/")}
    rebuilt, _ = compile_review_set(snapshot["structure"], tools.parse_json(a["files"]["registry.json"]),
                                    tools.parse_json(a["files"]["resolutions.json"]), evidence, ontology_root)
    if rebuilt != a["files"]:
        raise ValueError("Structural preparation differs from current original sources")
    match_public_bundle(a["files"], loaded["a_info"], ontology_root)
    b_snapshots = {canonical(item["binding"]["selection"]): item for item in snapshot["jurisprudence"]}
    if len(b_snapshots) != len(loaded["jurisprudence"]):
        raise ValueError("Complete decision context inventory is required")
    for item in loaded["jurisprudence"]:
        current = b_snapshots[canonical(item["selection"].model_dump())]
        private = b_public.verify_files(store, item["files"], current, ontology_root)
        b_grants.match_grant(item["raw"], loaded["paths"][2], item["files"], item["packet_hash"], private,
                             current, item["info"], loaded["epoch"])
    _lifetimes(loaded, snapshot)


def _lifetimes(loaded, snapshot):
    # Expiry can pass while earlier public/source reconstruction runs. Repeat
    # ONLY the cheap current permission checks after that work for EVERY member.
    _validate_body(loaded["structure"]["body"], _packet_tools())
    b_snapshots = {canonical(item["binding"]["selection"]): item for item in snapshot["jurisprudence"]}
    for item in loaded["jurisprudence"]:
        b_grants.match_grant(item["raw"], loaded["paths"][2], item["files"], item["packet_hash"], item["private"],
            b_snapshots[canonical(item["selection"].model_dump())], item["info"], loaded["epoch"])


@contextmanager
def current_assembly(settings, store, source_store, declaration, ontology_root):
    """One sorted transaction and publication read lock, all dependencies or none.

    Callers discard new artifacts on ANY failed exit, including interruption.
    This never returns install/activation/rollback/runtime permission.
    """
    declaration = Declaration.model_validate(declaration.model_dump())
    serving = _load_serving()
    with serving.publication_lock(_packet_tools().checked_path(settings.graph_release_dir), shared=True) as descriptor:
        lock_stat = os.fstat(descriptor)
        lock_identity = (lock_stat.st_dev, lock_stat.st_ino)
        loaded = _load(settings, store, declaration, ontology_root)
        if loaded["lock_identity"] != lock_identity:
            raise ValueError("Publication lock was replaced")
        original = _fingerprint(loaded)
        with locked_mixed_snapshot(store, source_store, operator_id=declaration.operator_id, request=loaded["request"],
                trusted_key=loaded["paths"][1], ontology_root=ontology_root, shared=True) as snapshot:
            _match(store, loaded, snapshot, ontology_root)
            prepared = {item.release_id: item.prepared for item in (declaration.structure, *declaration.jurisprudence)}
            files, inventory = compile_union(prepared, base=loaded["base"], trusted_key=loaded["paths"][0],
                                             ontology_root=ontology_root)
            _lifetimes(loaded, snapshot)
            if trust(settings) != (loaded["paths"], loaded["keys"]):
                raise ValueError("Assembly trust changed during compilation")
            output_hash = digest(canonical({name: digest(raw) for name, raw in files.items()}))
            def recheck():
                final = _load(settings, store, declaration, ontology_root)
                if (_fingerprint(final) != original or _fingerprint(loaded) != original or final["lock_identity"] != lock_identity
                        or canonical(inventory) != files["assembly-inputs.json"]
                        or digest(canonical({name: digest(raw) for name, raw in files.items()})) != output_hash):
                    raise ValueError("Assembly dependencies or output changed")
                _match(store, final, snapshot, ontology_root)
                if trust(settings) != (loaded["paths"], loaded["keys"]):
                    raise ValueError("Assembly trust changed at final validation")
            yield files, inventory, loaded
            recheck()
        # Check expiry/keys/base/files again after original ledger reconstruction.
        recheck()
