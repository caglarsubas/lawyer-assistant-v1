"""Fresh invented identities and frozen recovery/re-review fault cases."""

import asyncio
import sqlite3
from dataclasses import replace

import operator_enrollment_evidence as e
import operator_review_fixture as old
from anchored_operator_review import AnchoredReviewHandoff
from authenticated_operator_review import DECISIONS, Target
from operator_review_journal import ReviewJournal, frame

CASES = [("R01_valid", 200), ("R02_lost_ack", 400), ("R03_db_commit_only", 200),
         ("R04_anchor_only", 200), ("R05_missing_projection", 200), ("R06_old_database", 400),
         ("R07_anchor_one_behind", 200), ("R08_anchor_deep_rollback", 400), ("R09_forged_suffix", 400),
         ("R10_source_stale", 200), ("R11_revoked_session", 401), ("R12_unassigned", 403),
         ("R13_wrong_recovery_pin", 400), ("R14_observation_only", 200), ("R15_repair_lost_ack", 400),
         ("R16_fresh_review", 200), ("R17_expired_parent_new_sessions", 200), ("R18_parent_hash", 400),
         ("R19_parent_undecided", 400), ("R20_reused_identity", 409), ("R21_rereview_replay", 409),
         ("R22_new_pending", 200), ("R23_changed_decision", 200), ("R24_role_changed", 409),
         ("R25_rereview_race", 409), ("R26_projection_tampered", 400), ("R27_recovery_no_csrf", 400),
         ("R28_before_db_commit", 200), ("R29_new_roles", 200), ("R30_expired_packet_history", 200),
         ("R31_missing_independent_intent", 400)]
POLICY = {"schema": "anchored-review-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "max_records": 128, "max_lineage_depth": 16,
          "actual_local_auth": True, "disposable_accounts_only": True, "model_verification_seconds": 20,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}


class Fixture(old.Fixture):
    def __init__(self, name, models, work, anchors, api):
        super().__init__(name, models, work, anchors, api)
        control, independent = self.work / "review-control", anchors / (e.sha((name + "-review").encode())[:32])
        control.mkdir(mode=0o700)
        independent.mkdir(mode=0o700)
        scope = {"firm_id": self.authority.firm_id, "profile_id": self.authority.profile_id,
                 "marker_sha256": self.authority.marker_sha, "bindings_sha256": e.sha(e.encode(dict(self.authority.bindings)))}
        self.journal = ReviewJournal.create(control / "review.sqlite", independent / "review.anchor", self.ledger, scope, api)
        self.journal.checkpoint = self.jpoint
        self.service = AnchoredReviewHandoff(self.authority, self.target, self.ledger, self.journal, clock=lambda: self.now, checkpoint=self.point)
        self.fault = None
        self.saved = {}
        self.recovered_without_renewal = False
        self.parent_preserved = False

    def jpoint(self, name):
        if self.fault == name:
            self.fault = None
            raise ValueError("Invented interrupted review commit")

    def point(self, name):
        self.jpoint(name)

    async def prepare(self, client):
        response = await self.request(client, "prepare", "preparer", {"request_id": self.request_id, "packet_sha256": self.packet_sha, "observation_sha256": self.observation_sha})
        if response.status_code != 200:
            raise ValueError("Frozen preparation rejected")
        self.handoff = response.json()

    async def decide(self, client, *, ident=None, handoff=None, choice="accept"):
        response = await self.request(client, "decide", "reviewer", {"handoff_id": ident or self.request_id,
                                      "handoff_sha256": (handoff or self.handoff)["handoff_sha256"], "decision": choice, "reason_code": DECISIONS[choice]})
        if response.status_code == 200:
            self.decision = response.json()
        return response

    async def inspect(self, client, ident, hsha, dsha, expected):
        response = await self.request(client, "inspect", "preparer", {"handoff_id": ident, "handoff_sha256": hsha, "decision_sha256": dsha})
        if response.status_code != 200 or response.json()["status"] != expected:
            raise ValueError("Exact historical inspection failed")
        return response

    async def recover(self, client, *, repair=True, role="preparer", wrong=False, headers=None):
        observed = await self.request(client, "recover", role, {"expected": None, "repair": False}, headers=headers)
        if observed.status_code != 200 or not repair:
            return observed
        value = observed.json()
        expected = {k: value[k] for k in ("anchor_head_sha256", "journal_tip_sha256")}
        if wrong:
            expected["journal_tip_sha256"] = "0" * 64
        return await self.request(client, "recover", role, {"expected": expected, "repair": True})

    def backup(self, name):
        destination = self.work / (name + ".sqlite")
        with sqlite3.connect(self.journal.path) as original, sqlite3.connect(destination) as target:
            original.backup(target)
        destination.chmod(0o600)
        return destination

    def remember(self):
        self.saved = {p.name: p.read_bytes() for p in self.ledger.iterdir()}

    def preserved(self):
        if any((self.ledger / n).read_bytes() != raw for n, raw in self.saved.items()):
            raise ValueError("Retained parent history changed")
        self.parent_preserved = True

    def renew_target(self):
        packet = e.decode(e.read(self.packet_path))
        packet.update(packet_id=e.sha((self.name + "-fresh-packet").encode())[:32], created_at=self.now, expires_at=self.now + 900)
        self.packet_path = self.work / "fresh-packet.json"
        self.packet_sha = e.retain(self.packet_path, e.encode(packet))["sha256"]
        self.observation_path = self.work / "fresh-observation.json"
        obs = e.reconcile(self.packet_path, self.packet_sha, self.target.stage, self.base.model, self.base.journal,
                          self.base.binding, self.base.trust, api=self.api, clock=lambda: self.now)
        self.observation_sha = e.retain(self.observation_path, e.encode(obs))["sha256"]
        self.target = replace(self.target, packet_path=self.packet_path, packet_sha256=self.packet_sha,
                              observation_path=self.observation_path, observation_sha256=self.observation_sha)
        if not isinstance(self.target, Target):
            raise ValueError("Frozen target lost")
        self.service.target = self.target

    async def run(self, client):
        number = int(self.name[1:3])
        await self.prepare(client)
        old_db = self.backup("pre-decision")
        old_anchor = self.journal.anchor.path.read_bytes()
        if number == 19:
            return (await self.request(client, "rereview", "preparer", self.fresh_body("0" * 64))).status_code
        self.fault = {2: "after_commit", 3: "committed_unanchored", 4: "anchored", 9: "committed_unanchored",
                      10: "committed_unanchored", 11: "committed_unanchored", 12: "committed_unanchored",
                      13: "committed_unanchored", 14: "committed_unanchored", 28: "before_db_commit",
                      31: "committed_unanchored"}.get(number)
        response = await self.decide(client, choice="changes_required" if number == 23 else "accept")
        if self.fault:
            raise ValueError("Frozen interruption was not reached")
        if number in {2, 3, 4, 9, 10, 11, 12, 13, 14, 28, 31} and response.status_code != 400:
            raise ValueError("Interrupted commit was acknowledged")
        if number == 6:
            with sqlite3.connect(old_db) as backup, sqlite3.connect(self.journal.path) as target:
                backup.backup(target)
        if number == 7:
            self.journal.anchor.path.write_bytes(old_anchor)
            denied = await self.request(client, "inspect", "preparer", {"handoff_id": self.request_id, "handoff_sha256": self.handoff["handoff_sha256"], "decision_sha256": self.decision["decision_sha256"]})
            if denied.status_code != 400:
                raise ValueError("Anchor changed without an explicit pin")
        if number == 9:
            with sqlite3.connect(self.journal.path) as db:
                rows = [list(r) for r in db.execute("SELECT seq,name,raw,parent FROM records ORDER BY seq")]
                forged = e.decode(rows[-1][2].encode())
                forged.update(decision="reject", reason_code=DECISIONS["reject"])
                rows[-1][2] = e.encode(forged).decode()
                previous = e.decode(db.execute("SELECT frame FROM audit WHERE seq=1").fetchone()[0].encode())["head"]
                new = frame(self.journal.identity, 2, previous, rows)
                db.execute("UPDATE records SET raw=? WHERE seq=2", (rows[-1][2],))
                db.execute("UPDATE audit SET frame=? WHERE seq=2", (e.encode(new).decode(),))
        if number == 10:
            path = self.base.trust / "candidate.json"
            path.write_bytes(path.read_bytes() + b" ")
        if number == 11:
            self.revoke("reviewer")
        if number in {5, 15}:
            (self.ledger / (self.request_id + ".decision.json")).unlink()
        if number == 15:
            self.fault = "recovered"
        if number == 26:
            path = self.ledger / (self.request_id + ".decision.json")
            path.write_bytes(path.read_bytes() + b" ")
        if number == 31:
            notes = sorted(self.journal.anchor.path.parent.glob("*.intent.json"))
            for path in notes:
                value = e.decode(path.read_bytes())
                if value["seq"] == 2:
                    path.unlink()
        if number in {2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 26, 27, 28, 30, 31}:
            self.remember()
            if number == 30:
                self.now += 901
            before = self.journal.anchor.path.read_bytes()
            headers = self.headers("preparer") if number == 27 else None
            if headers:
                headers.pop("x-csrf-token")
            role = "reviewer" if number == 11 else "other" if number == 12 else "preparer"
            result = await self.recover(client, repair=number != 14, role=role, wrong=number == 13, headers=headers)
            self.preserved()
            if number == 14 and before != self.journal.anchor.path.read_bytes():
                raise ValueError("Observation mutated the independent anchor")
            if result.status_code == 200 and number not in {14, 28}:
                raw = e.read(self.ledger / (self.request_id + ".decision.json"))
                await self.inspect(client, self.request_id, self.handoff["handoff_sha256"], e.sha(raw),
                                   "stale_review_retained" if number in {10, 30} else "reviewed_for_disposable_handoff")
                self.recovered_without_renewal = True
            if number == 28 and (result.json()["records"] != 1 or any(self.ledger.glob("*.decision.json"))):
                raise ValueError("Uncommitted intent invented a decision")
            if number == 2:
                return response.status_code
            return result.status_code
        if number == 1:
            return (await self.inspect(client, self.request_id, self.handoff["handoff_sha256"], self.decision["decision_sha256"], "reviewed_for_disposable_handoff")).status_code
        self.remember()
        if number == 17:
            for role in ("preparer", "reviewer"):
                self.revoke(role)
                self.login(role)
            self.now += 301
            self.renew_target()
        if number == 29:
            for role in ("preparer", "reviewer"):
                self.revise_role(role)
        fresh = self.fresh_body(self.decision["decision_sha256"])
        if number == 18:
            fresh["parent"]["decision_sha256"] = "0" * 64
        if number == 20:
            fresh["request_id"] = self.request_id
        if number == 25:
            values = await asyncio.gather(self.request(client, "rereview", "preparer", fresh), self.request(client, "rereview", "preparer", fresh))
            if sorted(r.status_code for r in values) != [200, 409]:
                raise ValueError("Competing re-review replaced a handoff")
            self.preserved()
            return 409
        new = await self.request(client, "rereview", "preparer", fresh)
        if new.status_code != 200:
            self.preserved()
            return new.status_code
        if new.json()["status"] != "fresh_independent_review_required" or len(list(self.ledger.glob("*.decision.json"))) != 1:
            raise ValueError("Previous decision was silently carried forward")
        if number == 21:
            result = await self.request(client, "rereview", "preparer", fresh)
        elif number == 22:
            result = new
        else:
            if number == 24:
                self.revise_role("reviewer")
            result = await self.decide(client, ident=fresh["request_id"], handoff=new.json())
            if result.status_code == 200:
                inspected = await self.inspect(client, fresh["request_id"], new.json()["handoff_sha256"], result.json()["decision_sha256"], "reviewed_for_disposable_handoff")
                if inspected.json()["parent"] != fresh["parent"]:
                    raise ValueError("Exact parent lineage lost")
        self.preserved()
        if number == 8:
            self.journal.anchor.path.write_bytes(old_anchor)
            return (await self.recover(client)).status_code
        return result.status_code

    def fresh_body(self, dsha):
        return {"parent": {"handoff_id": self.request_id, "handoff_sha256": self.handoff["handoff_sha256"], "decision_sha256": dsha},
                "request_id": e.sha((self.name + "-new-review").encode())[:32], "packet_sha256": self.packet_sha, "observation_sha256": self.observation_sha}

    def result(self, status):
        self.preserved()
        result = super().result(status)
        raw = self.journal.path.read_bytes() + b"".join(p.read_bytes() for p in self.journal.anchor.path.parent.iterdir())
        if any(v.encode() in raw for v in [*self.passwords.values(), *self.cookies.values(), *self.csrf.values()]):
            raise ValueError("Disposable credential leaked into anchored storage")
        result.update(independent_anchor=True, original_records_not_rewritten_by_recovery=self.parent_preserved,
                      recovery_is_not_new_review=True, fresh_review_requires_new_decision=True)
        return result
