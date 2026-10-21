"""Invented originals/history; real transaction and subprocess crash recovery."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, text

from app.config import Settings
from app.db import Store
from app.runtime_key_rotation import STAGE, RotationError, recover, rotate


@pytest.fixture
def vault(tmp_path):
    old, new = Fernet.generate_key(), Fernet.generate_key()
    data = tmp_path / "data"
    (data / "documents").mkdir(parents=True)
    originals = {}
    for char in ["a", "b"]:
        name = char * 32 + ".enc"
        raw = Fernet(old).encrypt_at_time(("SENTETİK: Ödeme yapılmadı. " + char).encode(), 1234567)
        (data / "documents" / name).write_bytes(raw)
        originals[name] = raw
    url = "sqlite:///" + str(tmp_path / "workspace.db")
    engine = create_engine(url)
    plain = json.dumps({"state": "needs_review", "evidence_revision": 3, "quote": "SENTETİK: Kabul edilmedi."}).encode()
    token = Fernet(old).encrypt_at_time(plain, 1234567).decode()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE records (id TEXT PRIMARY KEY,kind TEXT,firm_id TEXT,matter_id TEXT,owner_id TEXT,payload TEXT,revision INTEGER,created_at TEXT)"))
        conn.execute(text("INSERT INTO records VALUES ('record','analysis','firm','matter','owner',:p,3,'2001-01-01')"), {"p": token})
        conn.execute(text("CREATE TABLE audit (id TEXT PRIMARY KEY,action TEXT)"))
        conn.execute(text("INSERT INTO audit VALUES ('history','review_pending')"))
    yield engine, data, old, new, originals, plain, token, url
    engine.dispose()


def payload(engine):
    with engine.connect() as conn:
        row = dict(conn.execute(text("SELECT * FROM records")).mappings().one())
        assert row["id"] == "record" and row["revision"] == 3 and row["created_at"] == "2001-01-01"
        assert conn.execute(text("SELECT action FROM audit")).scalar() == "review_pending"
        return row["payload"].encode()


def test_rotation_preserves_plaintext_ids_history_and_token_timestamps(vault):
    engine, data, old, new, files, plain, _, _ = vault
    result = rotate(engine, data, old, new)
    assert result["state"] == "rotated" and result["old_key_rejected"]
    assert Fernet(new).decrypt(payload(engine)) == plain
    assert Fernet(new).extract_timestamp(payload(engine)) == 1234567
    with pytest.raises(InvalidToken):
        Fernet(old).decrypt(payload(engine))
    for name, original in files.items():
        token = (data / "documents" / name).read_bytes()
        assert Fernet(new).decrypt(token) == Fernet(old).decrypt(original)
        assert Fernet(new).extract_timestamp(token) == 1234567
        with pytest.raises(InvalidToken):
            Fernet(old).decrypt(token)
    assert not (data / STAGE).exists()


@pytest.mark.parametrize("phase", ["staged", "file_swapped", "before_commit"])
def test_failure_before_commit_rolls_back_ciphertext_and_history(vault, phase):
    engine, data, old, new, files, _, token, _ = vault
    def fail(point):
        if point == phase:
            raise OSError("synthetic secret must never appear in a rotation error")
    with pytest.raises(RotationError) as caught:
        rotate(engine, data, old, new, checkpoint=fail)
    assert "synthetic secret" not in str(caught.value)
    assert payload(engine) == token.encode()
    assert {p.name: p.read_bytes() for p in (data / "documents").iterdir()} == files
    assert not (data / STAGE).exists()


def test_postcommit_failure_is_recovered_without_rewriting_review_metadata(vault):
    engine, data, old, new, _, plain, _, _ = vault
    def fail(phase):
        if phase == "after_commit":
            raise OSError("synthetic failure")
    with pytest.raises(RotationError):
        rotate(engine, data, old, new, checkpoint=fail)
    assert (data / STAGE / "journal.fernet").is_file()
    assert recover(engine, data, old, new)["state"] == "rotated"
    assert Fernet(new).decrypt(payload(engine)) == plain


@pytest.mark.parametrize("phase,state", [("staged", "rolled_back"), ("file_swapped", "rolled_back"), ("after_commit", "rotated")])
def test_abrupt_process_exit_recovers_exact_committed_state(vault, tmp_path, phase, state):
    engine, data, old, new, files, plain, token, url = vault
    for name, value in [("old", old), ("new", new)]:
        p = tmp_path / name
        p.write_bytes(value)
        p.chmod(0o600)
    code = """import os,sys
from sqlalchemy import create_engine
from app.runtime_key_rotation import rotate
from app.runtime_secrets import read_secret_file
rotate(create_engine(sys.argv[1]),sys.argv[2],read_secret_file(sys.argv[3]).encode(),read_secret_file(sys.argv[4]).encode(),checkpoint=lambda phase:os._exit(71) if phase==sys.argv[5] else None)
"""
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "LANG": "C.UTF-8"}
    proc = subprocess.run([sys.executable, "-c", code, url, str(data), str(tmp_path / "old"), str(tmp_path / "new"), phase],
                          env=env, capture_output=True, timeout=20)
    assert proc.returncode == 71
    assert recover(engine, data, old, new)["state"] == state
    assert not (data / STAGE).exists()
    if state == "rolled_back":
        assert payload(engine) == token.encode()
        assert {p.name: p.read_bytes() for p in (data / "documents").iterdir()} == files
    else:
        assert Fernet(new).decrypt(payload(engine)) == plain


def test_populated_ciphertext_dependent_ledger_refuses_before_mutation(vault):
    engine, data, old, new, files, _, token, _ = vault
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE source_review_heads (id TEXT,payload TEXT)"))
        conn.execute(text("INSERT INTO source_review_heads VALUES ('head','synthetic')"))
    with pytest.raises(RotationError):
        rotate(engine, data, old, new)
    assert payload(engine) == token.encode() and not (data / STAGE).exists()
    assert {p.name: p.read_bytes() for p in (data / "documents").iterdir()} == files


def test_incomplete_journal_blocks_application_startup(vault, tmp_path):
    _, data, _, new, _, _, _, _ = vault
    (data / STAGE).mkdir()
    with pytest.raises(ValueError, match="maintenance"):
        Store(Settings(_env_file=None, demo_mode=True, data_dir=data, encryption_key=new.decode(),
                       database_url="sqlite:///" + str(tmp_path / "unused.db")))
    assert not (tmp_path / "unused.db").exists()


def test_invalid_original_leaves_active_data_untouched_and_cleans_own_stage(vault):
    engine, data, old, new, _, _, token, _ = vault
    path = data / "documents" / ("a" * 32 + ".enc")
    path.write_bytes(b"synthetic damaged ciphertext")
    with pytest.raises(RotationError):
        rotate(engine, data, old, new)
    assert payload(engine) == token.encode() and path.read_bytes() == b"synthetic damaged ciphertext"
    assert not (data / STAGE).exists()


@pytest.mark.parametrize("tamper", ["journal", "original", "revision", "key"])
def test_recovery_refuses_tampering_without_overwriting_unknown_state(vault, tamper):
    engine, data, old, new, _, _, _, _ = vault
    def fail(phase):
        if phase == "after_commit":
            raise OSError("synthetic failure")
    with pytest.raises(RotationError):
        rotate(engine, data, old, new, checkpoint=fail)
    if tamper == "journal":
        (data / STAGE / "journal.fernet").write_bytes(b"synthetic corrupt journal")
    elif tamper == "original":
        (data / "documents" / ("a" * 32 + ".enc")).write_bytes(b"synthetic unknown original")
    elif tamper == "revision":
        with engine.begin() as conn:
            conn.execute(text("UPDATE records SET revision=4"))
    else:
        new = Fernet.generate_key()
    before_files = {p.name: p.read_bytes() for p in (data / "documents").iterdir()}
    with engine.connect() as conn:
        before_rows = list(conn.execute(text("SELECT * FROM records")))
    with pytest.raises(RotationError):
        recover(engine, data, old, new)
    assert {p.name: p.read_bytes() for p in (data / "documents").iterdir()} == before_files
    with engine.connect() as conn:
        assert list(conn.execute(text("SELECT * FROM records"))) == before_rows
    assert (data / STAGE).exists()


def test_same_key_is_not_a_rotation_and_never_stages(vault):
    engine, data, old, _, _, _, _, _ = vault
    with pytest.raises(RotationError):
        rotate(engine, data, old, old)
    assert not (data / STAGE).exists()
