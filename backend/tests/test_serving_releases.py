"""TEST-ONLY keys and invented RDF in temporary directories; no legal review performed."""
import base64
import hashlib
import importlib.util
import json
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rdflib import RDF, Dataset, Graph, Literal, URIRef

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("serving_test_module", ROOT / "ontology" / "serving.py")
serving = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serving)
release = serving._release


@pytest.fixture
def authorization_guard():
    """Explicit synthetic guard; never installed as the production default."""
    @contextmanager
    def guard(info, action):
        assert action in {"install", "activate", "rollback"}
        assert info["review"]["verified"] is True
        assert info["release_id"] == info["bundle_sha256"]
        assert info["bundle_path"].is_dir()
        yield {"release_id": info["release_id"], "current": True}
    return guard


@pytest.fixture
def trust(tmp_path):
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "TEST-ONLY-public.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo))
    return key, public


def bundle(tmp_path, trust, variant="a", unsigned=False):
    directory = tmp_path / variant
    directory.mkdir()
    inputs = {}
    for family in serving.FAMILIES:
        path = directory / f"{family}.ttl"
        # Deliberately no authority assertions, real source artifacts or purported
        # legal facts. Stable resource identifiers also exercise shared context.
        path.write_text(f'<urn:test-only:{family}:{variant}> <urn:test-only:label> "TEST ONLY" ; '
                        f'<urn:test-only:detail> <urn:test-only:detail:{family}:{variant}> .\n')
        inputs[family] = path
    evidence = directory / "evidence"
    evidence.mkdir()
    key, public = trust
    body = {"reviewer": "TEST ONLY - no actual legal review", "reviewed_at": "2026-01-01T00:00:00Z",
            "decision": "approve", "scope": "national_ontology_and_assertions",
            "ontology_sha256": release.ontology_digest(ROOT / "ontology"),
            "input_graphs_sha256": {name: release.file_hash(path) for name, path in inputs.items()}}
    attestation = directory / "TEST-ONLY-review.json"
    attestation.write_bytes(release.canonical({"algorithm": "Ed25519", "body": body,
                                             "signature": base64.b64encode(key.sign(release.canonical(body))).decode()}))
    output = directory / "bundle"
    release.create_bundle(ROOT / "ontology", inputs, evidence, output,
                          None if unsigned else attestation, None if unsigned else public)
    return output


def prepared(tmp_path, trust, variant="a"):
    output = tmp_path / f"prepared-{variant}"
    return output, serving.prepare(bundle(tmp_path, trust, variant), trust[1], output)


def test_prepare_is_deterministic_and_contains_signed_shared_context(tmp_path, trust):
    output, result = prepared(tmp_path, trust)
    again = serving.validate_prepared(output, trust[1])
    assert again == result
    assert result["release_id"] == result["bundle_sha256"]
    assert result["review"]["verified"]
    for family in serving.FAMILIES:
        dataset = Dataset().parse(output / f"{family}.nq", format="nquads")
        iris = {str(context.identifier) for context in dataset.contexts() if len(context)}
        assert iris == {result["graphs"][family]["graph_iri"], result["metadata_graph_iri"]}
        graph = dataset.graph(URIRef(result["graphs"][family]["graph_iri"]))
        assert (URIRef("urn:test-only:structure:a"), None, None) in graph
        assert (URIRef("urn:test-only:jurisprudence:a"), None, None) in graph
        assert len(graph) == result["graphs"][family]["triple_count"]
        assert len(graph) > 100  # Reviewed-snapshot schema also present, without inference.


def test_unsigned_bundle_cannot_be_prepared(tmp_path, trust):
    with pytest.raises(ValueError, match="trusted signed legal review"):
        serving.prepare(bundle(tmp_path, trust, unsigned=True), trust[1], tmp_path / "prepared")
    assert not (tmp_path / "prepared").exists()


def test_prepare_rejects_existing_destination(tmp_path, trust):
    output, _ = prepared(tmp_path, trust)
    with pytest.raises(ValueError, match="already exists"):
        serving.prepare(output / "bundle", trust[1], output)


@pytest.mark.parametrize("target", ["serving.json", "structure.nq", "jurisprudence.nq", "bundle/inputs/structure.ttl"])
def test_tampering_blocks_validation(tmp_path, trust, target):
    output, _ = prepared(tmp_path, trust)
    path = output / target
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"\n# modified\n")
    with pytest.raises(ValueError):
        serving.validate_prepared(output, trust[1])


def test_modified_payload_and_recomputed_unsigned_marker_still_fail(tmp_path, trust):
    output, _ = prepared(tmp_path, trust)
    payload = output / "structure.nq"
    payload.chmod(0o644)
    payload.write_bytes(payload.read_bytes() + b'<urn:fake> <urn:fake:p> "fake" <urn:fake:g> .\n')
    marker_path = output / "serving.json"
    marker = json.loads(marker_path.read_bytes())
    marker["graphs"]["structure"]["sha256"] = release.file_hash(payload)
    marker_path.chmod(0o644)
    marker_path.write_bytes(release.canonical(marker))
    with pytest.raises(ValueError, match="independently verified"):
        serving.validate_prepared(output, trust[1])


def test_unknown_file_or_symlink_cannot_enter_release(tmp_path, trust):
    output, _ = prepared(tmp_path, trust)
    (output / "unexpected").write_text("unexpected")
    with pytest.raises(ValueError, match="undeclared"):
        serving.validate_prepared(output, trust[1])
    (output / "unexpected").unlink()
    (output / "nested").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        serving.validate_prepared(output, trust[1])


def test_install_both_families_idempotently_and_activate_with_cas(tmp_path, trust, authorization_guard):
    output, result = prepared(tmp_path, trust)
    root = tmp_path / "volume"
    assert serving.load_active(root, None) is None
    installed = serving.install(root, output, trust[1], authorization_guard=authorization_guard)
    assert serving.install(root, output, trust[1], authorization_guard=authorization_guard) == installed
    assert serving.read_pointer(root) is None
    pointer = serving.activate(root, result["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    assert pointer["sequence"] == 1 and pointer["previous_release_id"] is None
    active = serving.load_active(root, trust[1])
    assert active["release_id"] == result["release_id"]
    assert active["bundle_path"] == root / "releases" / result["release_id"] / "bundle"
    with pytest.raises(ValueError, match="compare-and-swap"):
        serving.activate(root, result["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    with pytest.raises(ValueError, match="already active"):
        serving.activate(root, result["release_id"], trust[1], expected_current=result["release_id"], expected_sequence=1, authorization_guard=authorization_guard)


def test_prepared_and_installed_public_data_is_readable_by_distinct_api_uid(tmp_path, trust, authorization_guard):
    output, result = prepared(tmp_path, trust)
    volume = tmp_path / "volume"
    serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    installed = volume / "releases" / result["release_id"]
    for root in (output, installed):
        assert stat.S_IMODE(root.stat().st_mode) == 0o755
        for path in root.rglob("*"):
            assert stat.S_IMODE(path.stat().st_mode) == (0o755 if path.is_dir() else 0o444)
    assert stat.S_IMODE(volume.stat().st_mode) == 0o2775
    assert stat.S_IMODE((volume / "releases").stat().st_mode) == 0o2775
    previous_umask = serving.os.umask(0o077)
    try:
        serving.activate(volume, result["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    finally:
        serving.os.umask(previous_umask)
    assert stat.S_IMODE((volume / "active.json").stat().st_mode) == 0o444


def test_rollback_advances_sequence_and_revalidates_previous(tmp_path, trust, authorization_guard):
    output_a, a = prepared(tmp_path, trust, "a")
    output_b, b = prepared(tmp_path, trust, "b")
    root = tmp_path / "volume"
    for output in (output_a, output_b):
        serving.install(root, output, trust[1], authorization_guard=authorization_guard)
    serving.activate(root, a["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    serving.activate(root, b["release_id"], trust[1], expected_current=a["release_id"], expected_sequence=1, authorization_guard=authorization_guard)
    pointer = serving.rollback(root, trust[1], expected_current=b["release_id"], expected_sequence=2, authorization_guard=authorization_guard)
    assert pointer["release_id"] == a["release_id"] and pointer["sequence"] == 3
    with pytest.raises(ValueError, match="compare-and-swap"):
        serving.activate(root, b["release_id"], trust[1], expected_current=a["release_id"], expected_sequence=1, authorization_guard=authorization_guard)


def test_live_reader_lock_prevents_activation(tmp_path, trust, authorization_guard):
    output, result = prepared(tmp_path, trust)
    root = tmp_path / "volume"
    serving.install(root, output, trust[1], authorization_guard=authorization_guard)
    with serving.publication_lock(root, shared=True):
        with pytest.raises(ValueError, match="stop Fuseki"):
            serving.activate(root, result["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    assert serving.read_pointer(root) is None


def test_interrupted_install_leaves_no_release_or_pointer(tmp_path, trust, monkeypatch, authorization_guard):
    output, result = prepared(tmp_path, trust)
    root = tmp_path / "volume"
    def fail_copy(*_args, **_kwargs):
        raise OSError("TEST ONLY interrupted copy")
    monkeypatch.setattr(serving.shutil, "copytree", fail_copy)
    with pytest.raises(OSError, match="interrupted"):
        serving.install(root, output, trust[1], authorization_guard=authorization_guard)
    assert not (root / "releases" / result["release_id"]).exists()
    assert not list((root / "releases").glob(".installing-*"))
    assert serving.read_pointer(root) is None


def test_interrupted_pointer_replace_preserves_previous(tmp_path, trust, monkeypatch, authorization_guard):
    output, result = prepared(tmp_path, trust)
    root = tmp_path / "volume"
    serving.install(root, output, trust[1], authorization_guard=authorization_guard)
    def fail_replace(*_args):
        raise OSError("TEST ONLY interrupted replace")
    monkeypatch.setattr(serving.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        serving.activate(root, result["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    assert serving.read_pointer(root) is None
    assert not list(root.glob(".active-*"))


@pytest.mark.parametrize("value", ["../x", "/tmp/x", "a" * 63, "A" * 64, "a" * 64 + "\n", None])
def test_release_path_injection_rejected(value):
    with pytest.raises(ValueError, match="full lowercase SHA-256"):
        serving.release_id(value)


def test_active_release_needs_key_and_rejects_different_trust(tmp_path, trust, authorization_guard):
    output, result = prepared(tmp_path, trust)
    root = tmp_path / "volume"
    serving.install(root, output, trust[1], authorization_guard=authorization_guard)
    serving.activate(root, result["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    with pytest.raises(ValueError, match="trusted public review key"):
        serving.load_active(root, None)
    wrong = tmp_path / "wrong.pem"
    wrong.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.PEM,
                                                                          serialization.PublicFormat.SubjectPublicKeyInfo))
    with pytest.raises(ValueError, match="signature"):
        serving.load_active(root, wrong)


def test_root_symlink_and_pointer_symlink_rejected(tmp_path, trust):
    root = tmp_path / "volume"
    serving.initialize(root)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        serving.initialize(alias)
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    (root / "active.json").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        serving.read_pointer(root)


def test_compose_activation_checks_real_container_state(monkeypatch):
    spec = importlib.util.spec_from_file_location("graph_release_cli_test", ROOT / "scripts" / "graph_releases.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "run", lambda args: "container-id" if "ps" in args else "true")
    with pytest.raises(ValueError, match="Stop api and fuseki"):
        cli.require_stopped()


def test_payload_transform_does_not_copy_other_family_assertions(tmp_path, trust):
    # Pure transform test; intentionally incomplete assertions are never validated,
    # prepared, installed or signed after this test-only mutation.
    source = bundle(tmp_path, trust)
    result = release.validate_bundle(source, trust[1])
    for family in serving.FAMILIES:
        path = source / "inputs" / f"{family}.ttl"
        data = Graph().parse(path, format="turtle")
        ident = URIRef(f"urn:test-only:{family}:assertion")
        data.add((ident, RDF.type, release.LA.Assertion))
        data.add((ident, release.LA.graphFamily, Literal(family)))
        path.chmod(0o644)
        data.serialize(path, format="turtle")
    # Only the private transform is exercised here. The altered test manifest has
    # no valid review signature and cannot pass any serving publication operation.
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for family in serving.FAMILIES:
        relative = f"inputs/{family}.ttl"
        manifest["files"][relative] = serving.file_hash(source / relative)
    manifest_path.chmod(0o644)
    manifest_path.write_bytes(serving.canonical(manifest))
    result["bundle_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for family in serving.FAMILIES:
        raw, meta = serving._payload(source, result, family)
        parsed = Dataset().parse(data=raw, format="nquads")
        graph = parsed.graph(URIRef(meta["graph_iri"]))
        assert set(graph.subjects(RDF.type, release.LA.Assertion)) == {
            URIRef(f"urn:test-only:{family}:assertion")
        }


def test_initialize_rejects_special_lock_without_waiting(tmp_path):
    root = tmp_path / "volume"
    root.mkdir()
    serving.os.mkfifo(root / "publication.lock")
    with pytest.raises(ValueError, match="regular file"):
        serving.initialize(root)


def test_source_bundle_rejects_blank_nodes_before_partitioning(tmp_path):
    paths = {}
    for family in serving.FAMILIES:
        paths[family] = tmp_path / f"{family}.ttl"
        paths[family].write_text('<urn:test-only:resource> <urn:test-only:detail> [ <urn:test-only:label> "test" ] .')
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    with pytest.raises(ValueError, match="stable identifiers; blank nodes"):
        release.create_bundle(ROOT / "ontology", paths, evidence, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_payload_regeneration_rejects_post_verification_source_change(tmp_path, trust):
    source = bundle(tmp_path, trust)
    result = release.validate_bundle(source, trust[1])
    changed = source / "inputs" / "structure.ttl"
    changed.chmod(0o644)
    changed.write_text('<urn:test-only:changed> <urn:test-only:label> "changed" .')
    with pytest.raises(ValueError, match="changed after bundle validation"):
        serving._payload(source, result, "structure")


def test_runtime_loader_uses_private_hash_verified_copy(tmp_path, trust, monkeypatch, authorization_guard):
    output, result = prepared(tmp_path, trust)
    volume = tmp_path / "volume"
    serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    spec = importlib.util.spec_from_file_location("fuseki_runtime_test", ROOT / "deploy/fuseki/runtime.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    work = tmp_path / "work"
    work.mkdir()
    calls = []
    def invoke(args, **kwargs):
        calls.append(args)
        if "tdb2.tdbloader" in args:
            private_source = Path(args[-1])
            assert private_source.parent == work
            assert serving.file_hash(private_source) == result["graphs"]["structure"]["sha256"]
            source = volume / "releases" / result["release_id"] / "structure.nq"
            source.chmod(0o644)
            source.write_text("changed original after private copy")
        rows = [{"g": {"value": result["graphs"]["structure"]["graph_iri"]},
                 "count": {"value": str(result["graphs"]["structure"]["triple_count"])}},
                {"g": {"value": result["metadata_graph_iri"]}, "count": {"value": "5"}}]
        return runtime.subprocess.CompletedProcess(args, 0, stdout=json.dumps({"results": {"bindings": rows}}).encode())
    monkeypatch.setattr(runtime.subprocess, "run", invoke)
    runtime.compile_dataset(result, volume, work, "structure")
    assert len(calls) == 2


def test_runtime_never_compiles_modified_public_payload(tmp_path, trust, monkeypatch, authorization_guard):
    output, result = prepared(tmp_path, trust)
    volume = tmp_path / "volume"
    serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    source = volume / "releases" / result["release_id"] / "structure.nq"
    source.chmod(0o644)
    source.write_text("changed original before private copy")
    spec = importlib.util.spec_from_file_location("fuseki_runtime_changed_test", ROOT / "deploy/fuseki/runtime.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("Jena must not run"))
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(ValueError, match="changed after release validation"):
        runtime.compile_dataset(result, volume, work, "structure")


@pytest.mark.parametrize("action", ["install", "activate", "rollback"])
def test_signed_transitions_universally_require_live_guard(tmp_path, trust, authorization_guard, action):
    output, result = prepared(tmp_path, trust)
    volume = tmp_path / "volume"
    if action != "install":
        serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    with pytest.raises(ValueError, match="requires a live authorization guard"):
        if action == "install":
            serving.install(volume, output, trust[1])
        elif action == "activate":
            serving.activate(volume, result["release_id"], trust[1], expected_current=None)
        else:
            serving.rollback(volume, trust[1], expected_current=result["release_id"], expected_sequence=1)
    assert serving.read_pointer(volume) is None
    if action == "install":
        assert not volume.exists()


def test_install_guard_runs_under_lock_even_for_existing_release(tmp_path, trust):
    output, result = prepared(tmp_path, trust)
    volume, calls = tmp_path / "volume", []

    @contextmanager
    def guard(info, action):
        assert action == "install"
        assert info["release_id"] == result["release_id"]
        assert info["serving_sha256"] == result["serving_sha256"]
        assert info["ontology_sha256"] == result["ontology_sha256"]
        assert info["review"] == result["review"]
        descriptor = serving._lock_descriptor(volume, ".install.lock")
        try:
            with pytest.raises(BlockingIOError):
                serving.fcntl.flock(descriptor, serving.fcntl.LOCK_EX | serving.fcntl.LOCK_NB)
        finally:
            serving.os.close(descriptor)
        calls.append(info["bundle_path"])
        yield
        assert serving.validate_prepared(volume / "releases" / result["release_id"], trust[1])
        assert serving.read_pointer(volume) is None

    # Installing remains permitted while Fuseki holds its shared publication lock.
    serving.initialize(volume)
    with serving.publication_lock(volume, shared=True):
        serving.install(volume, output, trust[1], authorization_guard=guard)
        serving.install(volume, output, trust[1], authorization_guard=guard)
    assert calls == [output / "bundle", volume / "releases" / result["release_id"] / "bundle"]


def test_activation_and_rollback_guards_hold_publication_lock_through_commit(tmp_path, trust, authorization_guard):
    volume, calls = tmp_path / "volume", []
    a, first = prepared(tmp_path, trust, "a")
    b, second = prepared(tmp_path, trust, "b")
    for output in (a, b):
        serving.install(volume, output, trust[1], authorization_guard=authorization_guard)

    @contextmanager
    def guard(info, action):
        with pytest.raises(ValueError, match="stop Fuseki"):
            with serving.publication_lock(volume, shared=True):
                pytest.fail("Publication EX must precede the live authorization guard")
        calls.append((info["release_id"], action))
        yield
        assert serving.read_pointer(volume)["release_id"] == info["release_id"]
        with pytest.raises(ValueError, match="stop Fuseki"):
            with serving.publication_lock(volume, shared=True):
                pytest.fail("Guard exit must remain inside publication EX")

    serving.activate(volume, first["release_id"], trust[1], expected_current=None, authorization_guard=guard)
    serving.activate(volume, second["release_id"], trust[1], expected_current=first["release_id"],
                     expected_sequence=1, authorization_guard=guard)
    serving.rollback(volume, trust[1], expected_current=second["release_id"], expected_sequence=2,
                     authorization_guard=guard)
    assert calls == [(first["release_id"], "activate"), (second["release_id"], "activate"),
                     (first["release_id"], "rollback")]


@pytest.mark.parametrize("action", ["install", "activate", "rollback"])
def test_guard_entry_denial_does_not_change_release_state(tmp_path, trust, authorization_guard, action):
    volume = tmp_path / "volume"
    output, result = prepared(tmp_path, trust)
    if action != "install":
        serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    if action == "rollback":
        serving.activate(volume, result["release_id"], trust[1], expected_current=None,
                         authorization_guard=authorization_guard)
        other, second = prepared(tmp_path, trust, "b")
        serving.install(volume, other, trust[1], authorization_guard=authorization_guard)
        serving.activate(volume, second["release_id"], trust[1], expected_current=result["release_id"],
                         expected_sequence=1, authorization_guard=authorization_guard)
    before = serving.read_pointer(volume)

    @contextmanager
    def denied(info, guard_action):
        assert guard_action == action
        raise ValueError("TEST ONLY review is stale")
        yield  # pragma: no cover

    with pytest.raises(ValueError, match="review is stale"):
        if action == "install":
            serving.install(volume, output, trust[1], authorization_guard=denied)
        elif action == "activate":
            serving.activate(volume, result["release_id"], trust[1], expected_current=None, authorization_guard=denied)
        else:
            serving.rollback(volume, trust[1], expected_current=before["release_id"], expected_sequence=2,
                             authorization_guard=denied)
    assert serving.read_pointer(volume) == before
    if action == "install":
        assert not list((volume / "releases").iterdir())


@pytest.mark.parametrize("action", ["install", "activate", "rollback"])
def test_guard_exit_failure_retains_commit_and_reports_ambiguous_outcome(tmp_path, trust, authorization_guard, action):
    volume = tmp_path / "volume"
    output, result = prepared(tmp_path, trust)
    if action != "install":
        serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    if action == "rollback":
        serving.activate(volume, result["release_id"], trust[1], expected_current=None,
                         authorization_guard=authorization_guard)
        other, second = prepared(tmp_path, trust, "b")
        serving.install(volume, other, trust[1], authorization_guard=authorization_guard)
        serving.activate(volume, second["release_id"], trust[1], expected_current=result["release_id"],
                         expected_sequence=1, authorization_guard=authorization_guard)

    @contextmanager
    def final_failure(info, guard_action):
        yield
        raise ValueError("TEST ONLY private authorization detail must not escape")

    with pytest.raises(serving.TransitionOutcomeUnknown, match="transition may have committed; reconcile pointer") as error:
        if action == "install":
            serving.install(volume, output, trust[1], authorization_guard=final_failure)
        elif action == "activate":
            serving.activate(volume, result["release_id"], trust[1], expected_current=None,
                             authorization_guard=final_failure)
        else:
            serving.rollback(volume, trust[1], expected_current=second["release_id"], expected_sequence=2,
                             authorization_guard=final_failure)
    assert "private authorization detail" not in str(error.value)
    assert serving.validate_prepared(volume / "releases" / result["release_id"], trust[1])["release_id"] == result["release_id"]
    if action == "install":
        assert serving.read_pointer(volume) is None
    else:
        assert serving.load_active(volume, trust[1])["release_id"] == result["release_id"]
        assert serving.read_pointer(volume)["sequence"] == (3 if action == "rollback" else 1)
    assert not list(volume.glob(".active-*"))
    assert not list((volume / "releases").glob(".installing-*"))


@pytest.mark.parametrize("action", ["prepare", "install"])
@pytest.mark.parametrize("kind", ["empty_directory", "directory_with_content", "symlink"])
def test_atomic_publication_never_replaces_concurrent_destination(tmp_path, trust, authorization_guard, monkeypatch, action, kind):
    output, result = prepared(tmp_path, trust)
    source = tmp_path / "unrelated"
    source.mkdir()
    (source / "private").write_text("must survive")
    destination = tmp_path / "raced-preparation" if action == "prepare" else tmp_path / "volume" / "releases" / result["release_id"]
    original = serving._rename_exclusive

    def race(stage, final):
        assert final == destination
        if kind == "symlink":
            final.symlink_to(source, target_is_directory=True)
        else:
            final.mkdir()
            if kind == "directory_with_content":
                (final / "sentinel").write_text("must survive")
        original(stage, final)

    monkeypatch.setattr(serving, "_rename_exclusive", race)
    with pytest.raises(FileExistsError):
        if action == "prepare":
            serving.prepare(output / "bundle", trust[1], destination)
        else:
            serving.install(tmp_path / "volume", output, trust[1], authorization_guard=authorization_guard)
    assert destination.exists()
    assert not (destination / "serving.json").exists()
    assert not list(destination.parent.glob(".preparing-*"))
    assert not list(destination.parent.glob(".installing-*"))
    if kind == "directory_with_content":
        assert (destination / "sentinel").read_text() == "must survive"
    if kind == "symlink":
        assert destination.is_symlink()
        assert (source / "private").read_text() == "must survive"


def test_install_rejects_different_coherently_signed_copy(tmp_path, trust, authorization_guard, monkeypatch):
    output, result = prepared(tmp_path, trust)
    other, second = prepared(tmp_path, trust, "b")
    volume = tmp_path / "volume"
    original = serving.shutil.copytree

    def substitute(source, destination, *args, **kwargs):
        return original(other if source == output else source, destination, *args, **kwargs)

    monkeypatch.setattr(serving.shutil, "copytree", substitute)
    with pytest.raises(ValueError, match="changed during installation"):
        serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    assert not list((volume / "releases").iterdir())
    assert serving.read_pointer(volume) is None


def test_activation_rechecks_pointer_after_guard_entry(tmp_path, trust, authorization_guard):
    output, result = prepared(tmp_path, trust)
    volume = tmp_path / "volume"
    serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    intervening = {"format_version": 1, "release_id": result["release_id"], "serving_sha256": result["serving_sha256"],
                   "previous_release_id": None, "sequence": 1}

    @contextmanager
    def noncooperating_change(info, action):
        (volume / "active.json").write_bytes(serving.canonical(intervening))
        yield

    with pytest.raises(ValueError, match="compare-and-swap"):
        serving.activate(volume, result["release_id"], trust[1], expected_current=None,
                         authorization_guard=noncooperating_change)
    assert serving.read_pointer(volume) == intervening


def test_rollback_reads_pointer_only_inside_publication_lock(tmp_path, trust, authorization_guard, monkeypatch):
    volume = tmp_path / "volume"
    a, first = prepared(tmp_path, trust, "a")
    b, second = prepared(tmp_path, trust, "b")
    for output in (a, b):
        serving.install(volume, output, trust[1], authorization_guard=authorization_guard)
    serving.activate(volume, first["release_id"], trust[1], expected_current=None, authorization_guard=authorization_guard)
    serving.activate(volume, second["release_id"], trust[1], expected_current=first["release_id"],
                     expected_sequence=1, authorization_guard=authorization_guard)
    original = serving.read_pointer

    def locked_read(root):
        with pytest.raises(ValueError, match="stop Fuseki"):
            with serving.publication_lock(root, shared=True):
                pytest.fail("Rollback target must be selected under publication EX")
        return original(root)

    monkeypatch.setattr(serving, "read_pointer", locked_read)
    result = serving.rollback(volume, trust[1], expected_current=second["release_id"], expected_sequence=2,
                              authorization_guard=authorization_guard)
    assert result["release_id"] == first["release_id"]


def test_initialize_does_not_chmod_already_correct_shared_paths(tmp_path, monkeypatch):
    volume = tmp_path / "volume"
    serving.initialize(volume)
    assert stat.S_IMODE(volume.stat().st_mode) == 0o2775
    assert stat.S_IMODE((volume / "releases").stat().st_mode) == 0o2775
    for name in ("publication.lock", ".install.lock"):
        assert stat.S_IMODE((volume / name).stat().st_mode) == 0o644
    monkeypatch.setattr(Path, "chmod", lambda *args, **kwargs: pytest.fail("Different UID cannot chmod existing paths"))
    monkeypatch.setattr(serving.os, "fchmod", lambda *args, **kwargs: pytest.fail("Different UID cannot chmod existing locks"))
    serving.initialize(volume)


@pytest.mark.parametrize("name", ["publication.lock", ".install.lock"])
def test_initialize_rejects_symlink_lock(tmp_path, name):
    volume = tmp_path / "volume"
    volume.mkdir()
    target = tmp_path / "target"
    target.write_text("private sentinel")
    (volume / name).symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        serving.initialize(volume)
    assert target.read_text() == "private sentinel"
