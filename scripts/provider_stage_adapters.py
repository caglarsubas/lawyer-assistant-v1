"""Staged adapters for the inspected engine auth/manager interfaces. No inference."""

import os
import re
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from provider_trust_stage import directory, read
from signed_provider_contract import (
    EXPECT_FIELDS,
    ExecutionReceipt,
    completion,
    decode,
    encode,
    label,
    nonce,
    pin,
    request,
    sha,
    stamp,
)


def authenticated_principal(auth, credential, *, now):
    """Read the loaded auth snapshot without cached Request identity or token logs.

    The current engine's require_identity logs fragments for rejected keys. This
    staged adapter never invokes that logging path, loads a file or reloads keys.
    """
    stamp(now)
    if (
        not isinstance(credential, str)
        or not 8 <= len(credential) <= 4096
        or any(not 33 <= ord(c) <= 126 for c in credential)
    ):
        raise ValueError("Current authenticated principal unavailable")
    try:
        if auth.settings.auth_enabled is not True or auth._keys_loaded is not True:
            raise ValueError()
        records = auth._keys_by_value
        if not isinstance(records, dict) or len(records) > 10000:
            raise ValueError()
        record = records.get(credential)
        if record is None or not record.active_at(datetime.fromtimestamp(now, timezone.utc)):
            raise ValueError()
        return {
            "tenant_id": label(record.tenant),
            "organization_id": label(record.org_id),
            "key_id": label(record.key_id),
        }
    except Exception:
        raise ValueError("Current authenticated principal unavailable") from None


def loaded_runtime(manager, expected_pin, principal):
    """Never calls manager.get/resolve, registry refresh, load, inference or HTTP.

    Current tag-based Ollama execution is deliberately rejected. A future pinned
    backend must actually dispatch a reviewed immutable digest reference.
    """
    expected = pin(expected_pin)
    if any(expected[k] != principal[k] for k in ("tenant_id", "organization_id", "key_id")):
        raise ValueError("Principal differs from registered runtime")
    try:
        rows = manager.iter_loaded()
        if not isinstance(rows, list) or len(rows) > 128:
            raise ValueError()
        selected = [(a, d) for name, a, d in rows if name == expected["model_id"]]
        if len(selected) != 1:
            raise ValueError()
        adapter, descriptor = selected[0]
        if (
            adapter.backend_name != "ollama_http"
            or descriptor.format != "ollama_http"
            or expected["backend"] != "ollama_http"
            or expected["format"] != "ollama_http"
            or not adapter.is_loaded
            or descriptor.endpoint != "http://127.0.0.1:11434"
            or adapter._endpoint != descriptor.endpoint
            or type(descriptor.size_bytes) is not int
            or descriptor.size_bytes <= 0
            or type(adapter._num_ctx) is not int
            or adapter._num_ctx != expected["model_context_units"]
        ):
            raise ValueError()
        digest = descriptor.params.get("digest")
        digest = digest[7:] if isinstance(digest, str) and digest.startswith("sha256:") else digest
        if digest != expected["model_digest_sha256"]:
            raise ValueError()
        reference = "sha256:" + digest
        if descriptor.params.get("model_id") != reference or adapter._model_id != reference:
            raise ValueError("immutable_reference_required")
    except Exception as error:
        code = (
            "immutable_reference_required"
            if type(error) is ValueError and str(error) == "immutable_reference_required"
            else "loaded_runtime_unqualified"
        )
        raise ValueError(code) from None
    return expected


class EngineIdentityAdapter:
    def __init__(self, auth, manager, registered_pin, *, clock):
        self.auth, self.manager, self.registered = auth, manager, encode(pin(registered_pin))
        self.clock = clock

    def __call__(self, credential, model_id, route_sha256):
        expected = decode(self.registered)
        if model_id != expected["model_id"] or route_sha256 != expected["route_sha256"]:
            raise ValueError("Requested model or trusted route differs")
        principal = authenticated_principal(self.auth, credential, now=self.clock())
        settings = self.auth.settings
        if (
            getattr(settings, "openrouter_fallback_enabled", None) is not False
            or getattr(settings, "upstream_retry_enabled", None) is not False
            or getattr(settings, "model_substitution_groups", None) != ""
        ):
            raise ValueError("runtime_policy_unqualified")
        return loaded_runtime(self.manager, expected, principal)


class ReceiptStore:
    """Durable one-use metadata receipts, not execution or campaign authority.

    Trusted provider hooks alone may call begin/complete. The store contains no
    credentials, original prompts or response bodies. It is still confidential.
    """

    @classmethod
    def create(cls, path):
        path = Path(path)
        directory(path.parent)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                "CREATE TABLE receipts(handle TEXT PRIMARY KEY, nonce TEXT UNIQUE NOT NULL, record TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('prepared','finalizing','completed','consumed')))"
            )
        return cls(path)

    def __init__(self, path):
        self.path = Path(path)
        # Inspect permissions/ownership without interpreting database bytes as JSON.
        read(self.path, 16 * 1024 * 1024)
        with self.connect() as db:
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Staged receipt database failed integrity check")
            if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() != [("receipts",)]:
                raise ValueError("Unexpected staged receipt schema")

    @contextmanager
    def connect(self):
        read(self.path, 16 * 1024 * 1024)
        connection = sqlite3.connect(
            self.path.resolve().as_uri() + "?mode=rw", uri=True, timeout=2, isolation_level=None
        )
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin(self, runtime_pin, request_bytes, expectation, *, now):
        expected = pin(runtime_pin)
        stamp(now)
        req = request(request_bytes, expected)
        if (
            not isinstance(expectation, dict)
            or set(expectation) != EXPECT_FIELDS
            or expectation["kind"] != "completion"
            or expectation["contract"] != "lawyer-provider-binding-v2"
            or expectation["request_sha256"] != sha(request_bytes)
            or expectation["pin_sha256"] != sha(encode(expected))
            or not re.fullmatch("[0-9a-f]{64}", expectation["identity_sha256"])
            or stamp(expectation["issued_at"]) > now
            or not now < stamp(expectation["expires_at"]) <= now + 120
        ):
            raise ValueError("Receipt expectation rejected")
        nonce(expectation["nonce"])
        label(expectation["issuer_key_id"])
        handle = secrets.token_hex(32)
        record = {
            "runtime_pin": expected,
            "request_sha256": sha(request_bytes),
            "response_nonce": expectation["nonce"],
            "identity_sha256": expectation["identity_sha256"],
            "started_at": now,
            "expires_at": expectation["expires_at"],
            "maximum": req["max_completion_tokens"],
        }
        with self.connect() as db:
            db.execute(
                "INSERT INTO receipts VALUES(?,?,?,'prepared')",
                (handle, expectation["nonce"], encode(record).decode()),
            )
        return handle

    def complete(self, handle, response_bytes, current_pin, executed_reference, *, attempts, now):
        stamp(now)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT record,status FROM receipts WHERE handle=?", (handle,)).fetchone()
            if not row or row[1] != "prepared":
                raise ValueError("Receipt is not prepared")
            db.execute("UPDATE receipts SET status='finalizing' WHERE handle=?", (handle,))
            db.commit()
        # Invalid or interrupted finalization is permanently non-consumable.
        value = decode(row[0].encode())
        expected = pin(current_pin)
        if (
            attempts != 1
            or type(attempts) is not int
            or expected != value["runtime_pin"]
            or executed_reference != "sha256:" + expected["model_digest_sha256"]
            or not value["started_at"] <= now < value["expires_at"]
        ):
            raise ValueError("Execution is not qualified for a receipt")
        completion(response_bytes, expected, value["maximum"])
        value.update(
            response_sha256=sha(response_bytes), completed_at=now, local_execution=True, substituted=False
        )
        with self.connect() as db:
            changed = db.execute(
                "UPDATE receipts SET record=?,status='completed' WHERE handle=? AND status='finalizing'",
                (encode(value).decode(), handle),
            ).rowcount
            if changed != 1:
                raise ValueError("Receipt finalization state changed")

    def consume(self, handle, *, now):
        stamp(now)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT record,status FROM receipts WHERE handle=?", (handle,)).fetchone()
            if not row or row[1] != "completed":
                raise ValueError("Completed one-use receipt unavailable")
            # Commit consumption before validating/returning; failed reads burn it.
            db.execute("UPDATE receipts SET status='consumed' WHERE handle=?", (handle,))
            db.commit()
        value = decode(row[0].encode())
        if now >= value["expires_at"]:
            raise ValueError("Completed receipt expired")
        return ExecutionReceipt(**{k: value[k] for k in ExecutionReceipt.__dataclass_fields__})
