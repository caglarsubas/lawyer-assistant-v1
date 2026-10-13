"""Complete declared A/B inputs under current, conjunctive component permission.

No independent guard nesting, public graph mutation or serving authorization.
The existing retained structural base must be included whole. Unsupported base
namespaces fail closed rather than treating a missing inventory as empty.
"""
import os
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, NamedTuple

from pydantic import Field

from . import graph_b_component_grants as b_grants
from . import graph_b_publication as b_public
from .graph_b_review import configured_key_path
from .graph_b_snapshot import SnapshotRequest
from .graph_release import _load_serving
from .mixed_graph_snapshot import MixedGraphRequest, locked_mixed_snapshot
from .public_graph_union import compile_captured_union
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


class VerifiedServingContext(NamedTuple):
    """Internal signed-grant context; not a preparation or agent API.

    The caller verifies the external whole-release envelope and exact sealed
    original packet first. The original dependency fingerprint must still match.
    Only the live pointer has a distinct before/after lifecycle.
    """
    release_id: str
    original_pointer_sha256: str | None
    before: bytes
    after: bytes
    descriptor: int


def _load(settings, store, declaration, ontology_root, serving_context=None):
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
    if serving_context is None:
        if pointer != expected_base:
            raise ValueError("Retained publication base changed")
    elif (not isinstance(serving_context, VerifiedServingContext)
            or canonical(pointer) != serving_context.before):
        raise ValueError("Signed serving context pointer differs")
    base = None
    if expected_base:
        # This packet qualifies the first mixed release from a retained A source
        # set. A prior mixed assembly needs its own complete serving grant and
        # dependency reconstruction; never route it through an A-only fallback.
        if expected_base["release_id"] != declaration.structure.release_id:
            raise ValueError("The whole retained structural base must be declared")
        active = serving.validate_prepared(root / "releases" / expected_base["release_id"], paths[0])
        if active["release_id"] != expected_base["release_id"] or active["serving_sha256"] != expected_base["serving_sha256"]:
            raise ValueError("Original retained structural base differs")
        base_root = active["bundle_path"].parent
        base = {"pointer": expected_base, "files": {name: digest(tools.read_file(base_root / name, tools.MAX_FILE))
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
            "pointer_sha256": (serving_context.original_pointer_sha256 if serving_context is not None
                                else digest(pointer_bytes) if pointer_bytes else None),
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


def _public_capture(info):
    """Read ALL public bytes and bind them to the just-verified signed manifest.

    Pure RDF/signature validation is not repeated for unchanged bytes within
    this operation. Every file is read/hashed again on exit, never mtime-trusted.
    """
    tools, serving = _packet_tools(), _load_serving()
    root = info["bundle_path"].parent
    names = serving._files(root)
    if len(names) > tools.MAX_FILES:
        raise ValueError("Public component inventory exceeds budget")
    files, total = {}, 0
    for name in sorted(names):
        raw = tools.read_file(root / name, tools.MAX_FILE)
        total += len(raw)
        if total > tools.MAX_PACKET:
            raise ValueError("Public component exceeds capture budget")
        files[name] = raw
    manifest_raw = files["bundle/manifest.json"]
    if digest(manifest_raw) != info["release_id"]:
        raise ValueError("Verified public manifest changed")
    manifest = tools.parse_json(manifest_raw)
    expected = {"bundle/" + name for name in manifest["files"]}
    expected |= {"bundle/manifest.json", "bundle/manifest.sha256", "serving.json", "structure.nq", "jurisprudence.nq"}
    if (set(files) != expected or files["bundle/manifest.sha256"] != (info["release_id"] + "\n").encode()
            or digest(files["serving.json"]) != info["serving_sha256"]
            or any(digest(files["bundle/" + name]) != value for name, value in manifest["files"].items())
            or any(digest(files[family + ".nq"]) != info["graphs"][family]["sha256"] for family in ("structure", "jurisprudence"))):
        raise ValueError("Verified public bytes or complete inventory changed")
    return files


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
def current_assembly(settings, store, source_store, declaration, ontology_root, *, serving_context=None, shared=True):
    """One sorted transaction and publication read lock, all dependencies or none.

    Callers discard new artifacts on ANY failed exit, including interruption.
    This never returns install/activation/rollback/runtime permission.
    """
    declaration = Declaration.model_validate(declaration.model_dump())
    serving = _load_serving()
    publication = (nullcontext(serving_context.descriptor) if serving_context is not None
                   else serving.publication_lock(_packet_tools().checked_path(settings.graph_release_dir), shared=True))
    with publication as descriptor:
        lock_stat = os.fstat(descriptor)
        lock_identity = (lock_stat.st_dev, lock_stat.st_ino)
        loaded = _load(settings, store, declaration, ontology_root, serving_context)
        if loaded["lock_identity"] != lock_identity:
            raise ValueError("Publication lock was replaced")
        original = _fingerprint(loaded)
        public = {loaded["a_info"]["release_id"]: (loaded["a_info"], _public_capture(loaded["a_info"])),
                  **{item["info"]["release_id"]: (item["info"], _public_capture(item["info"])) for item in loaded["jurisprudence"]}}
        with locked_mixed_snapshot(store, source_store, operator_id=declaration.operator_id, request=loaded["request"],
                trusted_key=loaded["paths"][1], ontology_root=ontology_root, shared=shared) as snapshot:
            _match(store, loaded, snapshot, ontology_root)
            files, inventory = compile_captured_union(public, base=loaded["base"], ontology_root=ontology_root)
            _lifetimes(loaded, snapshot)
            if trust(settings) != (loaded["paths"], loaded["keys"]):
                raise ValueError("Assembly trust changed during compilation")
            output_hash = digest(canonical({name: digest(raw) for name, raw in files.items()}))
            def recheck():
                # Read every private/public byte afresh. The enclosing mixed
                # snapshot reconstructs all original DB/source histories on exit.
                # Nothing is cached across operations or accepted from a caller.
                tools = _packet_tools()
                root = tools.checked_path(settings.graph_release_dir)
                current_lock = (root / "publication.lock").stat()
                pointer = serving.read_pointer(root)
                pointer_hash = digest(tools.read_file(root / "active.json", 4096)) if pointer else None
                a = loaded["structure"]
                if (_fingerprint(loaded) != original or (current_lock.st_dev, current_lock.st_ino) != lock_identity
                        or tuple(map(str, (root, tools.checked_path(settings.data_dir / "release-authorizations"),
                                          tools.checked_path(settings.public_source_dir)))) != loaded["location"]
                        or (canonical(pointer) != serving_context.after if serving_context is not None
                            else pointer_hash != loaded["pointer_sha256"])
                        or tools.read_file(settings.data_dir / "publication-epoch", 37) != loaded["epoch_bytes"]
                        or tools.read_file(Path(declaration.structure.grant) / "authorization.json", tools.MAX_JSON) != a["authorization"]
                        or tools.read_packet(Path(declaration.structure.grant) / "packet", store,
                            schema_version="legal-review-source-set-packet-v1") != (a["files"], a["packet_digest"])
                        or canonical(inventory) != files["assembly-inputs.json"]
                        or digest(canonical({name: digest(raw) for name, raw in files.items()})) != output_hash):
                    raise ValueError("Assembly dependencies or output changed")
                for component, item in zip(declaration.jurisprudence, loaded["jurisprudence"], strict=True):
                    if tools.read_packet(component.grant, store, schema_version=b_public.PACKET_SCHEMA)[1] != item["outer_hash"]:
                        raise ValueError("Retained inclusion grant changed")
                for info, captured in public.values():
                    if _public_capture(info) != captured:
                        raise ValueError("Verified public component changed")
                if loaded["base"]:
                    base_root = root / "releases" / loaded["base"]["pointer"]["release_id"]
                    if {name: digest(tools.read_file(base_root / name, tools.MAX_FILE)) for name in serving._files(base_root)} != loaded["base"]["files"]:
                        raise ValueError("Complete retained base changed")
                _lifetimes(loaded, snapshot)
                if trust(settings) != (loaded["paths"], loaded["keys"]):
                    raise ValueError("Assembly trust changed at final validation")
            yield files, inventory, loaded
            recheck()
        # Check expiry/keys/base/files again after original ledger reconstruction.
        recheck()
