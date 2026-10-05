"""Physical R01 byte verification must not confer authenticity or disclose private input."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from app import qualification_evidence as evidence
from app.research_qualification import ResearchDossier

SEED = Path(__file__).resolve().parents[2] / "qualification/research-dossier.json"


@pytest.fixture
def payload():
    return json.loads(SEED.read_bytes())


@pytest.fixture
def directory(tmp_path):
    # macOS's system temp aliases are outside the directory under test. Use its
    # actual test location, then introduce explicit symlinks in the adversarial cases.
    target = tmp_path.resolve() / "evidence"
    target.mkdir()
    return target


def add_evidence(payload, directory, *, content=b"Unverified operator-provided evidence.", kind="real", suffix="a",
                 measurement=True):
    digest = hashlib.sha256(content).hexdigest()
    record_id = f"evidence-{suffix}"
    payload["evidence_records"].append({
        "evidence_id": record_id, "sha256": digest, "sample_kind": kind,
        "recorded_on": payload["recorded_on"], "owner_role": "evaluation_owner",
    })
    if measurement:
        payload["measurements"].append({
            "measurement_id": f"measurement-{suffix}", "evidence_id": record_id,
            "sample_kind": kind, "practice": "contracts", "unit": "pages", "observed_units": 1,
            "elapsed_seconds": None, "reviewer_seconds": None, "assessed_items": None, "disagreements": None,
        })
    path = directory / f"{digest}.bin"
    path.write_bytes(content)
    return path


def verify(payload, directory):
    return evidence.verify_research_evidence(ResearchDossier.model_validate(payload), directory)


def assert_safe_failure(action):
    with pytest.raises(ValueError) as caught:
        action()
    assert str(caught.value) == evidence.FAILURE
    assert caught.value.__suppress_context__ is True


def test_empty_inventory_is_not_vacuous_evidence_verification(payload, directory):
    result = verify(payload, directory)
    assert result["status"] == "no_records"
    assert result["verified_file_count"] == result["verified_bytes"] == 0
    assert result["declared_evidence_counts"] == {"real": 0, "synthetic": 0}
    assert result["declared_measurement_counts"] == {"real": 0, "synthetic": 0}
    assert result["source_authenticity_verified"] is False
    assert result["review_authenticated"] is False
    assert result["metadata_authenticated"] is False
    assert result["source_identity_deduplication"] == "not_evaluated"
    assert result["sample_independence"] == "not_established"
    assert result["production_qualified"] is False
    assert result["runtime_authorization"] == "none"


def test_different_artifact_hashes_do_not_establish_independent_samples(payload, directory):
    add_evidence(payload, directory, content=b'{"sample":"same-underlying-case","version":1}')
    add_evidence(payload, directory, content=b'{ "sample": "same-underlying-case", "version": 1 }', suffix="b")
    result = verify(payload, directory)
    assert result["verified_file_count"] == 2
    assert result["source_identity_deduplication"] == "not_evaluated"
    assert result["sample_independence"] == "not_established"


def test_all_declared_bytes_are_verified_without_approving_labels(payload, directory):
    first = add_evidence(payload, directory, content=b"Claimed real evidence.")
    second = add_evidence(payload, directory, content=b"Synthetic evidence.", kind="synthetic", suffix="b")
    third = add_evidence(payload, directory, content=b"Not linked to a measurement.", suffix="c", measurement=False)
    result = verify(payload, directory)
    assert result["status"] == "hashes_verified"
    assert result["verified_file_count"] == 3
    assert result["verified_bytes"] == sum(path.stat().st_size for path in (first, second, third))
    assert result["declared_evidence_counts"] == {"real": 2, "synthetic": 1}
    assert result["declared_measurement_counts"] == {"real": 1, "synthetic": 1}
    assert result["metadata_authenticated"] is False
    assert result["source_authenticity_verified"] is False
    assert result["review_authenticated"] is False
    assert result["runtime_authorization"] == "none"


def test_zero_byte_file_proves_only_its_empty_digest(payload, directory):
    add_evidence(payload, directory, content=b"")
    result = verify(payload, directory)
    assert result["status"] == "hashes_verified" and result["verified_bytes"] == 0
    assert result["source_authenticity_verified"] is False


@pytest.mark.parametrize("change", ["missing", "hash_mismatch", "unknown", "unknown_subdirectory"])
def test_exact_inventory_and_hash_fail_closed(payload, directory, change):
    path = add_evidence(payload, directory)
    if change == "missing":
        path.unlink()
    elif change == "hash_mismatch":
        path.write_bytes(b"Changed contents")
    elif change == "unknown":
        (directory / "confidential-extra.txt").write_text("secret")
    else:
        (directory / "extra").mkdir()
    assert_safe_failure(lambda: verify(payload, directory))


def test_unknown_files_rejected_even_without_evidence_records(payload, directory):
    (directory / "raw.bin").write_bytes(b"unreferenced")
    assert_safe_failure(lambda: verify(payload, directory))


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory"])
def test_special_or_linked_evidence_rejected_without_hanging(payload, directory, kind):
    path = add_evidence(payload, directory)
    path.unlink()
    external = directory.parent / "external"
    external.write_bytes(b"external contents")
    if kind == "symlink":
        path.symlink_to(external)
    elif kind == "hardlink":
        os.link(external, path)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()
    assert_safe_failure(lambda: verify(payload, directory))


@pytest.mark.parametrize("where", ["leaf", "ancestor"])
def test_directory_symlinks_are_never_followed(payload, directory, where):
    add_evidence(payload, directory)
    if where == "leaf":
        link = directory.parent / "alias"
        link.symlink_to(directory, target_is_directory=True)
        supplied = link
    else:
        link = directory.parent.parent / "ancestor-alias"
        link.symlink_to(directory.parent, target_is_directory=True)
        supplied = link / directory.name
    assert_safe_failure(lambda: verify(payload, supplied))


def test_ancestor_replacement_during_traversal_cannot_redirect_reads(payload, directory, monkeypatch):
    add_evidence(payload, directory)
    original_open = os.open
    replaced = False
    replacement = directory.parent / "moved-evidence"

    def racing_open(path, flags, *args, **kwargs):
        nonlocal replaced
        descriptor = original_open(path, flags, *args, **kwargs)
        if path == directory.name and not replaced:
            replaced = True
            directory.rename(replacement)
            directory.symlink_to(replacement, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(evidence.os, "open", racing_open)
    assert_safe_failure(lambda: verify(payload, directory))
    assert replaced


@pytest.mark.parametrize("change", ["rewrite", "replace_identical", "replace_directory", "append_unknown"])
def test_second_capture_detects_changes_after_first_read(payload, directory, monkeypatch, change):
    path = add_evidence(payload, directory)
    capture = evidence._capture
    changed = False

    def changing_capture(*args, **kwargs):
        nonlocal changed
        result = capture(*args, **kwargs)
        if not changed:
            changed = True
            if change == "rewrite":
                path.write_bytes(b"same-file changed contents")
            elif change == "replace_identical":
                replacement = directory.parent / "replacement"
                replacement.write_bytes(path.read_bytes())
                replacement.replace(path)
            elif change == "replace_directory":
                directory.rename(directory.parent / "moved")
                directory.mkdir()
                (directory / path.name).write_bytes(b"replacement")
            else:
                (directory / "secret-extra").write_bytes(b"private")
        return result

    monkeypatch.setattr(evidence, "_capture", changing_capture)
    assert_safe_failure(lambda: verify(payload, directory))
    assert changed


def test_mutation_while_streaming_rejected(payload, directory, monkeypatch):
    path = add_evidence(payload, directory, content=b"a" * (evidence.CHUNK_BYTES * 2))
    original_read = os.read
    changed = False

    def racing_read(descriptor, size):
        nonlocal changed
        value = original_read(descriptor, size)
        if not changed:
            changed = True
            with path.open("ab") as stream:
                stream.write(b"appended during read")
        return value

    monkeypatch.setattr(evidence.os, "read", racing_read)
    assert_safe_failure(lambda: verify(payload, directory))


def test_final_file_binding_check_detects_rewrite_after_second_capture(payload, directory, monkeypatch):
    path = add_evidence(payload, directory)
    capture = evidence._capture
    calls = 0

    def changing_capture(*args, **kwargs):
        nonlocal calls
        result = capture(*args, **kwargs)
        calls += 1
        if calls == 2:
            path.write_bytes(b"changed after the second complete capture")
        return result

    monkeypatch.setattr(evidence, "_capture", changing_capture)
    assert_safe_failure(lambda: verify(payload, directory))
    assert calls == 2


def test_summary_never_echoes_content_paths_hashes_or_secret_shaped_ids(payload, directory):
    private = b"sk-fakeapikey-value; Client Jane Doe case details"
    path = add_evidence(payload, directory, content=private)
    secret_id = "sk-" + "a" * 40
    payload["evidence_records"][0]["evidence_id"] = secret_id
    payload["measurements"][0]["evidence_id"] = secret_id
    payload["measurements"][0]["measurement_id"] = "confidential-client-case"
    text = json.dumps(verify(payload, directory))
    for secret in (private.decode(), str(directory), path.name, secret_id, "confidential-client-case"):
        assert secret not in text
    path.write_bytes(b"tampered " + private)
    assert_safe_failure(lambda: verify(payload, directory))


def test_revalidates_mutated_dossier_before_file_access(payload, directory, monkeypatch):
    dossier = ResearchDossier.model_validate(payload)
    dossier.providers[0].gates[0].evidence_ids.append("absent-secret-evidence")

    def unexpected_read(*args, **kwargs):
        pytest.fail("An invalid dossier reached the directory reader")

    monkeypatch.setattr(evidence, "read_exact_directory", unexpected_read)
    assert_safe_failure(lambda: evidence.verify_research_evidence(dossier, directory))


def test_reader_accepts_exact_calibration_inventory(directory):
    expected = {"sample.json": b"{}", "raw.bin": b"source", "extraction.json": b"{}", "reference.json": b"{}"}
    for name, content in expected.items():
        (directory / name).write_bytes(content)
    assert evidence.read_exact_directory(directory, {name: 32 for name in expected}, 128) == expected


@pytest.mark.parametrize("filename", ["../raw.bin", "/tmp/raw.bin", "credentials.json", "private-case-id.bin",
                                      "A" * 64 + ".bin", "0" * 64 + ".bin\n"])
def test_reader_rejects_non_fixed_or_unsafe_names(directory, filename):
    assert_safe_failure(lambda: evidence.read_exact_directory(directory, {filename: 10}, 10))


@pytest.mark.parametrize("limits,total", [({"raw.bin": True}, 10), ({"raw.bin": 0}, 10),
                                         ({"raw.bin": evidence.MAX_FILE_BYTES + 1}, 10),
                                         ({"raw.bin": 10}, True), ({"raw.bin": 10}, 0),
                                         ({"raw.bin": 10}, evidence.MAX_TOTAL_BYTES + 1)])
def test_reader_limits_are_strict_and_bounded(directory, limits, total):
    assert_safe_failure(lambda: evidence.read_exact_directory(directory, limits, total))


def test_per_file_size_is_checked_before_read(directory, monkeypatch):
    (directory / "raw.bin").write_bytes(b"12345")

    def unexpected_read(*args, **kwargs):
        pytest.fail("An oversized file reached streaming read")

    monkeypatch.setattr(evidence.os, "read", unexpected_read)
    assert_safe_failure(lambda: evidence.read_exact_directory(directory, {"raw.bin": 4}, 100))


def test_aggregate_size_budget_is_enforced_across_files(directory):
    (directory / "raw.bin").write_bytes(b"12345")
    (directory / "sample.json").write_bytes(b"12345")
    assert_safe_failure(lambda: evidence.read_exact_directory(directory, {"raw.bin": 5, "sample.json": 5}, 9))
    assert evidence.read_exact_directory(directory, {"raw.bin": 5, "sample.json": 5}, 10)["raw.bin"] == b"12345"


def test_inventory_bound_applies_before_opening_directory(directory, monkeypatch):
    specifications = {f"{value:064x}.bin": 1 for value in range(evidence.MAX_FILES + 1)}

    def unexpected_open(*args, **kwargs):
        pytest.fail("An excessive inventory reached filesystem access")

    monkeypatch.setattr(evidence.os, "open", unexpected_open)
    assert_safe_failure(lambda: evidence.read_exact_directory(directory, specifications, 10))


def test_directory_parent_traversal_rejected(directory):
    assert_safe_failure(lambda: evidence.read_exact_directory(directory / ".." / directory.name, {}, 10))


def test_inventory_enumeration_stops_at_first_unknown(directory, monkeypatch):
    original_scandir = os.scandir
    yielded = 0

    class BoundedEntries:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            nonlocal yielded
            for _ in range(1_000_000):
                yielded += 1
                yield type("Entry", (), {"name": "private-unknown-name"})()

    monkeypatch.setattr(evidence.os, "scandir", lambda _: BoundedEntries())
    assert_safe_failure(lambda: evidence.read_exact_directory(directory, {}, 10))
    assert yielded == 1
    monkeypatch.setattr(evidence.os, "scandir", original_scandir)
