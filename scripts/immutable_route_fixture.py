"""Synthetic blob files and explicit mock transport; never a native model."""

import asyncio
import base64

import httpx
from immutable_provider_hook import ImmutableExecutionHook, ManifestSnapshot
from provider_stage_adapters import ReceiptStore
from provider_stage_fixture import CREDENTIAL, NOW, StageFixture
from provider_trust_stage import write
from signed_provider_contract import IdentityChallenge, ResponseChallenge, encode, sha
from signed_provider_fixture import I_NONCE, R_NONCE
from staged_signed_route import COMPLETION_PATH, IDENTITY_PATH, StagedSignedRoute


class NativeBytes(httpx.AsyncByteStream):
    def __init__(self, raw):
        self.raw = raw

    async def __aiter__(self):
        yield self.raw


class RouteFixture:
    def __init__(self, root, mode="good"):
        self.root, self.mode, self.now, self.sent = root, mode, NOW, []
        self.stage = StageFixture(root)
        self.base = self.stage.base
        self.artifacts = root / "invented-blobs"
        self.artifacts.mkdir(mode=0o700)
        self.model = b"GGUF-INVENTED-NOT-A-REAL-MODEL"
        self.config = encode(
            {
                "model_format": "gguf",
                "model_family": "invented",
                "remote_host": "",
                "remote_model": "",
            }
        )
        self.manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": {
                "mediaType": "application/vnd.docker.container.image.v1+json",
                "digest": "sha256:" + sha(self.config),
                "size": len(self.config),
            },
            "layers": [
                {
                    "mediaType": "application/vnd.ollama.image.model",
                    "digest": "sha256:" + sha(self.model),
                    "size": len(self.model),
                }
            ],
        }
        manifest_raw = encode(self.manifest)
        self.base.pin["model_digest_sha256"] = sha(manifest_raw)
        for raw in (manifest_raw, self.config, self.model):
            write(self.artifacts / ("sha256-" + sha(raw)), raw)
        self.reference = "sha256:" + sha(manifest_raw)
        self.stage.rows[0][2].params.update(
            digest=sha(manifest_raw), model_id=self.reference
        )
        self.stage.adapter._model_id = self.reference
        from provider_stage_adapters import EngineIdentityAdapter

        self.identity = EngineIdentityAdapter(
            self.stage.auth, self.stage.manager, self.base.pin, clock=lambda: self.now
        )
        self.snapshot = ManifestSnapshot(self.artifacts, self.base.pin)
        self.receipts = ReceiptStore.create(root / "route-receipts.sqlite3")
        self.hook = ImmutableExecutionHook(
            self.snapshot,
            clock=lambda: self.now,
            transport=httpx.MockTransport(self.native),
        )
        self.route = StagedSignedRoute(
            self.base.key,
            "synthetic-issuer-v2",
            resolve_identity=self.identity,
            hook=self.hook,
            receipts=self.receipts,
            clock=lambda: self.now,
        )

    async def native(self, request):
        self.sent.append(request)
        if self.mode == "cancel":
            raise asyncio.CancelledError()
        if self.mode == "revoked_during":
            self.stage.auth._keys_by_value = {}
        if self.mode == "late_expiry":
            self.now = NOW + 121
        if self.mode == "changed_during":
            (self.artifacts / ("sha256-" + sha(self.model))).write_bytes(
                b"X" * len(self.model)
            )
        body = {
            "model": self.reference,
            "message": {"role": "assistant", "content": "Invented staged answer."},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 40,
            "eval_count": 10,
        }
        if self.mode == "wrong_model":
            body["model"] = self.base.pin["model_id"]
        if self.mode == "clipped":
            body["done_reason"] = "length"
        if self.mode == "missing_usage":
            body.pop("prompt_eval_count")
        raw = b"X" * 8193 if self.mode == "body_overflow" else encode(body)
        status = (
            302 if self.mode == "redirect" else 502 if self.mode == "http502" else 200
        )
        return httpx.Response(
            status,
            headers={
                "Content-Type": "application/json",
                "Location": "https://external.invalid",
            },
            stream=NativeBytes(raw),
        )

    async def post(self, path, value, *, headers=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.route),
            base_url="http://staged.invalid",
        ) as client:
            return await client.post(
                path,
                content=encode(value),
                headers=headers
                or {
                    "Authorization": "Bearer " + CREDENTIAL,
                    "Content-Type": "application/json",
                },
            )

    async def prepare(self, raw=None):
        if self.mode == "mutable_tag":
            self.stage.adapter._model_id = self.base.pin["model_id"]
        if self.mode == "foreign_key":
            self.stage.auth._keys_by_value = {}
        if self.mode == "policy_changed":
            self.stage.auth.settings.openrouter_fallback_enabled = True
        self.raw = raw if raw is not None else self.base.request
        response = await self.post(
            IDENTITY_PATH,
            {
                "model": self.base.pin["model_id"],
                "route_sha256": self.base.pin["route_sha256"],
                "challenge": I_NONCE,
            },
        )
        if response.status_code != 200:
            return response
        self.proof = IdentityChallenge(
            self.base.key.public_key(),
            "synthetic-issuer-v2",
            self.base.pin,
            challenge=I_NONCE,
        ).consume(response.content, now=self.now)
        self.pending = ResponseChallenge(
            self.raw,
            self.proof,
            trusted_key=self.base.key.public_key(),
            issuer_key_id="synthetic-issuer-v2",
            expected_pin=self.base.pin,
            identity_nonce=I_NONCE,
            now=self.now,
            challenge=R_NONCE,
        )
        self.envelope = {
            "request_base64": base64.b64encode(self.raw).decode(),
            "identity_proof": self.proof,
            "expectation": self.pending.expectation(),
        }
        if self.mode == "tamper_request":
            self.envelope["request_base64"] = base64.b64encode(self.raw + b" ").decode()
        if self.mode == "corrupt_blob":
            (self.artifacts / ("sha256-" + sha(self.model))).write_bytes(
                b"X" * len(self.model)
            )
        if self.mode == "remote_manifest":
            self.snapshot.blob = lambda *a, **k: encode(
                {"model_format": "gguf", "remote_host": "https://external.invalid"}
            )
        return response

    async def run(self):
        response = await self.prepare()
        if response.status_code == 200:
            response = await self.post(COMPLETION_PATH, self.envelope)
            if self.mode == "good" and response.status_code == 200:
                self.pending.consume(response.content, now=self.now)
            if self.mode == "replay" and response.status_code == 200:
                response = await self.post(COMPLETION_PATH, self.envelope)
        return response.status_code, len(self.sent)
