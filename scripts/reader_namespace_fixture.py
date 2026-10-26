"""Frozen invented namespace handoff; exact old/new records remain separate."""

import asyncio
import hashlib

import operator_enrollment_evidence as e
import operator_review_fixture as raw
import reader_lifecycle_fixture as retained
import staged_reader_fixture as old
from authenticated_operator_review import PREFIX
from reader_namespace import ReaderNamespace
from reader_namespace_log import NamespaceLog, scope_for
from staged_reader import StagedReader
from staged_reader_log import ReaderLog

CASES = [("N01_reviewed_transition", 200), ("N02_self_review", 409), ("N03_denied_transition", 409),
         ("N04_legacy_advanced", 409), ("N05_destination_advanced", 409), ("N06_canonical_withdrawal", 409),
         ("N07_legacy_tampered", 400), ("N08_destination_tampered", 400), ("N09_lost_commit_reply", 200),
         ("N10_unanchored_commit", 200), ("N11_missing_admission", 400), ("N12_competing_commits", 409),
         ("N13_expired_transition", 409), ("N14_revoked_reviewer", 403), ("N15_old_cursor", 409),
         ("N16_no_namespace_bypass", 409), ("N17_wrong_subject_pin", 409), ("N18_readonly_lineage", 200),
         ("N19_retired_destination", 409), ("N20_preserved_retirement_lineage", 200)]
POLICY = {"schema": "reader-namespace-qualification-v1", "cases": [dict(id=n, expected=v) for n, v in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_events": 256, "max_transition_seconds": 300,
          "max_page_rows": 8, "both_reader_histories_unchanged_by_transition": True, "fresh_independent_transition_review": True,
          "canonical_fence_on_every_read": True, "disposable_accounts_only": True, "model_verification_seconds": 20,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}


class PrefixClient:
    def __init__(self, client, namespace):
        self.client, self.namespace = client, namespace

    async def post(self, path, **kwargs):
        if path.startswith(PREFIX + "reader_"):
            path = PREFIX + self.namespace + "_" + path[len(PREFIX):]
        return await self.client.post(path, **kwargs)


class Fixture(retained.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        root, anchor = self.work / "reader-controls", self.base.anchors / "reader-anchor/reader.anchor"
        metadata = e.decode(e.read(root / "metadata.json"))
        self.legacy_controls = ReaderLog(root, anchor, metadata["scope"], metadata["control_id"], api)
        left = [StagedReader(v.inner, self.legacy_controls, clock=lambda: self.now) for v in self.services]
        root, anchor = self.work / "namespace-transition", self.base.anchors / "namespace-transition-anchor"
        root.mkdir(mode=0o700)
        anchor.mkdir(mode=0o700)
        self.transition_controls = NamespaceLog.create(root, anchor / "transition.anchor", scope_for(left[0], self.services[0], root), api)
        self.namespace_fault = None
        self.transition_controls.checkpoint = self.transitionpoint
        self.services = [ReaderNamespace(a, b, self.transition_controls, clock=lambda: self.now, checkpoint=self.newpoint) for a, b in zip(left, self.services, strict=True)]
        self.namespace = "legacy"
        self.transition_id = e.sha((name + "-transition").encode())[:32]
        self.transition_pin = self.transition_proposal = self.transition_decision = self.transition_commit = None
        self.history_checks = 0

    def transitionpoint(self, name):
        if self.namespace_fault == name:
            self.namespace_fault = None
            raise ValueError("Invented interrupted namespace transition")

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        n = int(self.name[1:3])
        value.update(fault="namespace_committed_complete" if n == 9 and node == 0 else None,
                     reader_fault=None, namespace_fault="committed_retained" if n == 10 and node == 0 else None,
                     legacy_reader_root=str(self.legacy_controls.root), legacy_reader_anchor=str(self.legacy_controls.anchor.path),
                     legacy_reader_id=self.legacy_controls.identity, legacy_reader_scope=self.legacy_controls.scope,
                     transition_root=str(self.transition_controls.root), transition_anchor=str(self.transition_controls.anchor.path),
                     transition_control_id=self.transition_controls.identity, transition_scope=self.transition_controls.scope)
        return value

    async def request(self, client, action, role, body, **kwargs):
        if action in StagedReader.management or action == "reader_retire":
            client = PrefixClient(client, self.namespace)
            if self.namespace == "legacy":
                return await old.Fixture.request(self, client, action, role, body, **kwargs)
        return await super().request(client, action, role, body, **kwargs)

    def namespace_files(self):
        result = {}
        for name, controls in (("legacy", self.legacy_controls), ("destination", self.reader_controls)):
            for p in [*controls.root.iterdir(), *controls.anchor.path.parent.iterdir()]:
                if p.is_file():
                    result[name + "/" + str(p.relative_to(controls.root) if p.is_relative_to(controls.root) else p.name)] = hashlib.sha256(p.read_bytes()).hexdigest()
        return result

    async def transition_request(self, client, action, role, body):
        value = dict(body)
        if action not in {"transition_observe", "transition_status", "transition_recover"}:
            value.update({"expected_" + k: self.transition_pin[k] for k in ("transition_head_sha256", "subject_sha256")})
        if action == "transition_prepare" and self.name.startswith("N17_"):
            value["expected_subject_sha256"] = "0" * 64
        before = self.namespace_files()
        result = await raw.Fixture.request(self, client, action, role, value)
        if self.namespace_files() != before:
            raise ValueError("Transition rewrote an existing reader namespace")
        self.history_checks += 1
        if result.status_code == 200:
            response = result.json()
            if action == "transition_observe":
                self.transition_pin = response
            elif "transition_head_sha256" in response and self.transition_pin:
                self.transition_pin["transition_head_sha256"] = response["transition_head_sha256"]
        return result

    async def prepare_transition(self, client):
        result = await self.transition_request(client, "transition_observe", "preparer", {})
        if result.status_code != 200:
            raise ValueError("Invented transition observation rejected")
        result = await self.transition_request(client, "transition_prepare", "preparer", {"transition_id": self.transition_id})
        if result.status_code == 200:
            self.transition_proposal = result.json()
        return result

    async def decide_transition(self, client, *, role="reviewer", denied=False):
        result = await self.transition_request(client, "transition_decide", role, {"transition_id": self.transition_id,
            "proposal_sha256": self.transition_proposal["proposal_sha256"], "decision": "deny" if denied else "approve",
            "reason_code": "transition_declined" if denied else "exact_reader_transition_checked"})
        if result.status_code == 200:
            self.transition_decision = result.json()
        return result

    async def commit_transition(self, client):
        result = await self.transition_request(client, "transition_commit", "preparer", {"transition_id": self.transition_id,
                                               "decision_sha256": self.transition_decision["decision_sha256"]})
        if result.status_code == 200:
            self.transition_commit = result.json()
        return result

    async def transition_status(self, client):
        result = await self.transition_request(client, "transition_status", "preparer", {"transition_id": self.transition_id, "decision_sha256": None, "commit_sha256": None})
        if result.status_code != 200:
            return result
        return await self.transition_request(client, "transition_status", "preparer", {"transition_id": self.transition_id,
            **{k:result.json()[k] for k in ("decision_sha256", "commit_sha256")}})

    async def inventory(self, client, *, previous=None):
        value = {"commit_sha256": self.transition_commit["commit_sha256"], "snapshot_sha256": None, "offset": 0, "limit": 1, "cursor": None}
        if previous:
            value.update(snapshot_sha256=previous["snapshot_sha256"], offset=previous["next_offset"], cursor=previous["next_cursor"])
        return await self.transition_request(client, "transition_inventory", "preparer", value)

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.seed(a, b)
        await self.stage(a)
        await self.bind(a, b)
        self.legacy_selection = dict(self.reader_selection)
        old_page = (await self.view(a, limit=1)).json()
        self.namespace, self.mode = "destination", "initial"
        await self.next_stage(a, "-destination")
        await self.bind(a, b)
        # Destination is not usable before the transition's independent review.
        if (await self.view(a)).status_code != 409:
            raise ValueError("Destination bypassed transition review")
        if n in {19, 20}:
            if (await self.retire(a)).status_code != 200:
                raise ValueError("Destination retirement setup rejected")
            if n == 19:
                return (await self.transition_request(a, "transition_observe", "preparer", {})).status_code
            self.mode = "renewal"
            await self.next_stage(a, "-renewed-destination")
            await self.bind(a, b)
        result = await self.prepare_transition(a)
        if n == 17:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Transition preparation rejected")
        if n in {4, 5}:
            self.namespace, self.mode = ("legacy", "initial") if n == 4 else ("destination", "renewal")
            self.reader_id = e.sha((self.name + "-pending-reader").encode())[:32]
            if (await self.prepare_reader(a)).status_code != 200:
                raise ValueError("Concurrent namespace advance rejected")
            if (await self.transition_request(a, "transition_observe", "preparer", {})).status_code != 200:
                raise ValueError("Advanced namespace observation rejected")
        result = await self.decide_transition(b, role="preparer" if n == 2 else "reviewer", denied=n == 3)
        if n in {2, 4, 5}:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Independent transition decision rejected")
        if n == 13:
            self.advance(301)
        if n == 14:
            self.revoke("reviewer")
        if n in {7, 8}:
            controls = self.legacy_controls if n == 7 else self.reader_controls
            p = controls.root / "metadata.json"
            p.write_bytes(p.read_bytes() + b"changed")
        if n == 9:
            self.backup_fault = "namespace_committed_complete"
        if n == 10:
            self.namespace_fault = "committed_retained"
        if n == 12:
            replies = await asyncio.gather(self.commit_transition(a), self.commit_transition(b))
            if sorted(v.status_code for v in replies) != [200, 409]:
                raise ValueError("Namespace transition committed twice")
            return 409
        result = await self.commit_transition(a)
        if n in {3, 7, 8, 13, 14}:
            return result.status_code
        if n in {9, 10}:
            if result.status_code != 400:
                raise ValueError("Commit interruption was not injected")
            if n == 10:
                if (await self.transition_request(b, "transition_observe", "reviewer", {})).status_code != 400:
                    raise ValueError("Unanchored transition admitted reads")
                result = await self.transition_request(b, "transition_recover", "reviewer", {"repair": False, "expected_head_sha256": None, "expected_tip_sha256": None})
                pins = result.json()
                result = await self.transition_request(b, "transition_recover", "reviewer", {"repair": True, "expected_head_sha256": pins["transition_head_sha256"], "expected_tip_sha256": pins["transition_tip_sha256"]})
                if result.status_code != 200:
                    raise ValueError("Exact transition recovery rejected")
            status = await self.transition_status(a)
            if status.status_code != 200 or not status.json()["usable"]:
                raise ValueError("Lost-reply reconciliation did not retain exact commit")
            self.transition_commit = status.json()
            if (await self.transition_request(a, "transition_observe", "preparer", {})).status_code != 200:
                raise ValueError("Transition context did not reconcile")
        elif result.status_code != 200:
            raise ValueError("Transition commit rejected")
        if n == 11:
            event = e.decode(e.read(self.transition_controls.root / "0003.json"))
            (self.transition_controls.anchor.path.parent / (event["head"] + ".intent.json")).unlink()
            return (await self.transition_request(a, "transition_observe", "preparer", {})).status_code
        if n == 6:
            await self.withdrawal(a, b)
            if (await self.transition_status(a)).json()["usable"]:
                raise ValueError("Canonical withdrawal retained transition authority")
            return (await self.inventory(a)).status_code
        if n == 15:
            return (await self.inventory(a, previous=old_page)).status_code
        if n == 16:
            for namespace in ("legacy", "destination"):
                self.namespace = namespace
                if (await self.view(a)).status_code != 409:
                    raise ValueError("Namespace bypass or fallback remained available")
            if (await self.inventory(a)).status_code != 200:
                raise ValueError("Reviewed destination was not usable")
            return 409
        if n == 18:
            before = self.preserved_files()
            result = await self.transition_status(b)
            if result.status_code != 200 or not result.json()["usable"] or before != self.preserved_files():
                raise ValueError("Readonly transition lineage changed evidence")
        return (await self.inventory(a)).status_code

    def result(self, status):
        value = super().result(status)
        payload = b"".join(p.read_bytes() for p in self.transition_controls.root.iterdir())
        if any(v.encode() in payload for v in [*self.passwords.values(), *self.cookies.values(), *self.csrf.values()]):
            raise ValueError("Credentials appeared in namespace transition history")
        value.update(transition_events=len(list(self.transition_controls.root.glob("[0-9a-f]*.json"))),
                     legacy_reader_events=len(list(self.legacy_controls.root.glob("[0-9a-f]*.json"))),
                     both_reader_histories_unchanged_by_transition=self.history_checks > 0,
                     fresh_independent_transition_review=True, no_automatic_namespace_fallback=True,
                     transition_does_not_reactivate_old_approvals=True)
        return value
