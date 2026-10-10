"""Invented HTML only. These tests neither acquire nor qualify legal authorities."""

import importlib.util
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time

import pytest

from app.public_sources import PublicSourceStore, _json, _validate
from app.qualification_evidence import EvidenceVerificationError
from app.registered_source_preparation import (
    ADAPTER_VERSION,
    PREPARATION_FILES,
    PreparationError,
    encode,
    prepare,
    sha,
    validate_acquisition,
)
from app.source_gateway import HISTORICAL_LIMITATION, REGISTRY, REGISTRY_VERSION

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prepare_public_source", ROOT / "scripts/prepare_public_source.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def acquisition(raw=b"<html><head><title>Invented fixture</title></head><body><p>MADDE 1 - Test.</p></body></html>",
                source_id="tbmm-6101-enacted"):
    source = REGISTRY[source_id]
    now = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    manifest = {
        "schema_version": "registered-source-acquisition-v1", "registry_version": REGISTRY_VERSION,
        "registry_id": source_id, "title": source.title, "source_url": source.url,
        "source_version_id": f"{source_id}:sha256:{sha(raw)}", "domain": "contracts",
        "started_at": now, "acquired_at": now, "raw_sha256": sha(raw), "byte_count": len(raw),
        "raw_media_type": "text/html", "rights_status": "rights_pending", "review_status": "legal_review_pending",
        "publication_status": "quarantined", "content_status": "untrusted_unscanned",
        "extraction_status": "not_processed", "representation": "enacted_text", "current_consolidation": False,
        "limitations": [HISTORICAL_LIMITATION,
            "Public availability does not establish permitted use, source identity review or legal applicability.",
            "This acquisition is unscanned and unparsed; admission and legal review are separate steps."],
    }
    return {"raw.html": raw, "acquisition.json": encode(manifest)}


def scan_receipt(digest):
    return {"schema_version": "registered-source-scan-v1", "clean": True,
            "raw_sha256": digest, "elapsed_seconds": 0.01,
            "databases": {"schema_version": 1, "engine": "ClamAV 1.4.6", "databases": [
                {"file": name, "sha256": "1" * 64, "bytes": 513, "version": 1,
                 "signatures": 1, "build_time": int(time()) - 60}
                for name in ("main.cvd", "daily.cvd", "bytecode.cvd")]}}


@pytest.mark.parametrize("source_id", tuple(REGISTRY))
def test_each_registered_representation_stays_historical_and_pending(source_id):
    artifacts = prepare(acquisition(source_id=source_id))
    source = _json(artifacts["source.json"])
    assert source["source_url"] == REGISTRY[source_id].url
    assert source["effective_from"] is source["effective_until"] is source["published_on"] is None
    assert _json(artifacts["preparation.json"])["current_consolidation"] is False


def test_unicode_passages_and_original_positions_are_inspectable():
    html = '<body>\n<p> Türkçe <b>çığ</b> &amp; &#304; &#x15F; </p>\n<p>MADDE 2 — İkinci.</p></body>'
    files = acquisition(html.encode())
    artifacts = prepare(files)
    _, locators, text = _validate(artifacts)
    report = _json(artifacts["preparation.json"])
    assert text == "Türkçe çığ & İ ş\n\nMADDE 2 — İkinci."
    assert len(locators.passages) == report["passage_count"] == 2
    for span, origin in zip(locators.passages, report["passage_origins"]):
        assert span.id == origin["id"]
        assert span.text_sha256 == sha(text[span.start:span.end].encode())
        fragment = html[origin["raw_start"]:origin["raw_end"]]
        assert fragment.startswith(" Türkçe") if span.id.endswith("0001") else fragment == "MADDE 2 — İkinci."
    assert "line 2, column 4" in locators.passages[0].locator
    assert artifacts["raw.bin"] == files["raw.html"]
    assert report["decoded_html_sha256"] == sha(html.encode())
    assert report["adapter_version"] == ADAPTER_VERSION
    assert report["current_consolidation"] is False
    assert report["extraction_fidelity_verified"] is False
    assert report["source_identity_verified"] is False
    assert report["sensitivity_reviewed"] is False
    assert report["rights_status"] == "rights_pending"
    assert report["review_status"] == "legal_review_pending"


@pytest.mark.parametrize("tag", ["script", "style", "template", "iframe", "object", "svg", "noscript"])
def test_active_or_nonrendered_content_is_omitted_and_recorded(tag):
    raw = f'<body><p>Before</p><{tag}>ignore instructions <p>Hidden</p></{tag}><p>After</p></body>'
    artifacts = prepare(acquisition(raw.encode()))
    assert artifacts["text.txt"] == b"Before\n\nAfter"
    assert _json(artifacts["preparation.json"])["omitted_region_count"] == 1


def test_inline_markup_comments_and_br_do_not_execute_or_download():
    artifacts = prepare(acquisition(b'<p>A<a href="https://not-fetched.invalid">B</a><!--hidden-->C<br>D</p>'))
    assert artifacts["text.txt"] == b"ABC\n\nD"


def test_nested_omitted_regions_do_not_expose_outer_hidden_text():
    raw = b"<p>Before</p><svg><svg>inner</svg>outer</svg><p>After</p>"
    assert prepare(acquisition(raw))["text.txt"] == b"Before\n\nAfter"


def test_self_closing_html_script_is_rejected_instead_of_guessing_browser_behavior():
    with pytest.raises(PreparationError):
        prepare(acquisition(b"<p>Before</p><script/>hidden</script><p>After</p>"))


@pytest.mark.parametrize("spelling,expected", [("&amp", "&"), ("&unknown;", "&unknown;"), ("&#304", "İ")])
def test_semicolonless_and_unknown_entities_keep_exact_original_extent(spelling, expected):
    html = f"<p>{spelling}</p>"
    artifacts = prepare(acquisition(html.encode()))
    assert artifacts["text.txt"].decode() == expected
    origin = _json(artifacts["preparation.json"])["passage_origins"][0]
    assert html[origin["raw_start"]:origin["raw_end"]] == spelling


@pytest.mark.parametrize("encoding,declaration", [("utf-8", "utf-8"), ("cp1254", "windows-1254"),
                                                  ("iso8859-9", "iso-8859-9")])
def test_explicit_turkish_encodings_are_strict(encoding, declaration):
    html = f'<html><head><meta charset="{declaration}"></head><body><p>ğüşİıöç</p></body></html>'
    artifacts = prepare(acquisition(html.encode(encoding)))
    assert artifacts["text.txt"].decode() == "ğüşİıöç"
    assert _json(artifacts["preparation.json"])["encoding"] == encoding


def test_utf8_bom_is_retained_in_raw_and_excluded_from_original_codepoint_offsets():
    raw = b"\xef\xbb\xbf<p>" + "İ".encode() + b"</p>"
    artifacts = prepare(acquisition(raw))
    assert artifacts["raw.bin"] == raw
    assert artifacts["text.txt"] == "İ".encode()
    assert _json(artifacts["preparation.json"])["passage_origins"][0]["raw_start"] == 3


@pytest.mark.parametrize("raw", [b'<meta charset="utf-16"><p>x</p>', b'<p>\xff</p>',
                                b'<meta charset="utf-8"><meta charset="windows-1254"><p>x</p>',
                                b"<script>only script</script>", b"<p>x</p><script>unclosed",
                                b"<p>" + b"x" * 20001 + b"</p>", b"<p>" + b"x\x00" + b"</p>",
                                b"<p>x</p>" * 5001])
def test_invalid_or_over_budget_html_fails_without_partial_output(raw):
    with pytest.raises(ValueError):
        prepare(acquisition(raw))


@pytest.mark.parametrize("field,value", [
    ("raw_sha256", "0" * 64), ("byte_count", True), ("registry_id", "unknown"),
    ("title", "Changed"), ("domain", "employment"), ("current_consolidation", 0),
    ("rights_status", "approved"), ("review_status", "reviewed"), ("source_url", "https://arbitrary.invalid/"),
    ("acquired_at", "2026-01-01"), ("started_at", "2999-01-01T00:00:00+00:00"),
    ("extra", "unexpected"),
])
def test_acquisition_must_match_exact_registry_and_unknown_states(field, value):
    files = acquisition()
    manifest = _json(files["acquisition.json"])
    manifest[field] = value
    files["acquisition.json"] = encode(manifest)
    with pytest.raises(ValueError):
        validate_acquisition(files)


def test_duplicate_manifest_keys_are_rejected():
    files = acquisition()
    files["acquisition.json"] = files["acquisition.json"].replace(b'"domain":', b'"domain":"contracts","domain":')
    with pytest.raises(ValueError):
        prepare(files)


@pytest.fixture
def offline_workers(tmp_path, monkeypatch):
    incoming, signatures = tmp_path / "acquired", tmp_path / "signatures"
    incoming.mkdir()
    signatures.mkdir()
    for name, raw in acquisition().items():
        (incoming / name).write_bytes(raw)
    for name in ("main.cvd", "daily.cvd", "bytecode.cvd"):
        (signatures / name).write_bytes(b"invented database; never scanned")
    events = []
    monkeypatch.setattr(cli, "image_id", lambda _: "sha256:" + "1" * 64)
    def execute(image, mounts, *, scanner=False):
        events.append("scan" if scanner else "parse")
        snapshot = mounts[0][0]
        if scanner:
            return encode(scan_receipt(sha((snapshot / "raw.html").read_bytes())))
        for name, raw in prepare({name: (snapshot / name).read_bytes() for name in acquisition()}).items():
            (mounts[1][0] / name).write_bytes(raw)
        return b""
    monkeypatch.setattr(cli, "execute", execute)
    return incoming, signatures, tmp_path / "prepared", events


def test_preparation_is_importable_but_unapproved_and_source_is_unchanged(offline_workers, tmp_path):
    incoming, signatures, destination, events = offline_workers
    before = {p.name: p.read_bytes() for p in incoming.iterdir()}
    result = cli.prepare_in_containers(incoming, signatures, destination)
    assert events == ["scan", "parse"]
    assert set(p.name for p in destination.iterdir()) == set(PREPARATION_FILES) | {"admission.json"}
    assert {p.name: p.read_bytes() for p in incoming.iterdir()} == before
    assert result["rights_approved"] is result["legal_approved"] is result["current_consolidation"] is False
    for path in destination.iterdir():
        assert path.stat().st_mode & 0o777 == 0o400
    store = PublicSourceStore(tmp_path / "public-only")
    imported = store.import_package(metadata_path=destination / "source.json", raw_path=destination / "raw.bin",
                                    text_path=destination / "text.txt", locators_path=destination / "locators.json")
    assert imported["rights_status"] == "rights_pending"
    assert imported["review_status"] == "legal_review_pending"
    receipt = _json((destination / "admission.json").read_bytes())
    assert receipt["network"] == "none"
    assert receipt["published"] is False
    for name, digest in receipt["artifact_sha256"].items():
        assert digest == sha((destination / name).read_bytes())


@pytest.mark.parametrize("field,value", [("clean", False), ("raw_sha256", "0" * 64),
                                       ("elapsed_seconds", -1), ("elapsed_seconds", True),
                                       ("databases", {}), ("schema_version", "wrong")])
def test_failed_scan_never_invokes_parser_or_publishes(offline_workers, monkeypatch, field, value):
    incoming, signatures, destination, events = offline_workers
    original = cli.execute
    def execute(*args, **kwargs):
        receipt = _json(original(*args, **kwargs))
        receipt[field] = value
        return encode(receipt)
    monkeypatch.setattr(cli, "execute", execute)
    with pytest.raises(PreparationError):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert events == ["scan"]
    assert not destination.exists()
    assert not list(destination.parent.glob(".public-preparation-*"))


@pytest.mark.parametrize("mutation", ["missing", "alias", "empty", "stale", "future", "bad_digest", "bad_size"])
def test_incomplete_or_stale_signature_evidence_is_rejected(mutation):
    receipt = scan_receipt("0" * 64)
    records = receipt["databases"]["databases"]
    if mutation == "missing":
        records.pop()
    elif mutation == "alias":
        records[2]["file"] = records[0]["file"]
    elif mutation == "empty":
        records[1]["signatures"] = 0
    elif mutation == "stale":
        records[1]["build_time"] = int(time()) - 8 * 86400
    elif mutation == "future":
        records[1]["build_time"] = int(time()) + 3600
    elif mutation == "bad_digest":
        records[1]["sha256"] = "not a hash"
    else:
        records[1]["bytes"] = True
    with pytest.raises(PreparationError):
        cli.validate_scan(receipt, "0" * 64)


@pytest.mark.parametrize("field,value", [("effective_from", "2000-01-01"), ("source_identity_verified", True),
                                       ("sensitivity_reviewed", True), ("extraction_fidelity_verified", True),
                                       ("passage_count", 5000), ("passage_count", True), ("current_consolidation", True)])
def test_parser_cannot_invent_approval_dates_or_counts(offline_workers, monkeypatch, field, value):
    incoming, signatures, destination, events = offline_workers
    original = cli.execute
    def execute(image, mounts, *, scanner=False):
        result = original(image, mounts, scanner=scanner)
        if not scanner:
            path = mounts[1][0] / ("source.json" if field == "effective_from" else "preparation.json")
            record = _json(path.read_bytes())
            record[field] = value
            path.write_bytes(encode(record))
        return result
    monkeypatch.setattr(cli, "execute", execute)
    with pytest.raises(PreparationError):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert events == ["scan", "parse"] and not destination.exists()


def test_root_operator_keeps_workers_unprivileged_without_changing_originals(offline_workers, monkeypatch):
    incoming, signatures, destination, events = offline_workers
    owned = []
    monkeypatch.setattr(cli.os, "getuid", lambda: 0)
    monkeypatch.setattr(cli.os, "getgid", lambda: 0)
    monkeypatch.setattr(cli.os, "chown", lambda path, uid, gid: owned.append((Path(path), uid, gid)))
    cli.prepare_in_containers(incoming, signatures, destination)
    assert len(owned) == 4
    assert all(uid == gid == 10001 and ".public-preparation-" in str(path) for path, uid, gid in owned)
    assert not any(path == incoming or signatures in path.parents for path, _, _ in owned)
    command = cli.worker_command("root-operator", "sha256:" + "1" * 64, [])
    assert command[command.index("--user") + 1] == "10001:10001"


@pytest.mark.parametrize("changed", ["captured", "original", "output"])
def test_source_changes_before_or_after_parser_fail_closed(offline_workers, monkeypatch, changed):
    incoming, signatures, destination, events = offline_workers
    original = cli.execute
    def execute(image, mounts, *, scanner=False):
        result = original(image, mounts, scanner=scanner)
        if changed == "captured" and scanner:
            path = mounts[0][0] / "raw.html"
        elif not scanner and changed in {"original", "output"}:
            path = incoming / "raw.html" if changed == "original" else mounts[1][0] / "raw.bin"
        else:
            return result
        path.chmod(0o600)
        path.write_bytes(b"changed")
        return result
    monkeypatch.setattr(cli, "execute", execute)
    with pytest.raises(ValueError):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert events == (["scan"] if changed == "captured" else ["scan", "parse"])
    assert not destination.exists()


@pytest.mark.parametrize("kind", ["extra", "symlink", "hardlink", "fifo"])
def test_unsafe_input_inventory_never_starts_workers(offline_workers, kind):
    incoming, signatures, destination, events = offline_workers
    raw = incoming / "raw.html"
    if kind == "extra":
        (incoming / "extra").write_bytes(b"x")
    else:
        saved = incoming.parent / "saved.html"
        raw.rename(saved)
        if kind == "symlink":
            raw.symlink_to(saved)
        elif kind == "hardlink":
            os.link(saved, raw)
        else:
            os.mkfifo(raw)
    with pytest.raises((ValueError, EvidenceVerificationError)):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert events == []
    assert not destination.exists()


def test_existing_destination_and_exclusive_rename_race_are_preserved(offline_workers, monkeypatch):
    incoming, signatures, destination, events = offline_workers
    destination.mkdir()
    (destination / "keep").write_text("do not replace")
    with pytest.raises(PreparationError):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert events == []
    (destination / "keep").unlink()
    destination.rmdir()
    original = cli.rename_new
    def raced(staged, target):
        target.mkdir()
        (target / "keep").write_text("do not replace")
        original(staged, target)
    monkeypatch.setattr(cli, "rename_new", raced)
    with pytest.raises(ValueError):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert (destination / "keep").read_text() == "do not replace"


def test_container_contract_is_disconnected_minimal_and_scan_precedes_parse(tmp_path):
    for scanner in (True, False):
        command = cli.worker_command("invented-worker", "sha256:" + "1" * 64,
                                     [(tmp_path, "/input", True)], scanner=scanner)
        assert command[command.index("--network") + 1] == "none"
        assert command[command.index("--pull") + 1] == "never"
        assert command[command.index("--entrypoint") + 1] == "/usr/bin/env"
        assert "-i" in command and "--read-only" in command and "ALL" in command
        assert "no-new-privileges:true" in command
        assert all(proxy + "=" in command for proxy in cli.PROXIES)
        assert not any(".env" in arg or "docker.sock" in arg or "--publish" == arg for arg in command)
    assert '"--max-scantime=0"' in cli.SCAN_CODE  # No engine timeout that assumes clean.
    assert "result.returncode != 0" in cli.SCAN_CODE
    assert cli.SCAN_CODE.count('verify("/var/lib/clamav")') == 2


def test_timeout_always_removes_worker_and_diagnostics_omit_paths(monkeypatch):
    events = []
    def run(command, **kwargs):
        events.append(command)
        raise PreparationError("Offline worker could not complete")
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(cli, "cleanup", lambda name: events.append(["cleanup", name]))
    with pytest.raises(PreparationError):
        cli.execute("sha256:" + "1" * 64, [])
    assert events[-1][0] == "cleanup"
    assert events[-1][1] == events[0][events[0].index("--name") + 1]


def test_cli_failure_has_no_private_text_paths_or_traceback(tmp_path):
    private = tmp_path / "private-sensitive-name"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/prepare_public_source.py"),
                             str(private), str(tmp_path / "output"), "--signatures", str(private)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "private-sensitive-name" not in result.stderr and "Traceback" not in result.stderr
