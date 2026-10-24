"""Invented model/control layouts and loopback protocol scenarios only."""

import asyncio
import base64
import shutil

import guarded_controller_route as guarded
import httpx
import sealed_control_journal as control
import sealed_volume as volume
from cryptography.hazmat.primitives import serialization
from provider_stage_adapters import EngineIdentityAdapter, ReceiptStore
from provider_stage_fixture import CREDENTIAL, NOW, StageFixture
from sealed_handoff_qualification import make_store, operation
from signed_provider_contract import IdentityChallenge, ResponseChallenge, decode, encode, sha
from staged_signed_route import COMPLETION_PATH, IDENTITY_PATH

CASES = [
    ("G01_valid", 200, 1), ("G02_replay", 400, 1), ("G03_revoked_parent", 400, 0),
    ("G04_before_admission", 400, 0), ("G05_after_admission", 400, 0),
    ("G06_during_backend", 400, 1), ("G07_before_complete", 400, 1),
    ("G08_before_consume", 400, 1), ("G09_before_release", 400, 1),
    ("G10_foreign_auth", 400, 0), ("G11_auth_before_admission", 400, 0),
    ("G12_auth_during_backend", 400, 1), ("G13_wrong_record", "setup_rejected", 0),
    ("G14_wrong_journal", "setup_rejected", 0), ("G15_unsealed", "setup_rejected", 0),
    ("G16_writable", "setup_rejected", 0), ("G17_context_override", 400, 0),
    ("G18_backend_502", 400, 1), ("G19_context_budget", 400, 0),
    ("G20_commit_gap", 400, 0), ("G21_lost_admission", 400, 0),
    ("G22_receipt_rollback", 400, 1), ("G23_direct_hook", "direct_rejected", 0),
    ("G24_concurrent", 503, 1), ("G25_clipped", 400, 1),
    ("G26_changed_pin", 400, 1), ("G27_legacy_journal", "setup_rejected", 0),
    ("G28_expired", 400, 0), ("G29_exact_wire", 200, 1),
]
POLICY = {"schema": "guarded-route-qualification-v1",
          "cases": [{"id": n, "status": s, "simulated_backend_sends": c} for n, s, c in CASES],
          "single_native_attempt": True, "actual_native_inference": False,
          "backend_transport": "explicit_httpx_mock_only", "real_provider_requests": 0,
          "real_trust_confirmed": False, "runtime_installation": False, "production_activation": False,
          "model_verification_seconds": 20, "loopback_HTTP_only": True}
ISSUER = "synthetic-issuer-v2"


def layout(root):
    for name, _, _ in CASES:
        case = root / name
        case.mkdir(mode=0o700)
        for role in ("parent", "child"):
            snapshot = case / ("snapshot-" + operation(name + "-" + role))
            snapshot.mkdir(mode=0o700)
            index = make_store(snapshot / "store")
        volume.write_new(case / "index.json", encode(index))


class NativeBytes(httpx.AsyncByteStream):
    def __init__(self, raw):
        self.raw = raw

    async def __aiter__(self):
        yield self.raw


class Fixture:
    def __init__(self, name, models, work, anchors, *, binding_prefix, proof):
        self.name, self.now, self.sent, self.armed = name, NOW, [], False
        self.work, self.anchor_root = work / name, anchors / name
        self.work.mkdir(mode=0o700)
        self.anchor_root.mkdir(mode=0o700)
        self.root = models / name
        self.index = decode(volume.small(self.root / "index.json"))
        self.journal = control.Journal.create(self.work / "control.sqlite", self.anchor_root / "anchor.log")
        self.parent, self.child = operation(name + "-parent-op"), operation(name + "-child-op")
        self.volume_binding = sha((binding_prefix + "/" + name).encode())
        with self.journal.connect() as db:
            for role, op, parent in (("parent", self.parent, None), ("child", self.child, self.parent)):
                record = {"operation_id": op, "generation_id": operation(name + "-" + role),
                          "bundle_index_sha256": sha(encode(self.index)), "content_sha256": self.index["content_sha256"],
                          "manifest_digest": self.index["manifest"], "volume_binding_sha256": self.volume_binding,
                          "purpose": "restore" if parent else "import", "parent_operation": parent, "production_activation": False}
                sealed = name != "G15_unsealed" or role != "child"
                db.execute("INSERT INTO operations VALUES(?,?,?,?,?)", (op, record["generation_id"], encode(record).decode(),
                           "sealed" if sealed else "prepared", encode(proof).decode() if sealed else None))
                for event in (["copying", "prepared", "sealed"] if sealed else ["copying", "prepared"]):
                    db.execute("INSERT INTO events(operation,event) VALUES(?,?)", (op, event))
        self.stage = StageFixture(self.work)
        p = self.stage.base.pin
        p["model_digest_sha256"] = self.index["manifest"][7:]
        self.reference = self.index["manifest"]
        self.stage.rows[0][2].params.update(digest=p["model_digest_sha256"], model_id=self.reference)
        self.stage.adapter._model_id = self.reference
        self.identity = EngineIdentityAdapter(self.stage.auth, self.stage.manager, p, clock=lambda: self.now)
        self.receipts = ReceiptStore.create(self.work / "receipts.sqlite")
        self.empty_receipts = self.receipts.path.read_bytes()
        self.record = self.journal.get(self.child)["record"]
        self.binding = guarded.Binding(self.journal.journal_id, self.child, sha(encode(self.record)), self.volume_binding, encode(p))
        self.raw = self.stage.base.request
        if name == "G29_exact_wire":
            self.raw += b" \n"
        if name == "G19_context_budget":
            value = decode(self.raw)
            value["messages"][0]["content"] = "X" * p["application_context_units"]
            self.raw = encode(value)
        self.cancel = False
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.response, self.proof, self.pending, self.envelope = None, None, None, None

    def point(self, stage):
        if not self.armed:
            return
        stages = {"G04_before_admission": "before_admission", "G05_after_admission": "admitted",
                  "G07_before_complete": "before_complete", "G08_before_consume": "before_consume",
                  "G09_before_release": "before_release"}
        if stages.get(self.name) == stage:
            self.journal.revoke(self.parent)
        if self.name == "G11_auth_before_admission" and stage == "before_admission":
            self.stage.auth._keys_by_value = {}
        if self.name == "G21_lost_admission" and stage == "admitted":
            raise ValueError("Invented lost acknowledgement")

    def app(self):
        from dataclasses import replace

        binding, journal, root = self.binding, self.journal, self.root
        if self.name == "G13_wrong_record":
            binding = replace(binding, record_sha256="0" * 64)
        if self.name == "G14_wrong_journal":
            binding = replace(binding, journal_id="0" * 32)
        if self.name == "G16_writable":
            root = self.work / "writable-model"
            if not root.exists():
                shutil.copytree(self.root, root)
        if self.name == "G27_legacy_journal":
            journal = volume.Journal.create(self.work / "legacy.sqlite")
        return guarded.build(root, journal, binding, key=self.stage.base.key, issuer_key_id=ISSUER,
                             receipts=self.receipts, resolve_identity=self.identity, clock=lambda: self.now,
                             transport=httpx.MockTransport(self.native), checkpoint=self.point)

    async def native(self, outgoing):
        self.sent.append(outgoing)
        if self.cancel:
            raise asyncio.CancelledError()
        if self.name == "G24_concurrent":
            self.entered.set()
            await self.release.wait()
        if self.name == "G06_during_backend":
            self.journal.revoke(self.parent)
        if self.name == "G12_auth_during_backend":
            self.stage.auth._keys_by_value = {}
        if self.name == "G26_changed_pin":
            self.stage.adapter._num_ctx += 1
        value = {"model": self.reference, "message": {"role": "assistant", "content": "Invented guarded answer."},
                 "done": True, "done_reason": "length" if self.name == "G25_clipped" else "stop",
                 "prompt_eval_count": 40, "eval_count": 10}
        return httpx.Response(502 if self.name == "G18_backend_502" else 200,
                              headers={"content-type": "application/json"}, stream=NativeBytes(encode(value)))

    async def prepare(self, post):
        response = await post(IDENTITY_PATH, {"model": self.stage.base.pin["model_id"],
                              "route_sha256": self.stage.base.pin["route_sha256"], "challenge": operation(self.name + "-identity")})
        if response.status_code != 200:
            return response
        self.proof = IdentityChallenge(self.stage.base.key.public_key(), ISSUER, self.stage.base.pin,
                                       challenge=operation(self.name + "-identity")).consume(response.content, now=self.now)
        self.pending = ResponseChallenge(self.raw, self.proof, trusted_key=self.stage.base.key.public_key(), issuer_key_id=ISSUER,
                                         expected_pin=self.stage.base.pin, identity_nonce=operation(self.name + "-identity"),
                                         now=self.now, challenge=operation(self.name + "-response"))
        self.envelope = {"request_base64": base64.b64encode(self.raw).decode(), "identity_proof": self.proof,
                         "expectation": self.pending.expectation()}
        return response

    async def run(self, post, rebuild):
        initial = await self.prepare(post)
        if initial.status_code != 200:
            return initial.status_code
        self.armed = True
        if self.name == "G03_revoked_parent":
            self.journal.revoke(self.parent)
        if self.name == "G10_foreign_auth":
            self.stage.auth._keys_by_value = {}
        if self.name == "G17_context_override":
            self.envelope["operation_id"] = "0" * 32
        if self.name == "G28_expired":
            self.now += 121
        if self.name == "G20_commit_gap":
            def gap(stage):
                if stage == "committed_unanchored":
                    raise ValueError("Invented interruption")
            self.journal.checkpoint = gap
        if self.name == "G23_direct_hook":
            try:
                await self.application.route.hook.execute(self.raw, self.stage.base.pin, expires_at=self.now + 120)
            except ValueError:
                return "direct_rejected"
            return "invalid-direct-admission"
        if self.name == "G24_concurrent":
            first = asyncio.create_task(post(COMPLETION_PATH, self.envelope))
            await asyncio.wait_for(self.entered.wait(), 2)
            second = await post(COMPLETION_PATH, self.envelope)
            self.release.set()
            self.response = await first
            if self.response.status_code != 200:
                return "invalid-first"
            self.pending.consume(self.response.content, now=self.now)
            return second.status_code
        self.response = await post(COMPLETION_PATH, self.envelope)
        status = self.response.status_code
        if status == 200:
            self.pending.consume(self.response.content, now=self.now)
        if self.name in {"G02_replay", "G18_backend_502", "G20_commit_gap", "G21_lost_admission", "G22_receipt_rollback"}:
            if self.name == "G20_commit_gap":
                self.journal.checkpoint = None
                control.Journal.reconcile(self.journal.path, self.journal.anchor.path, self.journal.journal_id)
            if self.name == "G22_receipt_rollback":
                self.receipts.path.write_bytes(self.empty_receipts)
            self.application = rebuild()
            status = (await post(COMPLETION_PATH, self.envelope)).status_code
        return status

    def result(self, status, kind):
        rows = self.journal.recover(self.child)
        private = CREDENTIAL.encode()
        database = self.journal.path.read_bytes() + self.receipts.path.read_bytes()
        if (private in database or b"Invented protocol input." in database or b"Invented guarded answer." in database
                or any("authorization" in r.headers or private in r.content for r in self.sent)):
            raise ValueError("Synthetic privacy sentinel leaked")
        frame = None
        if status == 200:
            frame = {"public_key_base64": base64.b64encode(self.stage.base.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode(),
                     "pin": self.stage.base.pin, "request_base64": base64.b64encode(self.raw).decode(), "identity_proof": self.proof,
                     "identity_nonce": operation(self.name + "-identity"), "response_nonce": operation(self.name + "-response"),
                     "now": self.now, "response_envelope_base64": base64.b64encode(self.response.content).decode()}
        return {"id": self.name, "status": status, "simulated_backend_sends": len(self.sent), "kind": kind,
                "nonce_counts": rows["nonce_counts"], "operation_state": rows["state"], "frame": frame,
                "request_sha256": sha(self.raw), "privacy_sentinels_absent": True,
                "native_execution_authorized": False, "production_activation": False}
