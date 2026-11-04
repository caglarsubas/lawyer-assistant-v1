"""Actual read-only reconstruction, hostile descriptors and offline native evidence."""

import hashlib
import json
import shutil
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import cold_controller_fixture as seed  # noqa: E402
import native_operator_preview as retained  # noqa: E402
import native_preview_restart as previous  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from operator_cold_recovery import identity, inventory, recover  # noqa: E402


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    work = tmp_path_factory.mktemp("cold-controller")
    work.chmod(0o700)
    old = retained.WORK
    retained.WORK = work
    try:
        f, selected, target, roots = previous.fixture()
    finally:
        retained.WORK = old
    anchors = work / "anchors"
    pins = seed.retain(f, selected, target, roots, anchors, "a" * 64)
    before = [inventory(root) for root in roots]
    f.store.engine.dispose()
    yield f, target, roots, anchors, pins
    assert before == [inventory(root) for root in roots]
    f.store.engine.dispose()


def test_cold_load_retains_original_actors_versions_and_expiry_without_database_writes(frozen):
    f, target, roots, anchors, pins = frozen
    database = f.profile / "disposable-identities.sqlite"
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    loaded = recover(f.root, anchors, pins, clock=lambda: f.now)
    try:
        assert loaded.original_handoff.record() == target.record()
        assert loaded.binding.validate()[0].actor(f.scope("reviewer"), "reviewer")["user_id"] == f.ids["reviewer"]
        with loaded.store.session() as session:
            with pytest.raises(OperationalError) as rejected:
                session.execute(text("CREATE TABLE forbidden_cold_recovery_write (id integer)"))
            assert rejected.value.orig.sqlite_errorcode == sqlite3.SQLITE_READONLY
        assert hashlib.sha256(database.read_bytes()).hexdigest() == before
        assert tuple(x.root for x in (
            loaded.binding.adapter.service.reconciler.disposition.source.service.planner.source,
            loaded.binding.adapter.service.reconciler.disposition.source.service.planner.journal)) == roots[:2]
    finally:
        loaded.close()


def test_active_or_interrupted_key_maintenance_blocks_cold_recovery(frozen):
    f, _, _, anchors, pins = frozen
    marker = f.profile / ".runtime-key-rotation"
    for dangling in (False, True):
        try:
            if dangling:
                marker.symlink_to(f.profile / "missing-maintenance-record")
            else:
                marker.write_bytes(b"invented active key maintenance")
                marker.chmod(0o600)
            with pytest.raises(ValueError):
                recover(f.root, anchors, pins, clock=lambda: f.now)
        finally:
            marker.unlink(missing_ok=True)


@pytest.mark.parametrize("fault", ["missing_pins", "descriptor", "handoff", "binding", "profile", "database", "case", "anchors", "expired"])
def test_original_independent_pins_and_original_expiry_are_required(frozen, fault):
    f, _, _, anchors, pins = frozen
    changed = pins
    def clock():
        return f.now + (301 if fault == "expired" else 0)
    if fault == "missing_pins":
        changed = None
    elif fault in {"descriptor", "handoff", "binding", "profile"}:
        changed = replace(pins, **{fault + "_sha256": "0" * 64})
    elif fault in {"database", "case", "anchors"}:
        changed = replace(pins, **{fault + "_identity": (0, 0)})
    with pytest.raises((ValueError, FileExistsError)):
        recover(f.root, anchors, changed, clock=clock)


@pytest.mark.parametrize("fault", ["duplicate_json", "unknown_field", "path_escape", "store_identity", "changed_inventory",
    "missing_key", "wrong_key", "key_permissions", "key_symlink", "receipt_bytes", "provenance_bytes", "renewed_handoff"])
def test_malformed_or_changed_retention_is_never_adopted(frozen, tmp_path, fault):
    f, _, _, original, pins = frozen
    anchors = tmp_path / "anchors"
    shutil.copytree(original, anchors)
    anchors.chmod(0o700)
    descriptor = e.decode((anchors / "controller.json").read_bytes())
    if fault == "duplicate_json":
        raw = b'{"schema":"one","schema":"two"}'
    elif fault == "unknown_field":
        descriptor["renew_authority"] = True
    elif fault == "path_escape":
        descriptor["stores"]["source"]["path"] = "../receipts"
    elif fault == "store_identity":
        descriptor["stores"]["source"]["identity"] = [0, 0]
    elif fault == "changed_inventory":
        descriptor["stores"]["journal"]["inventory"] = []
    elif fault == "missing_key":
        (anchors / "source.key").unlink()
    elif fault == "wrong_key":
        (anchors / "source.key").write_bytes(b"x" * 32)
    elif fault == "key_permissions":
        (anchors / "source.key").chmod(0o644)
    elif fault == "key_symlink":
        (anchors / "source.key").unlink()
        (anchors / "source.key").symlink_to(original / "source.key")
    elif fault in {"receipt_bytes", "provenance_bytes"}:
        (anchors / ("receipt.json" if fault == "receipt_bytes" else "provenance.json")).write_bytes(b"{}")
    else:
        path = anchors / "handoff.json"
        record = e.decode(path.read_bytes())
        record["created_at"] += 1
        record["expires_at"] += 1
        path.write_bytes(e.encode(record))
    if fault != "duplicate_json":
        raw = e.encode(descriptor)
    (anchors / "controller.json").write_bytes(raw)
    independent = replace(pins, anchors_identity=identity(anchors), descriptor_sha256=e.sha(raw))
    # A separately selected hash still cannot relax shape, original handoff or keys.
    with pytest.raises((ValueError, OSError)):
        recover(f.root, anchors, independent, clock=lambda: f.now)


def test_completed_native_cold_report_and_all_predecessor_sources_stay_bound():
    path = ROOT / "docs/evidence/native-cold-controller-2026-11-04.json"
    value = json.loads(path.read_bytes())
    from native_cold_controller_report import validate
    assert validate(value["native"], value["native"]["package_manifest_sha256"])["qualified"]
    assert value["status"] == "qualified" and value["production_activation"] is False
    for name, expected in value["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    previous_report = ROOT / "docs/evidence/native-preview-restart-2026-11-03.json"
    assert hashlib.sha256(previous_report.read_bytes()).hexdigest() == value["prior_native_report_sha256"]


def test_native_report_requires_all_actual_cold_processes_outcomes_and_scope():
    from native_cold_controller_report import CASES, COUNTS, FALSE, TRUE, plan_sha256, validate
    sample = {"schema": "native-cold-controller-v1", "package_manifest_sha256": "a" * 64,
        "case_plan_sha256": plan_sha256(), "cases": [{"id": k, "state": v} for k, v in CASES.items()],
        "filesystem": "ext4", "SIGKILL_exitcodes": [-9, -9, -9],
        "fixture_scope": "invented_accounts_and_encrypted_metadata_only",
        "restart_scope": "spawned_cold_interpreters_original_pins_and_retained_files_only",
        **COUNTS, **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False)}
    assert validate(sample, "a" * 64)["cases"] == 30
    for key, invalid in {**dict.fromkeys(TRUE, False), **dict.fromkeys(FALSE, True),
        **dict.fromkeys(COUNTS, True), "cases": sample["cases"][:-1],
        "SIGKILL_exitcodes": [-9.0, -9, -9], "restart_scope": "warm_fork"}.items():
        with pytest.raises(ValueError):
            validate({**sample, key: invalid}, "a" * 64)
    with pytest.raises(ValueError):
        validate({**sample, "trust_approved": True}, "a" * 64)


def test_cold_harness_preserves_mount_policy_and_restores_original_controller_configuration():
    from unittest.mock import patch

    import qualify_native_cold_controller as cold
    import qualify_native_operator_preview as mounts
    fields = ("FILES", "LABEL", "arguments", "plan_sha256", "validate")
    before = {k: getattr(mounts, k) for k in fields}
    name = "lawyer-preview-native-" + "b" * 16
    volumes = {k: name + "-" + k for k in ("host", "stage", "work")}
    for preparing in (True, False):
        original = mounts.arguments("sha256:" + "a" * 64, name, volumes, preparing=preparing)
        candidate = cold.arguments("sha256:" + "a" * 64, name, volumes, preparing=preparing)
        assert candidate[:-2] == original[:-2] and candidate[-1] == original[-1]
        assert candidate[-2] == "/controller/native_cold_controller.py"
    with patch.object(mounts, "run", side_effect=ValueError("invented incomplete attempt")), pytest.raises(ValueError):
        cold.run("invented-public-dependencies")
    assert before == {k: getattr(mounts, k) for k in fields}
