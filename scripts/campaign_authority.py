"""Disposable issuer/restore/identity boundary; no native provider dispatch.

The authority store must remain outside campaign backups. Its trusted issuer and
runtime observer are injected, not inferred from hashes, metadata labels or URLs.
Restoring this authority too, or hostile host administration, is outside the model.
"""

import json
import re

from durable_packet_campaign import CampaignLedger, digest, identity, validate_grant
from offline_quotation_boundaries import sha

from app.evidence_prompt import canonical

RECIPE = "disposable-campaign-authority-v1"
TABLES = (
    "CREATE TABLE guard_schema (version INTEGER PRIMARY KEY CHECK(version=1))",
    "CREATE TABLE guard_epochs (ledger_id TEXT PRIMARY KEY, epoch INTEGER NOT NULL CHECK(epoch>0))",
    "CREATE TABLE guard_intents (intent_id TEXT PRIMARY KEY, ledger_id TEXT NOT NULL REFERENCES guard_epochs(ledger_id), "
    "epoch INTEGER NOT NULL, grant_id TEXT NOT NULL UNIQUE, spec_json TEXT NOT NULL, checkpoint TEXT NOT NULL, pending_expected TEXT NOT NULL, phase TEXT NOT NULL "
    "CHECK(phase IN ('active','reserve_pending','settle_pending')), revoked INTEGER NOT NULL CHECK(revoked IN (0,1)))",
    "CREATE TABLE guard_spend (intent_id TEXT NOT NULL REFERENCES guard_intents(intent_id), packet_id TEXT NOT NULL, "
    "units INTEGER NOT NULL, copied_bytes INTEGER NOT NULL, PRIMARY KEY(intent_id,packet_id))",
)
PIN_FIELDS = {"model_id", "model_digest_sha256", "backend", "format", "model_context_units", "application_context_units",
              "tenant_id", "organization_id", "key_id", "transport_mode", "route_sha256", "cloud_fallback_disabled"}


def validate_pin(pin, limit):
    if not isinstance(pin, dict) or set(pin) != PIN_FIELDS:
        raise ValueError("Complete immutable runtime pin required")
    for k in ("model_id", "tenant_id", "organization_id", "key_id"):
        if not isinstance(pin[k], str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", pin[k]):
            raise ValueError("Invalid runtime identity label")
    if (not digest(pin["model_digest_sha256"]) or not digest(pin["route_sha256"])
            or pin["backend"] not in {"llama_cpp", "ollama_http", "mlx"}
            or pin["format"] != {"llama_cpp": "gguf", "ollama_http": "ollama_http", "mlx": "mlx"}.get(pin["backend"])
            or pin["transport_mode"] not in {"native_private", "approved_laptop_tunnel"}
            or pin["cloud_fallback_disabled"] is not True
            or type(pin["model_context_units"]) is not int or not limit <= pin["model_context_units"] <= 10**7
            or type(pin["application_context_units"]) is not int or pin["application_context_units"] != limit):
        raise ValueError("Unqualified model, route or context identity")
    return json.loads(canonical(pin))


class CampaignAuthority:
    @classmethod
    def create(cls, path):
        store = CampaignLedger.create(path)
        with store._db() as db:
            for statement in TABLES:
                db.execute(statement)
            db.execute("INSERT INTO guard_schema VALUES (1)")
        return cls(path, expected_authority_id=store.store_id)

    def __init__(self, path, *, expected_authority_id):
        self._store = CampaignLedger(path, expected_store_id=expected_authority_id)
        self.authority_id = self._store.store_id
        with self._store._db() as db:
            if [tuple(r) for r in db.execute("SELECT version FROM guard_schema")] != [(1,)]:
                raise ValueError("Unknown campaign authority schema")

    def _check(self, spec, action, authorize, observe):
        try:
            allowed = callable(authorize) and authorize(json.loads(canonical(spec)), action) is True
            observed = observe() if callable(observe) else None
            matched = canonical(validate_pin(observed, spec["grant"]["selector_context"]["context_limit_units"])) == canonical(spec["runtime_pin"])
        except Exception:
            raise ValueError("Campaign permission or current runtime identity unavailable") from None
        if not allowed or not matched:
            raise ValueError("Campaign permission or current runtime identity differs")

    def _load(self, db, spec):
        text = canonical(spec)
        row = db.execute("SELECT * FROM guard_intents WHERE intent_id=?", (spec["intent_id"],)).fetchone()
        epoch = db.execute("SELECT epoch FROM guard_epochs WHERE ledger_id=?", (spec["ledger_store_id"],)).fetchone()
        if (row is None or row["spec_json"] != text or spec["authority_id"] != self.authority_id
                or epoch is None or row["epoch"] != epoch[0] or row["revoked"]):
            raise ValueError("Unknown, changed, revoked or fenced campaign intent")
        return row

    def _receipt(self, ledger, spec):
        if type(ledger) is not CampaignLedger or ledger.store_id != spec["ledger_store_id"]:
            raise ValueError("Campaign ledger authority differs")
        # This closure admits only the exact already-approved metadata, never a
        # new grant. Outer checks enforce current issuer, epoch and identity.
        return ledger.receipt(spec["grant"], authorize=lambda g, action: action == "inspect" and canonical(g) == canonical(spec["grant"]))

    def register(self, intent_id, ledger, grant, pin, *, authorize, observe):
        identity(intent_id)
        frozen = json.loads(validate_grant(grant))
        runtime = validate_pin(pin, frozen["selector_context"]["context_limit_units"])
        if type(ledger) is not CampaignLedger or ledger.store_id == self.authority_id:
            raise ValueError("A distinct campaign ledger is required")
        with self._store._db() as db:
            row = db.execute("SELECT epoch FROM guard_epochs WHERE ledger_id=?", (ledger.store_id,)).fetchone()
            epoch = row[0] if row else 1
            spec = {"recipe": RECIPE, "authority_id": self.authority_id, "intent_id": intent_id,
                "ledger_store_id": ledger.store_id, "epoch": epoch, "grant": frozen,
                "runtime_pin": runtime, "not_native_or_production_authorization": True}
            self._check(spec, "register", authorize, observe)
            if db.execute("SELECT 1 FROM guard_intents WHERE intent_id=?", (intent_id,)).fetchone():
                raise ValueError("Issuer intent is one-use across grants and epochs")
            # A grant may not be rebound to another intent in this authority.
            if db.execute("SELECT 1 FROM guard_intents WHERE grant_id=?", (frozen["grant_id"],)).fetchone():
                raise ValueError("Campaign grant already bound to an issuer intent")
            receipt = self._receipt(ledger, spec)
            if receipt["consumed_completion_attempts"] or receipt["revoked"]:
                raise ValueError("Cannot adopt a spent or revoked campaign")
            if row is None:
                db.execute("INSERT INTO guard_epochs VALUES (?,1)", (ledger.store_id,))
            db.execute("INSERT INTO guard_intents VALUES (?,?,?,?,?,?,'','active',0)",
                       (intent_id, ledger.store_id, epoch, frozen["grant_id"], canonical(spec), sha(canonical(receipt))))
            self._check(spec, "register", authorize, observe)
        return json.loads(canonical(spec))

    def _begin(self, ledger, spec, packet_id, operation, authorize, observe, outcome=None, result_sha256=None):
        with self._store._db() as db:
            row = self._load(db, spec)
            self._check(spec, operation, authorize, observe)
            receipt = self._receipt(ledger, spec)
            if row["phase"] != "active" or sha(canonical(receipt)) != row["checkpoint"]:
                raise ValueError("Ambiguous operation or restored/changed campaign checkpoint")
            packet = next((p for p in spec["grant"]["packets"] if p["id"] == packet_id), None)
            if packet is None:
                raise ValueError("Unknown campaign packet")
            spent = db.execute("SELECT * FROM guard_spend WHERE intent_id=?", (spec["intent_id"],)).fetchall()
            if operation == "reserve":
                if any(x["packet_id"] == packet_id for x in spent):
                    raise ValueError("Issuer packet allowance already consumed")
                a = spec["grant"]["selector_context"]["allowance"]
                if (len(spent) + 1 > a["completion_attempts"] or sum(x["units"] for x in spent) + packet["units"] > a["context_units"]
                        or sum(x["copied_bytes"] for x in spent) + packet["copied_bytes"] > a["copied_text_bytes"]):
                    raise ValueError("Issuer aggregate allowance exhausted")
                db.execute("INSERT INTO guard_spend VALUES (?,?,?,?)", (spec["intent_id"], packet_id, packet["units"], packet["copied_bytes"]))
                receipt["consumed_completion_attempts"] += 1
                receipt["consumed_upper_bound_units"] += packet["units"]
                receipt["consumed_copied_text_bytes"] += packet["copied_bytes"]
                receipt["attempts"].append({"packet_id": packet_id, "state": "reserved", "result_sha256": None})
                receipt["attempts"].sort(key=lambda p: p["packet_id"])
            elif not any(x["packet_id"] == packet_id for x in spent):
                raise ValueError("Packet has no issuer reservation")
            else:
                attempt = next((a for a in receipt["attempts"] if a["packet_id"] == packet_id), None)
                if attempt is None or attempt["state"] != "reserved":
                    raise ValueError("Packet already terminal or ambiguous")
                attempt.update(state=outcome, result_sha256=result_sha256)
            db.execute("UPDATE guard_intents SET phase=?,pending_expected=? WHERE intent_id=?",
                       (operation + "_pending", sha(canonical(receipt)), spec["intent_id"]))
            self._check(spec, operation, authorize, observe)
        # This external commit precedes the campaign write. Any subsequent
        # failure leaves a consumed pending intent; never auto-reconcile/replay.
        return packet

    def _finish(self, ledger, spec, action, authorize, observe):
        with self._store._db() as db:
            row = self._load(db, spec)
            self._check(spec, action, authorize, observe)
            if row["phase"] != action + "_pending":
                raise ValueError("Unexpected issuer operation state")
            receipt = self._receipt(ledger, spec)
            if sha(canonical(receipt)) != row["pending_expected"]:
                raise ValueError("Campaign result differs from the exact pending operation")
            db.execute("UPDATE guard_intents SET checkpoint=?,phase='active',pending_expected='' WHERE intent_id=?",
                       (sha(canonical(receipt)), spec["intent_id"]))
            self._check(spec, action, authorize, observe)

    def reserve(self, ledger, spec, packet_id, *, authorize, observe):
        frozen = json.loads(canonical(spec))
        packet = self._begin(ledger, frozen, packet_id, "reserve", authorize, observe)
        try:
            ledger.reserve(frozen["grant"], packet_id, authorize=lambda *_: True)
            self._finish(ledger, frozen, "reserve", authorize, observe)
        except Exception:
            raise ValueError("Issuer reservation consumed; intent remains pending or fenced, never retry") from None
        return {"recipe": RECIPE, "intent_id": frozen["intent_id"], "epoch": frozen["epoch"],
                "packet_id": packet_id, "messages_sha256": packet["messages_sha256"],
                "runtime_pin_sha256": sha(canonical(frozen["runtime_pin"])),
                "selector_context_sha256": frozen["grant"]["selector_context_sha256"],
                "not_native_or_production_authorization": True}

    def settle(self, ledger, spec, packet_id, *, outcome, result_sha256=None, authorize, observe):
        if outcome not in {"returned_unqualified", "failed_consumed"} or (not digest(result_sha256) if outcome == "returned_unqualified" else result_sha256 is not None):
            raise ValueError("Invalid terminal metadata")
        frozen = json.loads(canonical(spec))
        self._begin(ledger, frozen, packet_id, "settle", authorize, observe, outcome, result_sha256)
        try:
            ledger.settle(frozen["grant"], packet_id, outcome=outcome, result_sha256=result_sha256, authorize=lambda *_: True)
            self._finish(ledger, frozen, "settle", authorize, observe)
        except Exception:
            raise ValueError("Issuer terminal operation pending or fenced; never replay") from None

    def fence_restore(self, ledger_store_id, *, authorize):
        identity(ledger_store_id)
        with self._store._db() as db:
            row = db.execute("SELECT epoch FROM guard_epochs WHERE ledger_id=?", (ledger_store_id,)).fetchone()
            if row is None or row[0] >= 10**9:
                raise ValueError("Unknown or exhausted restore epoch")
            request = {"recipe": RECIPE, "authority_id": self.authority_id, "ledger_store_id": ledger_store_id,
                       "previous_epoch": row[0], "next_epoch": row[0] + 1, "not_native_or_production_authorization": True}
            if not callable(authorize) or authorize(json.loads(canonical(request)), "fence_restore") is not True:
                raise ValueError("Restore fence not authorized")
            db.execute("UPDATE guard_epochs SET epoch=epoch+1 WHERE ledger_id=?", (ledger_store_id,))
            if authorize(json.loads(canonical(request)), "fence_restore") is not True:
                raise ValueError("Restore fence authorization changed")
        return request

    def revoke(self, spec, *, authorize):
        with self._store._db() as db:
            row = self._load(db, spec)
            if not callable(authorize) or authorize(json.loads(row["spec_json"]), "revoke") is not True:
                raise ValueError("Intent revocation not authorized")
            db.execute("UPDATE guard_intents SET revoked=1 WHERE intent_id=?", (spec["intent_id"],))
            if authorize(json.loads(row["spec_json"]), "revoke") is not True:
                raise ValueError("Intent revocation authorization changed")

    def receipt(self, spec, *, authorize):
        with self._store._db() as db:
            row = db.execute("SELECT * FROM guard_intents WHERE intent_id=?", (spec["intent_id"],)).fetchone()
            if row is None or row["spec_json"] != canonical(spec) or spec["authority_id"] != self.authority_id:
                raise ValueError("Unknown issuer intent")
            if not callable(authorize) or authorize(json.loads(row["spec_json"]), "inspect") is not True:
                raise ValueError("Issuer metadata access denied")
            epoch = db.execute("SELECT epoch FROM guard_epochs WHERE ledger_id=?", (spec["ledger_store_id"],)).fetchone()[0]
            spent = db.execute("SELECT units,copied_bytes FROM guard_spend WHERE intent_id=?", (spec["intent_id"],)).fetchall()
            if authorize(json.loads(row["spec_json"]), "inspect") is not True:
                raise ValueError("Issuer metadata authorization changed")
            return {"recipe": RECIPE, "epoch": row["epoch"], "current_epoch": epoch, "fenced": row["epoch"] != epoch,
                    "revoked": bool(row["revoked"]), "phase": row["phase"], "consumed_completion_attempts": len(spent),
                    "consumed_upper_bound_units": sum(x[0] for x in spent), "consumed_copied_text_bytes": sum(x[1] for x in spent),
                    "runtime_pin_sha256": sha(canonical(spec["runtime_pin"])),
                    "native_or_legal_qualification": False, "production_activation": False}
