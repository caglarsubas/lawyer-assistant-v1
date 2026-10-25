"""Bounded append-only disposable restore controls with external admission intents."""

import re
import secrets
from contextlib import contextmanager
from pathlib import Path

import operator_enrollment_evidence as e
from operator_review_journal import ZERO, actor, reject

SCHEMA, MAX_EVENTS = "restore-control-v1", 256


def ref(event):
    return e.sha(e.encode(event))


def fold(events, scope):
    operations, selections = {}, {}
    for event in events:
        kind, p = event["kind"], event["payload"]
        common = {"operation_id", "created_at", *e.FLAGS}
        fields = {
            "prepared": {"backup_id", "manifest_sha256", "review_head_sha256", "target_sha256", "custody_sha256", "packet_sha256", "observation_sha256", "prepared_by", "reviewer", "expires_at"},
            "decision": {"prepared_sha256", "reviewed_by", "decision", "reason_code"},
            "consumed": {"authorization_sha256", "executed_by"},
            "revoked": {"revoked_by"},
            "selected": {"selection_id", "authorization_sha256", "restore_intent_sha256", "restore_receipt_sha256", "selected_by"},
        }
        if kind not in fields or not isinstance(p, dict) or set(p) != common | fields[kind] or any(p[k] is not False for k in e.FLAGS):
            reject()
        ident, now = e.token(p["operation_id"], 32), e.stamp(p["created_at"])
        if kind == "prepared":
            if ident in operations or not 0 < e.stamp(p["expires_at"]) - now <= 300 or p["custody_sha256"] != scope["custody_sha256"]:
                reject()
            e.token(p["backup_id"], 32)
            for key in ("manifest_sha256", "review_head_sha256", "target_sha256", "custody_sha256", "packet_sha256", "observation_sha256"):
                e.token(p[key])
            actor(p["prepared_by"], session=True)
            actor(p["reviewer"], session=False)
            if p["prepared_by"]["kind"] != "preparer" or p["reviewer"]["kind"] != "reviewer" or p["prepared_by"]["user_id"] == p["reviewer"]["user_id"]:
                reject()
            for subject in (p["prepared_by"], p["reviewer"]):
                if any(subject[k] != scope[k] for k in ("firm_id", "profile_id")):
                    reject()
            operations[ident] = {"prepared": event}
            continue
        if ident not in operations:
            reject()
        state = operations[ident]
        prepared = state["prepared"]["payload"]
        if now < prepared["created_at"]:
            reject()
        if kind == "revoked":
            actor(p["revoked_by"], session=True)
            if "revoked" in state or p["revoked_by"]["user_id"] not in {prepared["prepared_by"]["user_id"], prepared["reviewer"]["user_id"]} or any(p["revoked_by"][k] != scope[k] for k in ("firm_id", "profile_id")):
                reject()
        else:
            if "revoked" in state or now >= prepared["expires_at"]:
                reject()
            if kind == "decision":
                actor(p["reviewed_by"], session=True)
                if ("decision" in state or p["prepared_sha256"] != ref(state["prepared"])
                        or {k: p["reviewed_by"][k] for k in prepared["reviewer"]} != prepared["reviewer"]
                        or {"approve": "exact_restore_scope_checked", "deny": "restore_declined"}.get(p["decision"]) != p["reason_code"]):
                    reject()
            else:
                if "decision" not in state or state["decision"]["payload"]["decision"] != "approve" or p["authorization_sha256"] != ref(state["decision"]):
                    reject()
                if kind == "consumed":
                    actor(p["executed_by"], session=True)
                    if "consumed" in state or p["executed_by"] != prepared["prepared_by"]:
                        reject()
                elif kind == "selected":
                    actor(p["selected_by"], session=True)
                    sid = e.token(p["selection_id"], 32)
                    if sid in selections or "consumed" not in state or p["selected_by"] != state["decision"]["payload"]["reviewed_by"] or now < state["consumed"]["payload"]["created_at"]:
                        reject()
                    for key in ("restore_intent_sha256", "restore_receipt_sha256"):
                        e.token(p[key])
                    selections[sid] = event
        state[kind] = event
    return operations, selections


class RestoreControlLog:
    schema = SCHEMA

    def validate(self, events):
        return fold(events, self.scope)

    @classmethod
    def create(cls, root, anchor_path, scope, api):
        root, anchor_path = e.directory(root), Path(anchor_path)
        e.directory(anchor_path.parent)
        if root == anchor_path.parent.resolve() or any(root.iterdir()) or anchor_path.exists():
            reject()
        identity = secrets.token_hex(16)
        metadata = {"schema": cls.schema, "control_id": identity, "scope": scope, **dict.fromkeys(e.FLAGS, False)}
        e.retain(root / "metadata.json", e.encode(metadata))
        api.sealed_volume.sync_dir(root)
        initial = {"journal_id": identity, "seq": 0, "previous": ZERO, "head": e.sha(e.encode(metadata))}
        e.retain(anchor_path, e.encode(initial) + b"\n")
        api.sealed_volume.sync_dir(anchor_path.parent)
        return cls(root, anchor_path, scope, identity, api)

    def __init__(self, root, anchor_path, scope, identity, api, *, checkpoint=None):
        self.root, self.scope, self.identity, self.api = e.directory(root), dict(scope), e.token(identity, 32), api
        self.anchor = api.control.Anchor(anchor_path)
        self.checkpoint = checkpoint
        if self.root == self.anchor.path.parent.resolve():
            reject()

    def scan(self, fence):
        metadata = {"schema": self.schema, "control_id": self.identity, "scope": self.scope, **dict.fromkeys(e.FLAGS, False)}
        if e.read(self.root / "metadata.json") != e.encode(metadata):
            reject()
        paths = sorted(p for p in self.root.iterdir() if p.name != "metadata.json")
        if len(paths) > MAX_EVENTS or any(not re.fullmatch(r"[0-9a-f]{4}\.json", p.name) for p in paths):
            reject()
        initial = {"journal_id": self.identity, "seq": 0, "previous": ZERO, "head": e.sha(e.encode(metadata))}
        frames, events = [initial], []
        for seq, path in enumerate(paths, 1):
            raw = e.read(path)
            event = e.decode(raw)
            fields = {"schema", "control_id", "seq", "previous", "kind", "payload", "head", *e.FLAGS}
            if (path.name != f"{seq:04x}.json" or e.encode(event) != raw or set(event) != fields or event["schema"] != self.schema
                    or event["control_id"] != self.identity or type(event["seq"]) is not int or event["seq"] != seq
                    or event["previous"] != frames[-1]["head"] or any(event[k] is not False for k in e.FLAGS)
                    or event["head"] != e.sha(e.encode({k: v for k, v in event.items() if k != "head"}))):
                reject()
            frame = {"journal_id": self.identity, "seq": seq, "previous": event["previous"], "head": event["head"]}
            if e.read(self.anchor.path.parent / (event["head"] + ".intent.json")) != e.encode(frame):
                reject()
            events.append(event)
            frames.append(frame)
        self.validate(events)
        if fence not in frames or len(events) - fence["seq"] not in {0, 1}:
            reject()
        return events, frames[-1]

    @contextmanager
    def locked(self, *, write=False, recovery=False):
        with self.anchor.locked(write=write) as (fd, fence):
            events, tip = self.scan(fence)
            if not recovery and tip != fence:
                reject()
            yield fd, fence, events, tip

    def append(self, fd, fence, events, kind, payload):
        if len(events) >= MAX_EVENTS or len(list(self.anchor.path.parent.glob("*.intent.json"))) >= 2 * MAX_EVENTS:
            reject()
        event = {"schema": self.schema, "control_id": self.identity, "seq": len(events) + 1, "previous": fence["head"],
                 "kind": kind, "payload": payload, **dict.fromkeys(e.FLAGS, False)}
        event["head"] = e.sha(e.encode(event))
        self.validate([*events, event])
        frame = {"journal_id": self.identity, "seq": event["seq"], "previous": event["previous"], "head": event["head"]}
        e.retain(self.anchor.path.parent / (event["head"] + ".intent.json"), e.encode(frame))
        self.api.sealed_volume.sync_dir(self.anchor.path.parent)
        e.retain(self.root / f"{event['seq']:04x}.json", e.encode(event))
        self.api.sealed_volume.sync_dir(self.root)
        if self.checkpoint:
            self.checkpoint(kind + "_retained")
        self.anchor.append(fd, fence, frame)
        return event
