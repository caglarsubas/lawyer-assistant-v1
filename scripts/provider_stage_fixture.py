"""Provider's public auth interface with synthetic records and loaded adapters."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy/fixtures"))
from provider_engine_contract import _KeyRecord  # noqa: E402
from provider_stage_adapters import EngineIdentityAdapter, ReceiptStore  # noqa: E402
from signed_provider_contract import ResponseChallenge  # noqa: E402
from signed_provider_fixture import CREDENTIAL, I_NONCE, NOW, R_NONCE, Fixture  # noqa: E402


class StageFixture:
    def __init__(self, root, mode="good"):
        self.root, self.mode, self.base = root, mode, Fixture()
        p = self.base.pin
        expiry = datetime.fromtimestamp(NOW - 1, timezone.utc) if mode == "key_expired" else None
        record = _KeyRecord(
            CREDENTIAL,
            "foreign" if mode == "foreign_principal" else p["tenant_id"],
            p["organization_id"],
            None if mode == "missing_explicit_key_id" else p["key_id"],
            expires_at=expiry,
        )
        self.auth = SimpleNamespace(
            settings=SimpleNamespace(
                auth_enabled=mode != "auth_disabled",
                openrouter_fallback_enabled=False,
                upstream_retry_enabled=False,
                model_substitution_groups="",
            ),
            _keys_loaded=True,
            _keys_by_value={CREDENTIAL: record},
        )
        ref = p["model_id"] if mode == "mutable_tag" else "sha256:" + p["model_digest_sha256"]
        endpoint = "https://external.invalid" if mode == "external_endpoint" else "http://127.0.0.1:11434"
        desc = SimpleNamespace(
            format="ollama_http",
            endpoint=endpoint,
            size_bytes=1024,
            params={
                "digest": "0" * 64 if mode == "digest_changed" else p["model_digest_sha256"],
                "model_id": ref,
            },
        )
        self.adapter = SimpleNamespace(
            backend_name="ollama_http",
            is_loaded=True,
            _endpoint=endpoint,
            _model_id=ref,
            _num_ctx=p["model_context_units"],
        )
        self.rows = [(p["model_id"], self.adapter, desc)]
        self.manager = SimpleNamespace(iter_loaded=lambda: list(self.rows))
        self.identity = EngineIdentityAdapter(self.auth, self.manager, p, clock=lambda: NOW)

    def prepare(self):
        p = self.base.pin
        self.resolved = self.identity(CREDENTIAL, p["model_id"], p["route_sha256"])
        self.base.issuer.resolve_identity = self.identity
        self.proof = self.base.identity()
        self.pending = ResponseChallenge(
            self.base.request,
            self.proof,
            trusted_key=self.base.key.public_key(),
            issuer_key_id="synthetic-issuer-v2",
            expected_pin=p,
            identity_nonce=I_NONCE,
            now=NOW,
            challenge=R_NONCE,
        )
        self.store = ReceiptStore.create(self.root / "receipts.sqlite3")
        self.handle = self.store.begin(self.resolved, self.base.request, self.pending.expectation(), now=NOW)
        return self.handle

    def finish(self):
        if self.mode != "not_completed":
            reference = "sha256:" + (
                "0" * 64 if self.mode == "wrong_executed_ref" else self.resolved["model_digest_sha256"]
            )
            self.store.complete(
                self.handle,
                self.base.response,
                self.resolved,
                reference,
                attempts=2 if self.mode == "retry_attempt" else 1,
                now=NOW + 120 if self.mode == "expired" else NOW + 1,
            )
        return self.store.consume(self.handle, now=NOW + 1)
