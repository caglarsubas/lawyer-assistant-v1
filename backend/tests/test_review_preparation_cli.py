"""Private temporary CLI I/O fixtures; never uses deployment data, keys or reviews."""

import hashlib
import hmac
import importlib.util
import json
import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("review_preparation_cli_tests", ROOT / "scripts" / "prepare_legal_review.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class FakeStore:
    def __init__(self, key=b"TEST ONLY: preparation deployment A"):
        self.key = key

    def preparation_mac(self, raw):
        return hmac.new(self.key, raw, hashlib.sha256).hexdigest()


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def files():
    return {"binding.json": b'{"operator_id":"TEST-ONLY-operator","source_id":"source"}',
            "registry.json": b'{"schema_version":"TEST-ONLY"}', "resolutions.json": b'{}',
            "review-report.json": b'{"signed":false,"publication_eligible":false}',
            "candidate/exact.txt": "Türkçe\nİkinci satır ⚖️.".encode()}


def materialize(tmp_path, files, store, name="packet"):
    destination = tmp_path / name
    identity = cli.atomic_packet(destination, cli.sealed_files(files, store))
    return destination, identity


def rewrite_manifest(path, manifest, store):
    raw = cli.canonical(manifest)
    (path / "manifest.json").write_bytes(raw)
    (path / "manifest.sha256").write_text(cli.digest(raw) + "\n")
    (path / "manifest.hmac").write_text(store.preparation_mac(raw) + "\n")


def test_exact_sealed_packet_roundtrip_is_deterministic_and_private(tmp_path, files, store):
    sealed = cli.sealed_files(files, store)
    assert sealed == cli.sealed_files(dict(reversed(list(files.items()))), store)
    output, identity = materialize(tmp_path, files, store)
    assert identity == (output.stat().st_dev, output.stat().st_ino)
    result, digest = cli.read_packet(output, store)
    assert result == files and digest == cli.digest(sealed["manifest.json"])
    manifest = json.loads(sealed["manifest.json"])
    assert manifest["signed"] is False and manifest["publication_eligible"] is False
    assert manifest["confidentiality"] == "firm_confidential"
    assert all(stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
               for path in (output, *output.rglob("*")))
    assert not list(tmp_path.glob(".legal-review-*")) and not list(tmp_path.glob("*.preparation-lock"))


def test_deep_intermediate_directories_remain_private_even_with_permissive_umask(tmp_path, store):
    prior = os.umask(0)
    try:
        output, _ = materialize(tmp_path, {"one/two/three/data.bin": b"TEST ONLY"}, store)
    finally:
        os.umask(prior)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in (output, *[p for p in output.rglob("*") if p.is_dir()]))


@pytest.mark.parametrize("target", ["binding.json", "registry.json", "resolutions.json", "candidate/exact.txt",
                                    "manifest.json", "manifest.sha256", "manifest.hmac"])
def test_tampering_any_packet_component_is_rejected(tmp_path, files, store, target):
    output, _ = materialize(tmp_path, files, store)
    path = output / target
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises((ValueError, OSError)):
        cli.read_packet(output, store)


def test_recomputed_plaintext_inventory_cannot_reseal_a_changed_identity_plan(tmp_path, files, store):
    output, _ = materialize(tmp_path, files, store)
    altered = b'{"schema_version":"replaced-identity-plan"}'
    (output / "registry.json").write_bytes(altered)
    manifest = json.loads((output / "manifest.json").read_bytes())
    manifest["files"]["registry.json"] = {"sha256": cli.digest(altered), "bytes": len(altered)}
    raw = cli.canonical(manifest)
    (output / "manifest.json").write_bytes(raw)
    (output / "manifest.sha256").write_text(cli.digest(raw) + "\n")
    with pytest.raises(ValueError, match="seal"):
        cli.read_packet(output, store)
    with pytest.raises(ValueError, match="seal"):
        cli.read_packet(output, FakeStore(b"TEST ONLY: different deployment key"))


@pytest.mark.parametrize("field,value", [("signed", True), ("publication_eligible", True),
                                         ("confidentiality", "public"), ("schema_version", "unknown")])
def test_even_a_locally_sealed_packet_cannot_claim_publication_eligibility(tmp_path, files, store, field, value):
    output, _ = materialize(tmp_path, files, store)
    manifest = json.loads((output / "manifest.json").read_bytes())
    manifest[field] = value
    rewrite_manifest(output, manifest, store)
    with pytest.raises(ValueError, match="Unsupported"):
        cli.read_packet(output, store)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "a//b", "a/./b", "a\\b",
                                  "", "a\x00b", "manifest.json", "manifest.hmac", "manifest.sha256"])
def test_invalid_or_reserved_output_paths_are_rejected(files, store, name):
    with pytest.raises(ValueError):
        cli.sealed_files({**files, name: b"TEST ONLY"}, store)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a//b", "a/./b", "a\\b"])
def test_resealed_traversal_manifest_is_rejected_before_opening_paths(tmp_path, files, store, name):
    output, _ = materialize(tmp_path, files, store)
    manifest = json.loads((output / "manifest.json").read_bytes())
    manifest["files"][name] = {"sha256": cli.digest(b"x"), "bytes": 1}
    rewrite_manifest(output, manifest, store)
    with pytest.raises(ValueError, match="relative path"):
        cli.read_packet(output, store)


@pytest.mark.parametrize("change", ["extra_file", "extra_directory", "missing", "symlink", "hardlink", "fifo"])
def test_packet_inventory_rejects_extra_missing_linked_and_special_entries(tmp_path, files, store, change):
    output, _ = materialize(tmp_path, files, store)
    original = output / "registry.json"
    if change == "extra_file":
        (output / "extra.bin").write_bytes(b"x")
    elif change == "extra_directory":
        (output / "empty-unlisted-directory").mkdir()
    elif change == "missing":
        original.unlink()
    elif change == "symlink":
        original.unlink()
        original.symlink_to(output / "resolutions.json")
    elif change == "hardlink":
        os.link(original, tmp_path / "external-hardlink")
    elif change == "fifo":
        original.unlink()
        os.mkfifo(original)
    with pytest.raises((ValueError, OSError)):
        cli.read_packet(output, store)


def test_parent_symlink_is_rejected_for_read_and_output(tmp_path, files, store):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(actual, target_is_directory=True)
    (actual / "test.bin").write_bytes(b"TEST ONLY")
    with pytest.raises(ValueError, match="Symbolic"):
        cli.read_file(link / "test.bin", 100)
    with pytest.raises(ValueError, match="Symbolic"):
        cli.atomic_packet(link / "output", cli.sealed_files(files, store))


def test_existing_output_is_never_modified(tmp_path, files, store):
    output, _ = materialize(tmp_path, files, store)
    expected = {str(path.relative_to(output)): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="new"):
        cli.atomic_packet(output, {"replacement": b"do not overwrite"})
    assert expected == {str(path.relative_to(output)): path.read_bytes() for path in output.rglob("*") if path.is_file()}


def test_exclusive_rename_does_not_replace_a_concurrent_empty_destination(tmp_path, files, store, monkeypatch):
    output = tmp_path / "packet"
    real_rename = cli._rename_exclusive

    def race(stage, destination):
        destination.mkdir()
        real_rename(stage, destination)

    monkeypatch.setattr(cli, "_rename_exclusive", race)
    with pytest.raises(OSError):
        cli.atomic_packet(output, cli.sealed_files(files, store))
    assert output.is_dir() and list(output.iterdir()) == []
    assert not list(tmp_path.glob(".legal-review-*"))
    assert not (tmp_path / ".packet.preparation-lock").exists()


def test_cleanup_never_deletes_a_replacement_created_after_rename(tmp_path, files, store, monkeypatch):
    output = tmp_path / "packet"
    relocated = tmp_path / "relocated-own-packet"
    real_rename = cli._rename_exclusive

    def replace_after_rename(stage, destination):
        real_rename(stage, destination)
        destination.rename(relocated)
        destination.mkdir()
        (destination / "unrelated.txt").write_text("Do not delete replacement")

    monkeypatch.setattr(cli, "_rename_exclusive", replace_after_rename)
    try:
        identity = cli.atomic_packet(output, cli.sealed_files(files, store))
    except (ValueError, OSError):
        identity = None
    cli._remove_own_output(output, identity)
    assert (output / "unrelated.txt").read_text() == "Do not delete replacement"
    assert (relocated / "manifest.json").is_file()


@pytest.mark.parametrize("replacement", [False, True], ids=["owned-output", "unrelated-replacement"])
def test_reservation_cleanup_failure_after_rename_discards_only_owned_output(
    tmp_path, files, store, monkeypatch, replacement,
):
    output = tmp_path / "packet"
    reservation = tmp_path / ".packet.preparation-lock"
    relocated = tmp_path / "relocated-own-packet"
    original_unlink = Path.unlink
    reached_cleanup = []

    def fail_reservation_cleanup(path, *args, **kwargs):
        if path == reservation:
            reached_cleanup.append(True)
            # The directory has already been renamed, but atomic_packet has not
            # returned its inode to the caller's created variable yet.
            assert (output / "manifest.json").is_file()
            if replacement:
                output.rename(relocated)
                output.mkdir()
                (output / "unrelated.txt").write_bytes(b"Do not delete replacement")
            original_unlink(path, *args, **kwargs)
            raise OSError("TEST ONLY reservation unlink failed after rename")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_reservation_cleanup)
    with pytest.raises(OSError, match="reservation unlink failed"):
        cli.atomic_packet(output, cli.sealed_files(files, store))
    assert reached_cleanup == [True]
    assert not list(tmp_path.glob(".legal-review-*"))
    assert not reservation.exists()
    if replacement:
        assert (output / "unrelated.txt").read_bytes() == b"Do not delete replacement"
        assert (relocated / "manifest.json").is_file()
    else:
        assert not output.exists()


def test_cleanup_removes_only_the_exact_owned_inode(tmp_path, files, store):
    output, identity = materialize(tmp_path, files, store)
    cli._remove_own_output(output, (identity[0], identity[1] + 1))
    assert output.is_dir()
    cli._remove_own_output(output, identity)
    assert not output.exists()


def test_enclosing_authorization_can_explicitly_store_five_levels_but_packets_stay_at_four(tmp_path, store):
    record = {"packet/candidate/sources/" + "a" * 64 + "/raw.bin": b"SYNTHETIC TEST ONLY"}
    with pytest.raises(ValueError, match="Unsafe packet-relative path"):
        cli.atomic_packet(tmp_path / "default-depth", record)
    assert not (tmp_path / "default-depth").exists()
    output = tmp_path / "private-authorization"
    cli._inventory(record, max_depth=5)
    identity = cli.atomic_packet(output, record, max_depth=5)
    assert (output / next(iter(record))).read_bytes() == b"SYNTHETIC TEST ONLY"
    with pytest.raises(ValueError, match="Unsafe packet-relative path"):
        cli.sealed_files(record, store)
    cli._remove_own_output(output, identity)
    assert not output.exists()


@pytest.mark.parametrize("depth", [3, 6, True, "5"])
def test_authorization_path_exception_cannot_expand_arbitrarily(tmp_path, depth):
    with pytest.raises(ValueError, match="Unsupported packet path depth"):
        cli.atomic_packet(tmp_path / "output", {"a": b"b"}, max_depth=depth)
    assert not (tmp_path / "output").exists()


def test_existing_reservation_is_not_removed_by_another_preparer(tmp_path, files, store):
    reservation = tmp_path / ".packet.preparation-lock"
    reservation.write_text("Another invocation owns this")
    with pytest.raises(FileExistsError):
        cli.atomic_packet(tmp_path / "packet", cli.sealed_files(files, store))
    assert reservation.read_text() == "Another invocation owns this"


def test_evidence_has_exact_digest_names_byte_budgets_and_no_links(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    raw = b"TEST ONLY rights material"
    path = evidence / (cli.digest(raw) + ".bin")
    path.write_bytes(raw)
    assert cli.evidence_files(evidence) == {cli.digest(raw): raw}
    path.write_bytes(b"Changed rights material")
    with pytest.raises(ValueError, match="digest mismatch"):
        cli.evidence_files(evidence)
    path.write_bytes(raw)
    monkeypatch.setattr(cli, "MAX_EVIDENCE_FILE", 3)
    with pytest.raises(ValueError, match="bounded"):
        cli.evidence_files(evidence)


@pytest.mark.parametrize("case", ["unknown_name", "subdirectory", "symlink", "hardlink", "fifo"])
def test_evidence_directory_rejects_unsafe_entries(tmp_path, case):
    root = tmp_path / "evidence"
    root.mkdir()
    data = b"TEST ONLY evidence"
    path = root / (cli.digest(data) + ".bin")
    if case == "unknown_name":
        (root / "private-name.txt").write_bytes(data)
    elif case == "subdirectory":
        path.mkdir()
    elif case == "symlink":
        target = tmp_path / "elsewhere.bin"
        target.write_bytes(data)
        path.symlink_to(target)
    elif case == "hardlink":
        target = tmp_path / "elsewhere.bin"
        target.write_bytes(data)
        os.link(target, path)
    else:
        os.mkfifo(path)
    with pytest.raises((ValueError, OSError)):
        cli.evidence_files(root)


@pytest.mark.parametrize("raw", [b'{"same":1,"same":2}', b'{"number":NaN}', b'{"number":Infinity}', b'\xff'])
def test_json_rejects_duplicate_fields_nonfinite_numbers_and_non_utf8(raw):
    with pytest.raises(ValueError):
        cli.parse_json(raw)


def test_io_budgets_count_entries_and_bytes(tmp_path, files, store, monkeypatch):
    monkeypatch.setattr(cli, "MAX_FILES", 1)
    with pytest.raises(ValueError, match="budget"):
        cli.sealed_files(files, store)
    monkeypatch.setattr(cli, "MAX_FILES", 256)
    monkeypatch.setattr(cli, "MAX_PACKET", 3)
    with pytest.raises(ValueError, match="budget"):
        cli.sealed_files(files, store)
    monkeypatch.setattr(cli, "MAX_PACKET", 96 * 1024 * 1024)
    monkeypatch.setattr(cli, "MAX_FILE", 1)
    with pytest.raises(ValueError, match="content"):
        cli.sealed_files(files, store)


@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch, store):
    import app.release_snapshot as snapshots

    binding = {"operator_id": "TEST-ONLY-operator", "source_id": "a" * 64,
               "source_review_revision": 5, "mapping_revision": 2, "firm_id": "TEST-ONLY-firm"}
    snapshot = {"binding": binding}
    settings = SimpleNamespace(public_source_dir=tmp_path / "public-only")
    registry = tmp_path / "registry.json"
    registry.write_bytes(b'{"schema_version":"TEST-ONLY-registry"}')
    resolutions = tmp_path / "resolutions.json"
    resolutions.write_bytes(b'{"schema_version":"TEST-ONLY-resolutions"}')
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    prepared = {"binding.json": cli.canonical(binding), "registry.json": registry.read_bytes(),
                "resolutions.json": resolutions.read_bytes(), "review-report.json": b'{"rdf_generated":false}'}
    summary = {"signed": False, "publication_eligible": False, "rdf_generated": False, "mapping_count": 1}

    @contextmanager
    def readonly(settings):
        yield store

    @contextmanager
    def locked(*args, **kwargs):
        yield snapshot

    monkeypatch.setattr(snapshots, "readonly_store", readonly)
    monkeypatch.setattr(snapshots, "locked_snapshot", locked)
    compiler = SimpleNamespace(compile_review=lambda *args: (prepared, summary))
    monkeypatch.setitem(sys.modules, "app.release_preparation", compiler)
    arguments = {"operator_id": binding["operator_id"], "source_id": binding["source_id"],
                 "expected_source_review_revision": 5, "expected_mapping_revision": 2,
                 "registry": registry, "resolutions": resolutions, "evidence_dir": evidence,
                 "output": tmp_path / "output"}
    return settings, arguments, snapshots, compiler, prepared, snapshot


def test_prepare_second_live_check_must_match_before_writing(fake_pipeline, monkeypatch):
    settings, arguments, snapshots, _, _, snapshot = fake_pipeline
    calls = 0

    @contextmanager
    def changed(*args, **kwargs):
        nonlocal calls
        calls += 1
        yield snapshot if calls == 1 else {"binding": {**snapshot["binding"], "mapping_revision": 3}}

    monkeypatch.setattr(snapshots, "locked_snapshot", changed)
    with pytest.raises(ValueError, match="changed before"):
        cli.prepare(settings, **arguments)
    assert not arguments["output"].exists()


def test_final_snapshot_failure_removes_own_atomic_output(fake_pipeline, monkeypatch):
    settings, arguments, snapshots, _, _, snapshot = fake_pipeline
    calls = 0

    @contextmanager
    def changed_after_output(*args, **kwargs):
        nonlocal calls
        calls += 1
        yield snapshot
        if calls == 2:
            raise ValueError("Final source-byte validation failed")

    monkeypatch.setattr(snapshots, "locked_snapshot", changed_after_output)
    with pytest.raises(ValueError, match="Final source"):
        cli.prepare(settings, **arguments)
    assert not arguments["output"].exists()
    assert not list(arguments["output"].parent.glob(".legal-review-*"))


def test_validation_rebuild_compares_every_file(fake_pipeline, monkeypatch):
    settings, arguments, _, compiler, prepared, _ = fake_pipeline
    result = cli.prepare(settings, **arguments)
    assert result["current_at_validation"] is True
    assert cli.validate(settings, arguments["output"], operator_id=arguments["operator_id"])["packet_sha256"] == result["packet_sha256"]
    compiler.compile_review = lambda *args: ({**prepared, "review-report.json": b"Changed live ontology or review"}, {})
    with pytest.raises(ValueError, match="differs from current"):
        cli.validate(settings, arguments["output"], operator_id=arguments["operator_id"])


def test_validation_detects_packet_tamper_during_live_rebuild(fake_pipeline):
    settings, arguments, _, compiler, prepared, _ = fake_pipeline
    cli.prepare(settings, **arguments)

    def corrupt_then_rebuild(*args):
        (arguments["output"] / "registry.json").write_bytes(b"Changed after initial seal check")
        return prepared, {}

    compiler.compile_review = corrupt_then_rebuild
    with pytest.raises(ValueError):
        cli.validate(settings, arguments["output"], operator_id=arguments["operator_id"])


@pytest.mark.parametrize("failure", [ValueError, OSError, RuntimeError, KeyboardInterrupt])
def test_main_failure_output_never_echoes_private_error_details(monkeypatch, capsys, failure):
    monkeypatch.setattr(cli, "load_settings", lambda: SimpleNamespace())

    def fail(*args, **kwargs):
        raise failure("PRIVATE REVIEW NOTE /Users/secret/api-key-value")

    monkeypatch.setattr(cli, "validate", fail)
    assert cli.main(["validate", "private-packet", "--operator-id", "private-reviewer-id"]) != 0
    captured = capsys.readouterr()
    assert captured.out == "" and "No publication was performed" in captured.err
    assert "PRIVATE" not in captured.err and "api-key-value" not in captured.err and "private-reviewer-id" not in captured.err


def test_argument_errors_never_echo_unknown_values_or_load_settings(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda: pytest.fail("Invalid args must not read configuration"))
    with pytest.raises(SystemExit) as error:
        cli.main(["validate", "packet", "--operator-id", "TEST-ONLY-operator", "--private-secret", "DO-NOT-ECHO"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "DO-NOT-ECHO" not in captured.err and "private-secret" not in captured.err
    assert "Invalid review preparation arguments" in captured.err


# Real application-ledger integration remains entirely under pytest's temporary
# demo database and invented source package. No deployment reviews are created.
from test_provision_mappings import mapping as mapping_fixture  # noqa: E402
from test_provision_mappings import source as source_fixture  # noqa: E402
from test_provision_mappings import workspace as workspace_fixture  # noqa: E402
from test_release_snapshot import counts as ledger_counts  # noqa: E402
from test_release_snapshot import operator_id  # noqa: E402
from test_source_reviews import assess, assign  # noqa: E402

mapping = mapping_fixture
source = source_fixture
workspace = workspace_fixture


@pytest.fixture
def live_pipeline(mapping, tmp_path):
    from app.release_snapshot import REQUIRED_USES

    app, client, sources, source_id, base = mapping
    private_proof = b"TEST ONLY PRIVATE MATERIAL CANARY: rights and identity evidence, never legal proof"
    proof_hash = cli.digest(private_proof)
    assert assign(client, base + "/review").status_code == 200
    for revision, category in enumerate(("rights", "source_identity", "extraction", "legal"), start=1):
        options = {"evidence_refs": [{"reference": "PRIVATE REVIEW REFERENCE CANARY", "sha256": proof_hash}]}
        if category == "rights":
            options["permitted_uses"] = sorted(REQUIRED_USES)
        response = assess(client, base + "/review", revision, category, **options)
        assert response.status_code == 200, response.text
    candidates = client.get(base + "/provision-candidates").json()["items"]
    assert len(candidates) == 2
    instrument = "urn:tr-law:instrument:test-only-closing-date"
    registry = {"schema_version": "legal-identity-registry-v1", "entities": [
        {"id": instrument, "kind": "instrument", "parent_id": None, "evidence_sha256": [proof_hash]}]}
    resolutions = {"schema_version": "provision-identity-resolutions-v1", "items": []}
    mapping_revision = 0
    for index, candidate in enumerate(candidates, start=1):
        proposed = client.post(base + "/provision-mappings", json={
            "expected_revision": mapping_revision, "expected_source_review_revision": 5,
            "candidate_id": candidate["id"], "start": candidate["proposed_span"]["start"],
            "end": candidate["proposed_span"]["end"], "kind": candidate["kind"], "label": candidate["label"],
            "rationale": "PRIVATE PROPOSAL CANARY: test-only exact source span"})
        assert proposed.status_code == 200, proposed.text
        mapping_revision += 1
        identifier = next(item["id"] for item in proposed.json()["items"] if item["candidate_id"] == candidate["id"])
        resolved = {"start": candidate["proposed_span"]["start"], "end": candidate["proposed_span"]["end"],
                    "instrument_ref": "PRIVATE INSTRUMENT CANARY", "provision_ref": "PRIVATE PROVISION CANARY",
                    "provision_version_ref": "PRIVATE VERSION CANARY", "valid_from": "2011-01-01",
                    "valid_until": "2012-01-01", "text_role": "operative_text" if index == 1 else "transitional_text"}
        accepted = client.post(base + f"/provision-mappings/{identifier}/review", json={
            "expected_revision": mapping_revision, "expected_source_review_revision": 5,
            "decision": "accepted", "rationale": "PRIVATE REVIEW RATIONALE CANARY: test only",
            "evidence_refs": [{"reference": "PRIVATE REVIEW PROOF CANARY", "sha256": proof_hash}],
            "resolution": resolved})
        assert accepted.status_code == 200, accepted.text
        mapping_revision += 1
        provision = f"urn:tr-law:provision:test-only-closing-date-{index}"
        version = f"urn:tr-law:provision-version:test-only-closing-date-{index}"
        registry["entities"] += [
            {"id": provision, "kind": "provision", "parent_id": instrument, "evidence_sha256": [proof_hash]},
            {"id": version, "kind": "provision_version", "parent_id": provision, "evidence_sha256": [proof_hash]}]
        resolutions["items"].append({"mapping_id": identifier, "instrument_id": instrument,
                                     "provision_id": provision, "provision_version_id": version})
    assert accepted.json()["handoff_ready"] and mapping_revision == 4
    registry_file, resolutions_file = tmp_path / "registry.json", tmp_path / "resolutions.json"
    registry_file.write_bytes(cli.canonical(registry))
    resolutions_file.write_bytes(cli.canonical(resolutions))
    evidence = tmp_path / "private-evidence-input"
    evidence.mkdir(mode=0o700)
    (evidence / (proof_hash + ".bin")).write_bytes(private_proof)
    arguments = {"operator_id": operator_id(app), "source_id": source_id,
                 "expected_source_review_revision": 5, "expected_mapping_revision": 4,
                 "registry": registry_file, "resolutions": resolutions_file, "evidence_dir": evidence,
                 "output": tmp_path / "prepared-review"}
    return mapping, arguments, private_proof


def test_real_prepare_validate_pipeline_is_deterministic_readonly_private_and_never_publishable(live_pipeline):
    from rdflib import Graph, Literal, Namespace

    from app.graph_release import _load_serving
    from app.release_snapshot import readonly_store

    release = _load_serving()._release
    mapping, arguments, proof = live_pipeline
    app, _, sources, source_id, _ = mapping
    before = ledger_counts(app)
    before_source = {path.name: path.read_bytes() for path in (sources.root / source_id).iterdir()}
    before_key = (app.state.settings.data_dir / "demo-encryption.key").read_bytes()
    result = cli.prepare(app.state.settings, **arguments)
    assert result["rdf_generated"] and result["mapping_count"] == 2 and result["assertion_count"] == 4
    assert result["signed"] is False and result["publication_eligible"] is False
    assert result["current_at_validation"] is True
    validated = cli.validate(app.state.settings, arguments["output"], operator_id=arguments["operator_id"])
    assert validated == result
    again = cli.prepare(app.state.settings, **{**arguments, "output": arguments["output"].with_name("prepared-again")})
    assert again == result
    with readonly_store(app.state.settings) as reader:
        files, digest = cli.read_packet(arguments["output"], reader)
        assert digest == result["packet_sha256"]
        assert files == cli.read_packet(arguments["output"].with_name("prepared-again"), reader)[0]
    binding = json.loads(files["binding.json"])
    assert binding["source_review_revision"] == 5 and binding["mapping_revision"] == 4
    assert files[f"private-evidence/{cli.digest(proof)}.bin"] == proof
    for path, raw in files.items():
        if path.startswith("candidate/"):
            assert b"PRIVATE " not in raw and proof not in raw and arguments["operator_id"].encode() not in raw
            assert b"demo-firm" not in raw and b"Demo Avukat" not in raw
    la = Namespace("https://lawyer-assistant.local/ontology/")
    graphs = {family: Graph().parse(data=files[f"candidate/{family}.ttl"], format="turtle")
              for family in release.FAMILIES}
    for graph in graphs.values():
        assert list(graph.triples((None, la.reviewPreparationOnly, Literal(True))))
    with pytest.raises(ValueError, match="(?i)preparation"):
        release.check_data(graphs, ROOT / "ontology", {"verified": True})
    assert ledger_counts(app) == before
    assert (app.state.settings.data_dir / "demo-encryption.key").read_bytes() == before_key
    assert before_source == {path.name: path.read_bytes() for path in (sources.root / source_id).iterdir()}


@pytest.mark.parametrize("field", ["valid_from", "valid_until"])
def test_real_unknown_date_is_preserved_and_blocks_rdf_without_guessing(live_pipeline, field):
    from app.release_snapshot import readonly_store

    mapping, arguments, _ = live_pipeline
    app, client, _, _, base = mapping
    current = client.get(base + "/provision-mappings").json()["items"][0]
    resolution = {**current["resolution"], field: None}
    response = client.post(base + f"/provision-mappings/{current['id']}/review", json={
        "expected_revision": 4, "expected_source_review_revision": 5, "decision": "accepted",
        "rationale": "TEST ONLY unknown endpoint stays unknown", "evidence_refs": current["last_event"]["evidence_refs"],
        "resolution": resolution})
    assert response.status_code == 200, response.text
    arguments["expected_mapping_revision"] = 5
    result = cli.prepare(app.state.settings, **arguments)
    assert result["rdf_generated"] is False and "unknown_" + field in result["blocker_codes"]
    with readonly_store(app.state.settings) as reader:
        files, _ = cli.read_packet(arguments["output"], reader)
    assert "candidate/structure.ttl" not in files and "candidate/jurisprudence.ttl" not in files
    report = json.loads(files["review-report.json"])
    assert any(item[field] is None for item in report["mapping_unknowns"])
    assert cli.validate(app.state.settings, arguments["output"], operator_id=arguments["operator_id"]) == result


@pytest.mark.parametrize("change", ["source_review", "mapping_review", "rights", "source_bytes", "identity_plan", "ontology"])
def test_real_validation_rejects_changed_live_inputs_or_resealed_plan(live_pipeline, change, tmp_path):
    import shutil

    from app.release_snapshot import SnapshotError, readonly_store

    mapping, arguments, _ = live_pipeline
    app, client, sources, source_id, base = mapping
    cli.prepare(app.state.settings, **arguments)
    options = {}
    if change in {"source_review", "rights"}:
        category = "rights" if change == "rights" else "legal"
        options = {"permitted_uses": ["local_processing", "internal_display"]} if category == "rights" else {}
        assert assess(client, base + "/review", 5, category, **options).status_code == 200
        options = {}
    elif change == "mapping_review":
        current = client.get(base + "/provision-mappings").json()["items"][0]
        response = client.post(base + f"/provision-mappings/{current['id']}/review", json={
            "expected_revision": 4, "expected_source_review_revision": 5, "decision": "rejected",
            "rationale": "TEST ONLY later reviewer rejection", "evidence_refs": [], "resolution": None})
        assert response.status_code == 200
    elif change == "source_bytes":
        raw = sources.root / source_id / "raw.bin"
        raw.chmod(0o600)
        raw.write_bytes(raw.read_bytes() + b"changed")
    elif change == "identity_plan":
        with readonly_store(app.state.settings) as reader:
            files, _ = cli.read_packet(arguments["output"], reader)
        changed = json.loads(files["registry.json"])
        changed["entities"][0]["id"] = "urn:tr-law:instrument:forged-test-only-id"
        raw = cli.canonical(changed)
        (arguments["output"] / "registry.json").write_bytes(raw)
        manifest = json.loads((arguments["output"] / "manifest.json").read_bytes())
        manifest["files"]["registry.json"] = {"sha256": cli.digest(raw), "bytes": len(raw)}
        unsealed = cli.canonical(manifest)
        (arguments["output"] / "manifest.json").write_bytes(unsealed)
        (arguments["output"] / "manifest.sha256").write_text(cli.digest(unsealed) + "\n")
    else:
        ontology = tmp_path / "changed-ontology"
        shutil.copytree(ROOT / "ontology", ontology)
        with (ontology / "domains.ttl").open("ab") as output:
            output.write(b"\n# TEST ONLY ontology revision\n")
        options["ontology_root"] = ontology
    with pytest.raises((ValueError, SnapshotError)):
        cli.validate(app.state.settings, arguments["output"], operator_id=arguments["operator_id"], **options)


def test_prepare_rechecks_just_written_packet_and_cleans_its_tampered_inode(fake_pipeline, monkeypatch):
    settings, arguments, _, _, _, _ = fake_pipeline
    real_atomic = cli.atomic_packet

    def changed_after_output(output, packet):
        identity = real_atomic(output, packet)
        (output / "registry.json").write_bytes(b"Changed immediately after atomic rename")
        return identity

    monkeypatch.setattr(cli, "atomic_packet", changed_after_output)
    with pytest.raises(ValueError):
        cli.prepare(settings, **arguments)
    assert not arguments["output"].exists()


def test_prepare_rejects_replaced_packet_but_preserves_unrelated_replacement(fake_pipeline, monkeypatch, store):
    settings, arguments, _, _, _, _ = fake_pipeline
    real_atomic = cli.atomic_packet
    relocated = arguments["output"].with_name("original-owned-packet")

    def replaced_after_output(output, packet):
        identity = real_atomic(output, packet)
        output.rename(relocated)
        real_atomic(output, cli.sealed_files({"replacement.bin": b"Preserve this unrelated artifact"}, store))
        return identity

    monkeypatch.setattr(cli, "atomic_packet", replaced_after_output)
    with pytest.raises(ValueError):
        cli.prepare(settings, **arguments)
    assert (arguments["output"] / "replacement.bin").read_bytes() == b"Preserve this unrelated artifact"
    assert (relocated / "manifest.json").is_file()
