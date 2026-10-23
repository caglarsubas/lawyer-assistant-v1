"""Isolated durable packet-accounting candidate; no provider, CLI or app hook.

A trusted issuer must authorize each exact grant/action against acquired evidence
and current permissions. Hashes and ledger admission do not grant native execution.
The configured store identity must be retained outside this file; backups/host
administration are outside the anti-replay boundary and require external fencing.
"""

import json
import os
import re
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from disposable_packet_selector import MARKER as SELECTOR
from disposable_packet_selector import Allowance, profile
from offline_quotation_boundaries import sha
from whole_passage_packets import plan_packets

from app.evidence_prompt import canonical

RECIPE = "disposable-durable-packet-campaign-v1"
SCHEMA = """
CREATE TABLE store_meta (id INTEGER PRIMARY KEY CHECK(id=1), store_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version=1));
CREATE TABLE campaigns (grant_id TEXT PRIMARY KEY, grant_json TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1)));
CREATE TABLE attempts (grant_id TEXT NOT NULL REFERENCES campaigns(grant_id), packet_id TEXT NOT NULL,
 units INTEGER NOT NULL CHECK(units>0), copied_bytes INTEGER NOT NULL CHECK(copied_bytes>0),
 state TEXT NOT NULL CHECK(state IN ('reserved','returned_unqualified','failed_consumed')), result_sha256 TEXT,
 PRIMARY KEY(grant_id,packet_id), CHECK((state='returned_unqualified' AND length(result_sha256)=64) OR
 (state IN ('reserved','failed_consumed') AND result_sha256 IS NULL)));
"""


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Canonical campaign/store UUID required")
    return value


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def prepare_grant(grant_id, question, originals, plan, allowance, *, context_limit=8192):
    """Read-only nomination, not issuer approval. All text stays outside ledger."""
    identity(grant_id)
    profile(context_limit)
    if type(allowance) is not Allowance:
        raise ValueError("Explicit campaign allowance required")
    sources_json, plan_json = canonical(originals), canonical(plan)
    frozen = json.loads(plan_json)
    rebuilt = plan_packets(question, json.loads(sources_json), context_limit=context_limit, max_packets=frozen["limits"]["max_packets"])
    if canonical(rebuilt) != plan_json or not rebuilt["empty_envelope_measurement"]["within_budget"]:
        raise ValueError("Stale or blocked campaign evidence")
    allowance.validate(rebuilt)
    context = {"recipe": SELECTOR, "question_sha256": sha(question), "source_inventory_sha256": rebuilt["source_inventory_sha256"],
               "plan_sha256": rebuilt["plan_sha256"], "context_limit_units": context_limit,
               "allowance": allowance.__dict__, "not_native_or_production_authorization": True}
    grant = {"recipe": RECIPE, "grant_id": grant_id, "selector_context": context,
        "selector_context_sha256": sha(canonical(context)), "packets": [{"id": p["id"],
            "messages_sha256": p["measurement"]["messages_sha256"], "units": p["measurement"]["total_upper_bound_units"],
            "copied_bytes": p["copied_text_utf8_bytes"]} for p in rebuilt["packets"]],
        "not_native_or_production_authorization": True}
    if canonical(originals) != sources_json or canonical(plan) != plan_json:
        raise ValueError("Campaign evidence changed during preparation")
    grant["grant_sha256"] = sha(canonical(grant))
    return grant


def validate_grant(grant):
    """Structural and cost check only; trusted issuer verifies source authority."""
    text = canonical(grant)
    if len(text.encode()) > 16000:
        raise ValueError("Unbounded campaign grant")
    g = json.loads(text)
    fields = {"recipe", "grant_id", "selector_context", "selector_context_sha256", "packets",
              "not_native_or_production_authorization", "grant_sha256"}
    if set(g) != fields or g["recipe"] != RECIPE or g["not_native_or_production_authorization"] is not True:
        raise ValueError("Unknown campaign grant")
    identity(g["grant_id"])
    body = {k: v for k, v in g.items() if k != "grant_sha256"}
    if g["grant_sha256"] != sha(canonical(body)) or g["selector_context_sha256"] != sha(canonical(g["selector_context"])):
        raise ValueError("Altered campaign seal")
    c = g["selector_context"]
    if (set(c) != {"recipe", "question_sha256", "source_inventory_sha256", "plan_sha256", "context_limit_units", "allowance", "not_native_or_production_authorization"}
            or c["recipe"] != SELECTOR or c["not_native_or_production_authorization"] is not True
            or any(not digest(c[k]) for k in ("question_sha256", "source_inventory_sha256", "plan_sha256"))):
        raise ValueError("Invalid selector context")
    profile(c["context_limit_units"])
    a = c["allowance"]
    if set(a) != {"completion_attempts", "context_units", "copied_text_bytes"}:
        raise ValueError("Unknown campaign allowance")
    limits = (a["completion_attempts"], a["context_units"], a["copied_text_bytes"])
    if any(type(x) is not int or not 0 <= x <= cap for x, cap in zip(limits, (8, 65536, 32000))):
        raise ValueError("Invalid campaign allowance")
    packets = g["packets"]
    if not isinstance(packets, list) or len(packets) > 8:
        raise ValueError("Invalid campaign packet inventory")
    for n, p in enumerate(packets):
        if (set(p) != {"id", "messages_sha256", "units", "copied_bytes"} or p["id"] != "P" + str(n + 1)
                or not digest(p["messages_sha256"]) or type(p["units"]) is not int or not 0 < p["units"] <= c["context_limit_units"]
                or type(p["copied_bytes"]) is not int or not 0 < p["copied_bytes"] <= 4000):
            raise ValueError("Invalid campaign packet cost or identity")
    if len(packets) > limits[0] or sum(p["units"] for p in packets) > limits[1] or sum(p["copied_bytes"] for p in packets) > limits[2]:
        raise ValueError("Whole campaign exceeds its allowance")
    return text


def private_path(path, *, exists):
    p = Path(path)
    if not p.is_absolute():
        raise ValueError("Absolute private ledger path required")
    parent = p.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700 or p.parent.resolve() != p.parent:
        raise ValueError("Ledger requires an owned, nonsymlink private directory")
    if exists:
        f = p.lstat()
        if not stat.S_ISREG(f.st_mode) or f.st_uid != os.getuid() or stat.S_IMODE(f.st_mode) != 0o600 or f.st_nlink != 1:
            raise ValueError("Unsafe ledger file")
    return p


class CampaignLedger:
    """Cross-process reservations in one configured private SQLite authority.

    No reset, refund, retry, deletion, missing-store recreation or result replay.
    A stale reservation stays consumed and ambiguous; it is never resumed.
    """

    @classmethod
    def create(cls, path):
        p = private_path(path, exists=False)
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        store_id = str(uuid.uuid4())
        with sqlite3.connect(p) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO store_meta VALUES (1,?,1)", (store_id,))
        # Persist directory entry as well as SQLite's synchronous commit.
        fd = os.open(p.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return cls(p, expected_store_id=store_id)

    def __init__(self, path, *, expected_store_id):
        self.path, self.store_id = private_path(path, exists=True), identity(expected_store_id)
        with self._db():
            pass

    @contextmanager
    def _db(self):
        private_path(self.path, exists=True)
        db = None
        try:
            db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=2, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            if db.execute("PRAGMA journal_mode").fetchone()[0] != "delete" or db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Unqualified ledger mode or integrity")
            rows = db.execute("SELECT id,store_id,version FROM store_meta").fetchall()
            if len(rows) != 1 or tuple(rows[0]) != (1, self.store_id, 1):
                raise ValueError("Ledger authority identity differs")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except sqlite3.Error:
            raise ValueError("Ledger unavailable or inconsistent; no dispatch authorized") from None
        finally:
            if db is not None:
                db.close()  # An uncommitted transaction rolls back, never a committed reservation.

    def _approved(self, grant, action, authorize):
        if not callable(authorize) or authorize(json.loads(grant), action) is not True:
            raise ValueError("Exact campaign action not authorized")

    def _load(self, db, text):
        g = json.loads(text)
        row = db.execute("SELECT grant_json,revoked FROM campaigns WHERE grant_id=?", (g["grant_id"],)).fetchone()
        if row is None or row["grant_json"] != text:
            raise ValueError("Unknown or changed admitted campaign")
        attempts = db.execute("SELECT * FROM attempts WHERE grant_id=? ORDER BY packet_id", (g["grant_id"],)).fetchall()
        by_id = {p["id"]: p for p in g["packets"]}
        if any(a["packet_id"] not in by_id or (a["units"], a["copied_bytes"]) !=
               (by_id[a["packet_id"]]["units"], by_id[a["packet_id"]]["copied_bytes"]) for a in attempts):
            raise ValueError("Ledger attempt costs differ from admitted campaign")
        return g, bool(row["revoked"]), attempts

    def admit(self, grant, *, authorize):
        text = validate_grant(grant)
        with self._db() as db:
            self._approved(text, "admit", authorize)
            if db.execute("SELECT 1 FROM campaigns WHERE grant_id=?", (json.loads(text)["grant_id"],)).fetchone():
                raise ValueError("Campaign grant already consumed by admission")
            db.execute("INSERT INTO campaigns(grant_id,grant_json) VALUES (?,?)", (json.loads(text)["grant_id"], text))
            self._approved(text, "admit", authorize)

    def reserve(self, grant, packet_id, *, authorize):
        text = validate_grant(grant)
        with self._db() as db:
            self._approved(text, "reserve", authorize)
            g, revoked, attempts = self._load(db, text)
            p = next((p for p in g["packets"] if p["id"] == packet_id), None)
            if revoked or p is None or any(a["packet_id"] == packet_id for a in attempts):
                raise ValueError("Revoked, unknown or already reserved packet")
            a = g["selector_context"]["allowance"]
            if (len(attempts) + 1 > a["completion_attempts"] or sum(x["units"] for x in attempts) + p["units"] > a["context_units"]
                    or sum(x["copied_bytes"] for x in attempts) + p["copied_bytes"] > a["copied_text_bytes"]):
                raise ValueError("Durable aggregate budget exhausted")
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,'reserved',NULL)", (g["grant_id"], packet_id, p["units"], p["copied_bytes"]))
            self._approved(text, "reserve", authorize)
        # A caller must receive this only AFTER durable commit; crashes never free the packet.
        return {"grant_sha256": g["grant_sha256"], "selector_context_sha256": g["selector_context_sha256"],
                "packet_id": packet_id, "units": p["units"], "copied_bytes": p["copied_bytes"], "state": "reserved_consumed"}

    def settle(self, grant, packet_id, *, outcome, result_sha256=None, authorize):
        if outcome not in {"returned_unqualified", "failed_consumed"} or (not digest(result_sha256) if outcome == "returned_unqualified" else result_sha256 is not None):
            raise ValueError("Invalid terminal metadata")
        text = validate_grant(grant)
        with self._db() as db:
            self._approved(text, "settle", authorize)
            g, revoked, _ = self._load(db, text)
            if revoked and outcome != "failed_consumed":
                raise ValueError("Revoked campaign cannot publish a result")
            updated = db.execute("UPDATE attempts SET state=?,result_sha256=? WHERE grant_id=? AND packet_id=? AND state='reserved'",
                                 (outcome, result_sha256, g["grant_id"], packet_id))
            if updated.rowcount != 1:
                raise ValueError("Unknown or already terminal reservation")
            self._approved(text, "settle", authorize)

    def revoke(self, grant, *, authorize):
        text = validate_grant(grant)
        with self._db() as db:
            self._approved(text, "revoke", authorize)
            g, _, _ = self._load(db, text)
            db.execute("UPDATE campaigns SET revoked=1 WHERE grant_id=?", (g["grant_id"],))
            self._approved(text, "revoke", authorize)

    def receipt(self, grant, *, authorize):
        text = validate_grant(grant)
        with self._db() as db:
            self._approved(text, "inspect", authorize)
            g, revoked, attempts = self._load(db, text)
            result = {"recipe": RECIPE, "grant_sha256": g["grant_sha256"], "revoked": revoked,
                "consumed_completion_attempts": len(attempts), "consumed_upper_bound_units": sum(x["units"] for x in attempts),
                "consumed_copied_text_bytes": sum(x["copied_bytes"] for x in attempts),
                "attempts": [{k: a[k] for k in ("packet_id", "state", "result_sha256")} for a in attempts],
                "production_activation": False, "native_or_legal_qualification": False}
            self._approved(text, "inspect", authorize)
            return result
