"""Frozen invented identities for independently selected staged metadata reads."""

import asyncio

import operator_enrollment_evidence as e
import operator_review_fixture as raw
import withdrawal_backup_fixture as retained
from staged_reader import StagedReader
from staged_reader_log import ReaderLog, scope_for

CASES = [("B01_approved_read", 200), ("B02_self_review", 409), ("B03_denied_selection", 409),
         ("B04_wrong_stage_pin", 400), ("B05_source_advanced", 409), ("B06_changed_preparer_role", 403),
         ("B07_expired_proposal", 409), ("B08_selection_replay", 409), ("B09_selection_race", 409),
         ("B10_lost_selection_reply", 200), ("B11_unanchored_selection", 200), ("B12_stage_tampered", 400),
         ("B13_canonical_withdrawal", 409), ("B14_superseded_selection", 200), ("B15_cross_selection_cursor", 409),
         ("B16_revoked_reviewer_session", 403), ("B17_unassigned_and_csrf", 400), ("B18_missing_admission_intent", 400),
         ("B19_retained_expired_status", 200), ("B20_fresh_post_withdrawal_review", 200)]
POLICY = {"schema": "staged-reader-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_events": 256,
          "max_proposal_seconds": 300, "max_page_rows": 8, "canonical_fence_on_every_read": True,
          "disposable_accounts_only": True, "model_verification_seconds": 20, "live_provider_requests": 0,
          "native_inference_calls": 0, "real_trust_enrolled": False, "runtime_installation": False, "production_activation": False}


class Fixture(retained.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        root, anchor = self.work / "reader-controls", self.base.anchors / "reader-anchor"
        root.mkdir(mode=0o700)
        anchor.mkdir(mode=0o700)
        self.reader_controls = ReaderLog.create(root, anchor / "reader.anchor", scope_for(self.services[0], root), api)
        self.reader_controls.checkpoint = self.readerpoint
        self.binding_fault = None
        self.services = [StagedReader(s, self.reader_controls, clock=lambda: self.now, checkpoint=self.newpoint) for s in self.services]
        self.reader_id = e.sha((name + "-reader").encode())[:32]
        self.reader_pin = self.reader_proposal = self.reader_decision = self.reader_selection = None

    def readerpoint(self, name):
        if self.binding_fault == name:
            self.binding_fault = None
            raise ValueError("Invented interrupted reader control")

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        value.update(fault="reader_selected_complete" if self.name.startswith("B10_") and node == 0 else None,
                     control_fault=None, journal_fault=False,
                     reader_fault="selected_retained" if self.name.startswith("B11_") and node == 0 else None,
                     reader_root=str(self.reader_controls.root), reader_anchor=str(self.reader_controls.anchor.path),
                     reader_id=self.reader_controls.identity, reader_scope=self.reader_controls.scope)
        return value

    async def request(self, client, action, role, body, **kwargs):
        if action not in StagedReader.management:
            return await super().request(client, action, role, body, **kwargs)
        value = dict(body)
        if action not in {"reader_observe", "reader_recover"}:
            value.update({"expected_" + key: self.reader_pin[key] for key in ("binding_head_sha256", "revocation_head_sha256", "context_sha256")})
        result = await raw.Fixture.request(self, client, action, role, value, **kwargs)
        if result.status_code == 200:
            response = result.json()
            if action == "reader_observe":
                self.reader_pin = response
            elif "binding_head_sha256" in response and self.reader_pin:
                self.reader_pin["binding_head_sha256"] = response["binding_head_sha256"]
        return result

    async def observe(self, client):
        return await self.request(client, "reader_observe", "preparer", {})

    async def stage(self, client):
        if (await self.snapshot(client)).status_code != 200 or (await self.archive(client)).status_code != 200:
            raise ValueError("Invented archive setup rejected")
        result = await self.restore_archive(client)
        if result.status_code != 200:
            raise ValueError("Invented staged journal rejected")
        self.stage_pins = result.json()

    async def prepare_reader(self, client, *, wrong=False):
        if (await self.observe(client)).status_code != 200:
            raise ValueError("Invented reader observation rejected")
        result = await self.request(client, "reader_prepare", "preparer", {"proposal_id": self.reader_id,
                                    "stage_id": self.archive_restore_id, "intent_sha256": "0" * 64 if wrong else self.stage_pins["intent_sha256"],
                                    "receipt_sha256": self.stage_pins["receipt_sha256"]})
        if result.status_code == 200:
            self.reader_proposal = result.json()
        return result

    async def decide_reader(self, client, *, role="reviewer", denied=False):
        result = await self.request(client, "reader_decide", role, {"proposal_id": self.reader_id,
                                    "proposal_sha256": self.reader_proposal["proposal_sha256"], "decision": "deny" if denied else "approve",
                                    "reason_code": "reader_declined" if denied else "exact_reader_scope_checked"})
        if result.status_code == 200:
            self.reader_decision = result.json()
        return result

    async def select_reader(self, client):
        result = await self.request(client, "reader_select", "preparer", {"proposal_id": self.reader_id, "decision_sha256": self.reader_decision["decision_sha256"]})
        if result.status_code == 200:
            self.reader_selection = result.json()
        return result

    async def bind(self, a, b):
        for operation, client in ((self.prepare_reader, a), (self.decide_reader, b), (self.select_reader, a)):
            result = await operation(client)
            if result.status_code != 200:
                raise ValueError("Invented independent binding rejected")

    async def view(self, client, *, previous=None, selection=None, limit=8):
        value = {"selection_sha256": (selection or self.reader_selection)["selection_sha256"], "snapshot_sha256": None,
                 "offset": 0, "limit": limit, "cursor": None}
        if previous:
            value.update(snapshot_sha256=previous["snapshot_sha256"], offset=previous["next_offset"], cursor=previous["next_cursor"])
        return await self.request(client, "reader_inventory", "preparer", value)

    async def status(self, client):
        result = await self.request(client, "reader_status", "preparer", {"proposal_id": self.reader_id, "decision_sha256": None, "selection_sha256": None})
        if result.status_code != 200:
            return result
        observed = result.json()
        return await self.request(client, "reader_status", "preparer", {"proposal_id": self.reader_id,
                                  "decision_sha256": observed["decision_sha256"], "selection_sha256": observed["selection_sha256"]})

    def advance(self, seconds):
        self.now += seconds
        self.clock_path.write_bytes(e.encode({"now": self.now}))

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.seed(a, b)
        await self.stage(a)
        if n == 17:
            self.login("other")
            if (await self.request(b, "reader_observe", "other", {})).status_code != 403:
                raise ValueError("Unassigned reader admitted")
            headers = self.headers("preparer")
            headers.pop("x-csrf-token")
            return (await self.request(a, "reader_observe", "preparer", {}, headers=headers)).status_code
        result = await self.prepare_reader(a, wrong=n == 4)
        if n == 4:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Reader proposal setup rejected")
        if n == 5:
            await self.withdrawal(a, b)
            await self.observe(a)
        if n == 6:
            self.revise_role("preparer")
        if n == 7:
            self.advance(301)
            await self.observe(a)
        result = await self.decide_reader(b, role="preparer" if n == 2 else "reviewer", denied=n == 3)
        if n in {2, 5, 6, 7}:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Reader decision setup rejected")
        if n == 9:
            replies = await asyncio.gather(self.select_reader(a), self.select_reader(b))
            if sorted(r.status_code for r in replies) != [200, 409]:
                raise ValueError("Competing reader selections both committed")
            return 409
        if n == 10:
            self.backup_fault = "reader_selected_complete"
        if n == 11:
            self.binding_fault = "selected_retained"
        selected = await self.select_reader(a)
        if n == 3:
            return selected.status_code
        if n in {10, 11}:
            if selected.status_code != 400:
                raise ValueError("Selection interruption was not injected")
            if n == 11:
                if (await self.observe(a)).status_code != 400:
                    raise ValueError("Unanchored reader became usable")
                result = await self.request(b, "reader_recover", "reviewer", {"repair": False, "expected_head_sha256": None, "expected_tip_sha256": None})
                if result.status_code != 200:
                    raise ValueError("Reader recovery observation rejected")
                value = result.json()
                result = await self.request(b, "reader_recover", "reviewer", {"repair": True, "expected_head_sha256": value["binding_head_sha256"], "expected_tip_sha256": value["binding_tip_sha256"]})
                if result.status_code != 200:
                    raise ValueError("Pinned reader repair rejected")
            await self.observe(a)
            before = self.preserved_files()
            result = await self.status(a)
            if result.status_code != 200 or not result.json()["usable"] or before != self.preserved_files():
                raise ValueError("Read-only lost-reply reconciliation changed history")
            self.reader_selection = result.json()
        elif selected.status_code != 200:
            raise ValueError("Reader selection setup rejected")
        if n == 8:
            return (await self.select_reader(a)).status_code
        if n == 12:
            path = self.archive_restores / self.archive_restore_id / "journal/metadata.json"
            path.write_bytes(path.read_bytes() + b"changed")
        if n == 16:
            self.revoke("reviewer")
        if n == 18:
            event = e.decode(e.read(self.reader_controls.root / "0003.json"))
            (self.reader_controls.anchor.path.parent / (event["head"] + ".intent.json")).unlink()
            return (await self.observe(a)).status_code
        if n in {13, 20}:
            await self.withdrawal(a, b)
            await self.observe(a)
            stale = await self.view(a)
            if stale.status_code != 409 or (await self.selected(b)).status_code != 409:
                raise ValueError("Canonical withdrawal did not fence staged/ordinary readers")
            if n == 13:
                return stale.status_code
            self.archive_id, self.archive_restore_id = [e.sha((self.name + suffix).encode())[:32] for suffix in ("-fresh-backup", "-fresh-stage")]
            await self.stage(a)
            self.reader_id = e.sha((self.name + "-fresh-reader").encode())[:32]
            await self.bind(a, b)
            result = await self.view(a)
            if result.status_code != 200 or not any(row["access_withdrawn"] for row in result.json()["rows"]):
                raise ValueError("Fresh metadata reader lost withdrawal evidence")
            if (await self.selected(b)).status_code != 409:
                raise ValueError("Fresh metadata binding reactivated an ordinary reader")
            return result.status_code
        if n == 19:
            self.advance(301)
            await self.observe(a)
            before = self.preserved_files()
            result = await self.status(a)
            if result.status_code != 200 or result.json()["usable"] or (await self.view(a)).status_code != 409 or before != self.preserved_files():
                raise ValueError("Historical status renewed an expired binding")
            return result.status_code
        if n in {14, 15}:
            old_id, old_selection = self.reader_id, dict(self.reader_selection)
            previous = (await self.view(a, limit=1)).json()
            self.reader_id = e.sha((self.name + "-successor-reader").encode())[:32]
            await self.bind(a, b)
            if n == 15:
                return (await self.view(a, previous=previous, limit=1)).status_code
            if (await self.view(a, selection=old_selection)).status_code != 409:
                raise ValueError("Superseded reader remained usable")
            current_id = self.reader_id
            self.reader_id = old_id
            result = await self.status(a)
            self.reader_id = current_id
            if result.status_code != 200 or result.json()["active"] or result.json()["usable"]:
                raise ValueError("Superseded exact status lost its history")
        before = self.preserved_files()
        result = await self.view(a)
        if before != self.preserved_files():
            raise ValueError("Staged reader changed retained files")
        return result.status_code

    def result(self, status):
        result = super().result(status)
        payload = b"".join(p.read_bytes() for p in self.reader_controls.root.iterdir())
        if any(v.encode() in payload for v in [*self.passwords.values(), *self.cookies.values(), *self.csrf.values()]):
            raise ValueError("Credentials appeared in reader control history")
        result.update(reader_events=len(list(self.reader_controls.root.glob("[0-9a-f]*.json"))),
                      canonical_fence_on_every_read=True, ordinary_writes_use_original_journal=True,
                      reader_selection_is_not_runtime_activation=True, independent_reader_controls_external=True)
        return result
