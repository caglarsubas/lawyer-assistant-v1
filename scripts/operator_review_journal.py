"""Bounded disposable review journal; independent anchor detects one-sided rollback.

Recovery never creates a review, changes its bytes, or renews its authority.
Privileged joint rollback of the journal, anchor and identity store is unqualified.
"""

import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import operator_enrollment_evidence as e
from authenticated_operator_review import DECISION, DECISIONS, HANDOFF, MAX_FILES

SCHEMA = "anchored-operator-review-v1"
ZERO = "0" * 64
MAX_DEPTH = 16


def reject():
    raise ValueError("Anchored review rejected; explicit reconciliation required")


def actor(value, *, session):
    keys = {"user_id", "firm_id", "kind", "profile_id", "role_sha256"}
    if session:
        keys |= {"session_sha256", "expires_at"}
    if not isinstance(value, dict) or set(value) != keys or value["kind"] not in {"preparer", "reviewer"}:
        reject()
    for key in ("user_id", "profile_id"):
        e.token(value[key], 32)
    e.token(value["role_sha256"])
    e.label(value["firm_id"])
    if session:
        e.token(value["session_sha256"])
        e.stamp(value["expires_at"])


def validate(record, scope):
    fields = {"schema", "handoff_id", "packet_sha256", "observation_sha256", "context_sha256", "prepared_by", "reviewer", "created_at", "expires_at", *e.FLAGS}
    decision = record.get("schema") == DECISION
    if decision:
        fields |= {"handoff_sha256", "reviewed_by", "reviewed_at", "decision", "reason_code"}
    if set(record) != fields or record["schema"] not in {HANDOFF, DECISION} or any(record[k] is not False for k in e.FLAGS):
        reject()
    e.token(record["handoff_id"], 32)
    for key in ("packet_sha256", "observation_sha256", "context_sha256"):
        e.token(record[key])
    for key in ("created_at", "expires_at"):
        e.stamp(record[key])
    if not 0 < record["expires_at"] - record["created_at"] <= 300:
        reject()
    actor(record["prepared_by"], session=True)
    actor(record["reviewer"], session=False)
    if record["prepared_by"]["kind"] != "preparer" or record["reviewer"]["kind"] != "reviewer" or record["prepared_by"]["user_id"] == record["reviewer"]["user_id"]:
        reject()
    for subject in (record["prepared_by"], record["reviewer"]):
        if any(subject[k] != scope[k] for k in ("firm_id", "profile_id")):
            reject()
    if decision:
        e.token(record["handoff_sha256"])
        actor(record["reviewed_by"], session=True)
        if ({k: record["reviewed_by"][k] for k in record["reviewer"]} != record["reviewer"]
                or not record["created_at"] <= e.stamp(record["reviewed_at"]) < record["expires_at"]
                or DECISIONS.get(record["decision"]) != record["reason_code"]):
            reject()
    return record["handoff_id"] + (".decision.json" if decision else ".handoff.json")


def frame(identity, seq, previous, rows):
    state = e.sha(e.encode(rows))
    return {"journal_id": identity, "seq": seq, "previous": previous,
            "head": e.sha(e.encode({"schema": SCHEMA, "journal_id": identity, "seq": seq, "previous": previous, "state": state}))}


class ReviewJournal:
    @classmethod
    def create(cls, path, anchor, ledger, scope, api):
        path, anchor, ledger = Path(path), Path(anchor), e.directory(ledger)
        for parent in (path.parent, anchor.parent):
            e.directory(parent)
        if len({path.parent.resolve(), anchor.parent.resolve(), ledger.resolve()}) != 3 or path.exists() or anchor.exists() or any(ledger.iterdir()):
            reject()
        identity = secrets.token_hex(16)
        api.sealed_volume.write_new(path, b"")
        db = sqlite3.connect(path)
        try:
            db.executescript("PRAGMA synchronous=FULL; CREATE TABLE metadata(schema TEXT,id TEXT,scope TEXT);"
                             "CREATE TABLE records(seq INTEGER PRIMARY KEY,name TEXT UNIQUE,raw TEXT,parent TEXT);"
                             "CREATE TABLE audit(seq INTEGER PRIMARY KEY,frame TEXT);")
            db.execute("INSERT INTO metadata VALUES(?,?,?)", (SCHEMA, identity, e.encode(scope).decode()))
            db.execute("INSERT INTO audit VALUES(0,?)", (e.encode(frame(identity, 0, ZERO, [])).decode(),))
            db.commit()
        finally:
            db.close()
        api.sealed_volume.sync_dir(path.parent)
        e.retain(anchor, e.encode(frame(identity, 0, ZERO, [])) + b"\n")
        api.sealed_volume.sync_dir(anchor.parent)
        return cls(path, anchor, ledger, scope, identity, api)

    def __init__(self, path, anchor, ledger, scope, identity, api, *, checkpoint=None):
        self.path, self.ledger, self.scope = Path(path), e.directory(ledger), dict(scope)
        self.identity, self.api = e.token(identity, 32), api
        self.anchor = api.control.Anchor(anchor)
        self.checkpoint = checkpoint
        if len({self.path.parent.resolve(), self.anchor.path.parent.resolve(), self.ledger.resolve()}) != 3:
            reject()

    def point(self, name):
        if self.checkpoint:
            self.checkpoint(name)

    def inspect(self, db, fence):
        if (db.execute("PRAGMA integrity_check").fetchone() != ("ok",)
                or db.execute("SELECT schema,id,scope FROM metadata").fetchall() != [(SCHEMA, self.identity, e.encode(self.scope).decode())]
                or {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} != {"metadata", "records", "audit"}
                or db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger')").fetchone()):
            reject()
        records = db.execute("SELECT seq,name,raw,parent FROM records ORDER BY seq LIMIT ?", (MAX_FILES + 1,)).fetchall()
        audits = db.execute("SELECT seq,frame FROM audit ORDER BY seq LIMIT ?", (MAX_FILES + 2,)).fetchall()
        if len(records) > MAX_FILES or len(audits) != len(records) + 1:
            reject()
        rows, seen, parents, frames, previous = [], {}, {}, [], ZERO
        for seq in range(len(audits)):
            if seq:
                n, name, raw, parent = records[seq - 1]
                record = e.decode(raw.encode())
                if n != seq or e.encode(record).decode() != raw or validate(record, self.scope) != name or name in seen:
                    reject()
                ancestor = e.decode(parent.encode()) if parent else None
                ident = record["handoff_id"]
                if record["schema"] == DECISION:
                    hname = ident + ".handoff.json"
                    if hname not in seen or ancestor is not None or record["handoff_sha256"] != e.sha(seen[hname].encode()):
                        reject()
                    h = e.decode(seen[hname].encode())
                    if any(record[k] != value for k, value in h.items() if k != "schema"):
                        reject()
                elif ancestor is not None:
                    if set(ancestor) != {"handoff_id", "handoff_sha256", "decision_sha256"}:
                        reject()
                    prior = e.token(ancestor["handoff_id"], 32)
                    for suffix, digest in (("handoff", ancestor["handoff_sha256"]), ("decision", ancestor["decision_sha256"])):
                        key = prior + "." + suffix + ".json"
                        if key not in seen or e.sha(seen[key].encode()) != e.token(digest):
                            reject()
                    if prior == ident:
                        reject()
                    parents[ident] = prior
                    cursor, depth = ident, 0
                    while cursor in parents:
                        depth += 1
                        cursor = parents[cursor]
                        if depth > MAX_DEPTH:
                            reject()
                seen[name] = raw
                rows.append([n, name, raw, parent])
            f = frame(self.identity, seq, previous, rows)
            if audits[seq] != (seq, e.encode(f).decode()):
                reject()
            # A database-only attacker cannot invent a recoverable suffix: its
            # exact frame must have been durably admitted outside DB backups.
            if seq and e.read(self.anchor.path.parent / (f["head"] + ".intent.json")) != e.encode(f):
                reject()
            frames.append(f)
            previous = f["head"]
        if fence not in frames or len(frames) - 1 - fence["seq"] not in {0, 1}:
            reject()
        files = list(self.ledger.iterdir())
        if len(files) > MAX_FILES or any(p.name not in seen for p in files):
            reject()
        for p in files:
            if e.read(p) != seen[p.name].encode():
                reject()
        missing = sorted(set(seen) - {p.name for p in files})
        return rows, frames[-1], missing

    @contextmanager
    def locked(self, *, write=False, recovery=False):
        self.api.sealed_volume.control_file(self.path)
        if self.path.stat().st_size > 8 * 1024**2:
            reject()
        with self.anchor.locked(write=write) as (fd, fence):
            db = sqlite3.connect(self.path.resolve().as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=2, isolation_level=None)
            try:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA query_only=" + ("OFF" if write else "ON"))
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                rows, tip, missing = self.inspect(db, fence)
                if not recovery and (tip != fence or missing):
                    reject()
                yield db, fd, fence, rows, tip, missing
            finally:
                db.rollback()
                db.close()

    def append(self, path, raw, parent):
        record = e.decode(raw)
        if path.parent != self.ledger or validate(record, self.scope) != path.name or e.encode(record) != raw:
            reject()
        with self.locked(write=True) as (db, fd, fence, rows, tip, missing):
            if len(rows) >= MAX_FILES or path.name in {r[1] for r in rows}:
                raise FileExistsError("Immutable review already retained")
            n = len(rows) + 1
            row = [n, path.name, raw.decode(), e.encode(parent).decode() if parent else None]
            db.execute("INSERT INTO records VALUES(?,?,?,?)", row)
            next_frame = frame(self.identity, n, fence["head"], [*rows, row])
            db.execute("INSERT INTO audit VALUES(?,?)", (n, e.encode(next_frame).decode()))
            intents = list(self.anchor.path.parent.glob("*.intent.json"))
            if len(intents) >= 2 * MAX_FILES:
                reject()
            e.retain(self.anchor.path.parent / (next_frame["head"] + ".intent.json"), e.encode(next_frame))
            self.api.sealed_volume.sync_dir(self.anchor.path.parent)
            self.inspect(db, fence)  # Validate lineage before durable admission.
            self.point("before_db_commit")
            db.commit()
            self.point("committed_unanchored")
            self.anchor.append(fd, fence, next_frame)
            self.point("anchored")
            e.retain(path, raw)
            self.api.sealed_volume.sync_dir(self.ledger)
            self.point("projected")
        return {"sha256": e.sha(raw)}

    def recover(self, expected, *, repair=False, recheck=lambda: None):
        with self.locked(write=repair, recovery=True) as (db, fd, fence, rows, tip, missing):
            observed = {"anchor_head_sha256": fence["head"], "journal_tip_sha256": tip["head"]}
            if expected is not None and expected != observed:
                reject()
            if repair:
                if expected is None:
                    reject()
                recheck()
                if tip != fence:
                    self.anchor.append(fd, fence, tip)
                for _, name, raw, _ in rows:
                    if name in missing:
                        recheck()
                        e.retain(self.ledger / name, raw.encode())
                self.api.sealed_volume.sync_dir(self.ledger)
                recheck()
            return {**observed, "status": "anchored_history_recovered" if repair else "recovery_observed_needs_pin",
                    "records": len(rows), "missing_projections": len(missing), "unanchored_commits": int(tip != fence),
                    **dict.fromkeys(e.FLAGS, False)}

    def parent(self, value):
        with self.locked() as (_, _, _, rows, _, _):
            by_name = {r[1]: r[2].encode() for r in rows}
            ident = e.token(value["handoff_id"], 32)
            for kind in ("handoff", "decision"):
                raw = by_name.get(ident + "." + kind + ".json")
                if raw is None or e.sha(raw) != e.token(value[kind + "_sha256"]):
                    reject()
            return dict(value)

    def lineage(self, ident):
        with self.locked() as (_, _, _, rows, _, _):
            row = next(r for r in rows if r[1] == ident + ".handoff.json")
            return e.decode(row[3].encode()) if row[3] else None
