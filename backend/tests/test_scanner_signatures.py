"""Package admission rejects stale, forged, partial and unexpected signature inputs."""

import importlib.util
import subprocess
import time
from pathlib import Path

import pytest


@pytest.fixture
def control(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "backend/app"))
    spec = importlib.util.spec_from_file_location("scanner_control", root / "deploy/scanner/control.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("LA_SCANNER_MAX_SIGNATURE_AGE_DAYS", "7")
    return module


def package(directory, *, days=0, count=10):
    for name in ("main.cvd", "daily.cvd", "bytecode.cvd"):
        header = f"ClamAV-VDB:fixture:28142:{count}:90:checksum:signature:builder:{int(time.time() - days * 86400)}"
        (directory / name).write_bytes(header.encode().ljust(512, b" ") + b"synthetic CVD payload")


def admitted(monkeypatch, control):
    calls = []

    def verification(command, **kwargs):
        assert command[:2] == ["sigtool", "--info"] and kwargs["timeout"] == 120
        calls.append(command[-1])
        return subprocess.CompletedProcess(command, 0, b"Verification OK.\n", b"")

    monkeypatch.setattr(control.subprocess, "run", verification)
    return calls


def test_each_database_requires_cryptographic_verification(control, monkeypatch, tmp_path):
    package(tmp_path)
    calls = admitted(monkeypatch, control)
    manifest = control.verify(tmp_path)
    assert len(calls) == 3 and len(manifest["databases"]) == 3
    assert all(len(item["sha256"]) == 64 and item["signatures"] == 10 for item in manifest["databases"])


@pytest.mark.parametrize("returncode,output", [(1, b"Verification OK."), (0, b"No signature"), (2, b"")])
def test_bad_signature_never_publishes(control, monkeypatch, tmp_path, returncode, output):
    package(tmp_path)
    monkeypatch.setattr(control.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a, returncode, output, b""))
    with pytest.raises(ValueError, match="cryptographic"):
        control.verify(tmp_path)


@pytest.mark.parametrize("days", [8, -1])
def test_stale_and_future_daily_databases_rejected(control, monkeypatch, tmp_path, days):
    package(tmp_path, days=days)
    admitted(monkeypatch, control)
    with pytest.raises(ValueError, match="age policy|future"):
        control.verify(tmp_path)


def test_old_main_database_is_permitted_when_daily_is_current(control, monkeypatch, tmp_path):
    package(tmp_path)
    main = tmp_path / "main.cvd"
    raw = main.read_bytes().replace(str(int(time.time())).encode(), str(int(time.time()) - 300 * 86400).encode())
    main.write_bytes(raw)
    admitted(monkeypatch, control)
    assert len(control.verify(tmp_path)["databases"]) == 3


def test_zero_signature_count_is_rejected(control, monkeypatch, tmp_path):
    package(tmp_path, count=0)
    admitted(monkeypatch, control)
    with pytest.raises(ValueError, match="count"):
        control.verify(tmp_path)


@pytest.mark.parametrize("change", ["extra", "symlink", "missing", "partial"])
def test_unapproved_or_incomplete_package_rejected(control, monkeypatch, tmp_path, change):
    package(tmp_path)
    admitted(monkeypatch, control)
    if change == "extra":
        (tmp_path / "custom.hdb").write_text("unapproved")
    elif change == "symlink":
        (tmp_path / "daily.cvd").unlink()
        (tmp_path / "daily.cvd").symlink_to(tmp_path / "main.cvd")
    elif change == "missing":
        (tmp_path / "daily.cvd").unlink()
    elif change == "partial":
        (tmp_path / "daily.cvd").write_bytes(b"bad")
    with pytest.raises(ValueError):
        control.verify(tmp_path)


@pytest.mark.parametrize("days", ["0", "15", "unbounded"])
def test_administrator_age_policy_is_bounded(control, monkeypatch, days):
    monkeypatch.setenv("LA_SCANNER_MAX_SIGNATURE_AGE_DAYS", days)
    with pytest.raises(ValueError):
        control.age_limit()
