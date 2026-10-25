"""Fresh synthetic portability cases; imports no app, engine or private fixtures."""

import base64
import hashlib
import importlib
import json
import os
import random
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

NOW = 1800000300
GENERATION = "a" * 32
CREDENTIAL = "SYNTHETIC-PORTABLE-ONLY"
ISSUER = "fixture-portable-issuer"
CASES = [
    ("A01_import", "verified"), ("A02_module", "rejected"), ("A03_manifest", "rejected"),
    ("A04_extra", "rejected"), ("A05_symlink", "rejected"), ("A06_hardlink", "rejected"),
    ("A07_missing", "rejected"), ("A08_app_import", "rejected"), ("A09_wrong_approval", "rejected"),
    ("A10_writable", "rejected"), ("A11_ready", "ready_for_disposable_mock_validation"),
    ("A12_candidate_only", "waiting"), ("A13_no_confirmation_approval", "waiting"),
    ("A14_fingerprint", "blocked"), ("A15_issuer", "blocked"), ("A16_reviewer", "blocked"),
    ("A17_self_review", "blocked"), ("A18_expired", "blocked"), ("A19_revoked", "blocked"),
    ("A20_candidate", "blocked"), ("A21_confirmation_hash", "blocked"), ("A22_binding", "blocked"),
    ("A23_unsealed", "blocked"), ("A24_journal", "blocked"), ("A25_revoked_during_check", "blocked"),
    ("A26_no_privileged_helpers", "ready_for_disposable_mock_validation"),
    ("A27_HTTP", "verified"), ("A28_receipt_rollback", "rejected"), ("A29_real_transport", "rejected"),
]
POLICY = {"schema": "portable-controller-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "attempts_per_case": 1, "model_verification_seconds": 20, "small_model_bytes": 65561,
          "package_modules": 14, "real_provider_requests": 0, "native_inference_calls": 0,
          "real_trust_confirmed": False, "runtime_installation": False, "production_activation": False}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def modules():
    return SimpleNamespace(**{n: importlib.import_module("lawyer_provider_stage." + n) for n in
                             ("manifest", "readiness", "controller", "control", "sealed_volume", "artifact_store", "trust", "contract", "adapters")})


def write(path, raw, mode=0o600):
    with Path(path).open("xb") as stream:
        stream.write(raw)
    Path(path).chmod(mode)


class SyntheticBytes(httpx.AsyncByteStream):
    def __init__(self, raw):
        self.raw = raw

    async def __aiter__(self):
        yield self.raw


def prepare(models, stage, m):
    """Only a new disposable volume; no acquired weights, documents or runtime data."""
    model = models / "model"
    store = model / ("snapshot-" + GENERATION) / "store"
    store.mkdir(parents=True, mode=0o700)
    for name in ("blobs", "manifests", "manifests-v2"):
        (store / name).mkdir(mode=0o700)
    raw = b"GGUF\x03\0\0\0" + b"\0" * 16 + random.Random(20261030).randbytes(65561 - 24)
    def descriptor(media, body):
        return {"mediaType": media, "digest": "sha256:" + sha(body), "size": len(body)}
    template = b"Invented portable fixture only."
    layers = [descriptor(m.artifact_store.MODEL, raw), descriptor("application/vnd.ollama.image.template", template)]
    config = encode({"model_format": "gguf", "model_family": "llama", "model_families": ["llama"],
                     "rootfs": {"type": "layers", "diff_ids": [v["digest"] for v in layers]}})
    cd = descriptor(m.artifact_store.CONFIG, config)
    manifest = encode({"schemaVersion": 2, "mediaType": m.artifact_store.MANIFEST, "config": cd, "layers": layers})
    artifacts = []
    for body in (manifest, config, raw, template):
        digest = "sha256:" + sha(body)
        write(store / "blobs" / digest.replace(":", "-"), body)
        artifacts.append({"digest": digest, "bytes": len(body)})
    projection = {"manifest": "sha256:" + sha(manifest), "artifacts": artifacts}
    index = {"format": m.sealed_volume.FORMAT, **projection, "content_sha256": sha(m.artifact_store.canonical(projection)),
             "total_bytes": sum(v["bytes"] for v in artifacts)}
    write(model / "index.json", encode(index))
    for name, _ in CASES[1:8]:
        target = models / name
        shutil.copytree(stage, target)
        file = target / "lawyer_provider_stage/__init__.py"
        if name == "A02_module":
            file.write_bytes(file.read_bytes() + b"\n# changed\n")
        elif name == "A03_manifest":
            path = target / "guarded-stage-manifest.json"
            path.write_bytes(path.read_bytes() + b" ")
        elif name == "A04_extra":
            write(target / ".env", b"INVENTED=fixture\n", 0o644)
        elif name == "A05_symlink":
            file.unlink()
            file.symlink_to("/absent-fixture")
        elif name == "A06_hardlink":
            os.link(file, models / "fixture-hardlink")
        elif name == "A07_missing":
            file.unlink()
        elif name == "A08_app_import":
            file.write_bytes(b"import app\n")
            path = target / "guarded-stage-manifest.json"
            value = json.loads(path.read_bytes())
            value["package_sha256"]["__init__.py"] = sha(file.read_bytes())
            path.write_bytes(encode(value))
    return index


class Fixture:
    def __init__(self, name, models, work, anchors, m):
        self.m, self.name, self.now = m, name, NOW
        self.work, self.anchors = work / name, anchors / name
        self.work.mkdir(mode=0o700)
        self.anchors.mkdir(mode=0o700)
        self.model = models / "model"
        self.index = json.loads((self.model / "index.json").read_bytes())
        self.journal = m.control.Journal.create(self.work / "control.sqlite", self.anchors / "anchor.log")
        self.operation = sha(name.encode())[:32]
        self.volume_binding = sha(b"disposable-exact-mount")
        proof = m.artifact_store.supervised_verify(self.model / ("snapshot-" + GENERATION) / "store", self.index["manifest"], strategy="windowed-pinned")
        self.record = {"operation_id": self.operation, "generation_id": GENERATION,
                       "bundle_index_sha256": sha(encode(self.index)), "content_sha256": self.index["content_sha256"],
                       "manifest_digest": self.index["manifest"], "volume_binding_sha256": self.volume_binding,
                       "purpose": "import", "parent_operation": None, "production_activation": False}
        sealed = name != "A23_unsealed"
        with self.journal.connect() as db:
            db.execute("INSERT INTO operations VALUES(?,?,?,?,?)", (self.operation, GENERATION, encode(self.record).decode(),
                       "sealed" if sealed else "prepared", encode(proof).decode() if sealed else None))
            for event in (["copying", "prepared", "sealed"] if sealed else ["copying", "prepared"]):
                db.execute("INSERT INTO events(operation,event) VALUES(?,?)", (self.operation, event))
        self.pin = {"model_id": "fixture-portable-model", "model_digest_sha256": self.index["manifest"][7:],
                    "backend": "ollama_http", "format": "ollama_http", "model_context_units": 8192,
                    "application_context_units": 4096, "tenant_id": "fixture-tenant", "organization_id": "fixture-org",
                    "key_id": "fixture-key", "transport_mode": "native_private", "route_sha256": sha(b"fixture-route"),
                    "cloud_fallback_disabled": True}
        self.binding = m.controller.Binding(self.journal.journal_id, self.operation, sha(encode(self.record)), self.volume_binding, encode(self.pin))
        self.key = Ed25519PrivateKey.generate()
        public = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.fingerprint = sha(public)
        self.trust = self.work / "trust"
        self.trust.mkdir(mode=0o700)
        candidate = {"version": 1, "issuer_key_id": ISSUER, "public_key_base64": base64.b64encode(public).decode(),
                     "fingerprint": self.fingerprint, "created_at": NOW - 100, "production_activation": False}
        write(self.trust / "candidate.json", encode(candidate))
        decision = {"issuer_key_id": ISSUER, "fingerprint": self.fingerprint, "reviewer": "fixture-reviewer",
                    "confirmed_at": NOW - 50, "expires_at": NOW - 50 + 86400, "production_activation": False}
        write(self.trust / "key-confirmation.json", encode(decision))
        self.kw = dict(expected_fingerprint=self.fingerprint, expected_issuer_key_id=ISSUER, expected_reviewer="fixture-reviewer",
                       provisioned_by="fixture-provisioner", approved_confirmation_sha256=sha(encode(decision)), now=NOW)
        self.sent = []

    def change(self):
        name = self.name
        if name == "A12_candidate_only":
            (self.trust / "key-confirmation.json").unlink()
        elif name == "A13_no_confirmation_approval":
            self.kw["approved_confirmation_sha256"] = None
        elif name == "A14_fingerprint":
            self.kw["expected_fingerprint"] = "0" * 64
        elif name == "A15_issuer":
            self.kw["expected_issuer_key_id"] = "fixture-other"
        elif name == "A16_reviewer":
            self.kw["expected_reviewer"] = "fixture-other-reviewer"
        elif name == "A17_self_review":
            self.kw["provisioned_by"] = self.kw["expected_reviewer"]
        elif name == "A18_expired":
            self.kw["now"] = NOW + 86400
        elif name == "A19_revoked":
            write(self.trust / "revoked.json", b"malformed")
        elif name == "A20_candidate":
            (self.trust / "candidate.json").write_bytes(b"malformed")
        elif name == "A21_confirmation_hash":
            self.kw["approved_confirmation_sha256"] = "0" * 64
        elif name == "A22_binding":
            self.binding = replace(self.binding, record_sha256="0" * 64)
        elif name == "A24_journal":
            self.binding = replace(self.binding, journal_id="0" * 32)

    def inventory(self):
        return {str(p): sha(p.read_bytes()) for root in (self.work, self.anchors) for p in sorted(root.rglob("*")) if p.is_file()}

    async def backend(self, request):
        self.sent.append(request)
        value = {"model": self.index["manifest"], "message": {"role": "assistant", "content": "Invented portable answer."},
                 "done": True, "done_reason": "stop", "prompt_eval_count": 40, "eval_count": 10}
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=SyntheticBytes(encode(value)))

    def app(self, transport=None):
        p, m = self.pin, self.m
        reference = self.index["manifest"]
        settings = SimpleNamespace(auth_enabled=True, openrouter_fallback_enabled=False, upstream_retry_enabled=False, model_substitution_groups="")
        key = SimpleNamespace(tenant=p["tenant_id"], org_id=p["organization_id"], key_id=p["key_id"], active_at=lambda _: True)
        auth = SimpleNamespace(settings=settings, _keys_loaded=True, _keys_by_value={CREDENTIAL: key})
        descriptor = SimpleNamespace(format="ollama_http", endpoint="http://127.0.0.1:11434", size_bytes=65561,
                                     params={"digest": p["model_digest_sha256"], "model_id": reference})
        adapter = SimpleNamespace(backend_name="ollama_http", is_loaded=True, _endpoint=descriptor.endpoint, _model_id=reference, _num_ctx=p["model_context_units"])
        manager = SimpleNamespace(iter_loaded=lambda: [(p["model_id"], adapter, descriptor)])
        identity = m.adapters.EngineIdentityAdapter(auth, manager, p, clock=lambda: NOW)
        if not hasattr(self, "receipts"):
            self.receipts = m.adapters.ReceiptStore.create(self.work / "receipts.sqlite")
            self.empty_receipts = self.receipts.path.read_bytes()
        return m.controller.build(self.model, self.journal, self.binding, key=self.key, issuer_key_id=ISSUER,
                                  receipts=self.receipts, resolve_identity=identity, clock=lambda: NOW,
                                  transport=httpx.MockTransport(self.backend) if transport is None else transport)

    async def protocol(self, post, rebuild):
        c = self.m.contract
        challenge = "1" * 32
        response = await post("/staged/v2/identity", {"model": self.pin["model_id"], "route_sha256": self.pin["route_sha256"], "challenge": challenge})
        proof = c.IdentityChallenge(self.key.public_key(), ISSUER, self.pin, challenge=challenge).consume(response.content, now=NOW)
        raw = encode({"model": self.pin["model_id"], "messages": [{"role": "user", "content": "Invented portable input."}], "stream": False, "max_completion_tokens": 100}) + b" \n"
        pending = c.ResponseChallenge(raw, proof, trusted_key=self.key.public_key(), issuer_key_id=ISSUER, expected_pin=self.pin,
                                      identity_nonce=challenge, now=NOW, challenge="2" * 32)
        envelope = {"request_base64": base64.b64encode(raw).decode(), "identity_proof": proof, "expectation": pending.expectation()}
        response = await post("/staged/v2/completions", envelope)
        pending.consume(response.content, now=NOW)
        frame = {"public_key_base64": base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode(),
                 "pin": self.pin, "request_base64": base64.b64encode(raw).decode(), "identity_proof": proof, "identity_nonce": challenge,
                 "response_nonce": "2" * 32, "now": NOW, "response_envelope_base64": base64.b64encode(response.content).decode()}
        status = "verified"
        if self.name == "A28_receipt_rollback":
            self.receipts.path.write_bytes(self.empty_receipts)
            rebuild()
            repeated = await post("/staged/v2/completions", envelope)
            status = "rejected" if repeated.status_code == 400 else "invalid"
        counts = self.journal.recover(self.operation)["nonce_counts"]
        if counts != {"consumed": 1} or len(self.sent) != 1 or any(CREDENTIAL.encode() in r.content or "authorization" in r.headers for r in self.sent):
            raise ValueError("Disposable protocol invariants failed")
        return status, frame
