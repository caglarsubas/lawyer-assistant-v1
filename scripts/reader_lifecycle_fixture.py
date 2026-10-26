"""Invented retirement and fresh-review succession; no real identities or cases."""

import asyncio

import operator_enrollment_evidence as e
import operator_review_fixture as raw
import staged_reader_fixture as retained
from reader_lifecycle import ReaderLifecycle
from reader_lifecycle_log import ReaderLifecycleLog
from staged_reader_log import scope_for

CASES = [("C01_retirement_blocks", 200), ("C02_expired_retired_renewal", 200), ("C03_fresh_rollback", 200),
         ("C04_old_decision_reuse", 409), ("C05_self_review", 409), ("C06_denied_renewal", 409),
         ("C07_wrong_predecessor", 400), ("C08_withdrawal_pending_rollback", 409), ("C09_retired_old_read", 409),
         ("C10_retirement_race", 409), ("C11_lost_retirement_reply", 200), ("C12_unanchored_retirement", 200),
         ("C13_missing_retirement_intent", 400), ("C14_superseded_retirement", 409), ("C15_expired_renewal", 409),
         ("C16_revoked_reviewer", 403), ("C17_cross_renewal_cursor", 409), ("C18_source_changed", 409),
         ("C19_stage_tampered", 400), ("C20_initial_mode_bypass", 400), ("C21_unknown_rollback_target", 400),
         ("C22_post_withdrawal_renewal", 200)]
POLICY = {"schema": "reader-lifecycle-qualification-v1", "cases": [dict(id=n, expected=v) for n, v in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_events": 256, "max_proposal_seconds": 300,
          "max_page_rows": 8, "retirement_permanent_per_selection": True, "fresh_independent_decision_for_succession": True,
          "canonical_fence_on_every_read": True, "disposable_accounts_only": True, "model_verification_seconds": 20,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}


class Fixture(retained.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        root, anchor = self.work / "reader-lifecycle", self.base.anchors / "reader-lifecycle-anchor"
        root.mkdir(mode=0o700)
        anchor.mkdir(mode=0o700)
        self.reader_controls = ReaderLifecycleLog.create(root, anchor / "reader.anchor", scope_for(self.services[0].inner, root), api)
        self.reader_controls.checkpoint = self.readerpoint
        self.services = [ReaderLifecycle(v.inner, self.reader_controls, clock=lambda: self.now, checkpoint=self.newpoint) for v in self.services]
        self.mode, self.target_selection = "initial", None

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        n = int(self.name[1:3])
        value.update(fault="reader_retired_complete" if n == 11 and node == 0 else None,
                     reader_fault="retired_retained" if n == 12 and node == 0 else None)
        return value

    async def request(self, client, action, role, body, **kwargs):
        if action not in ReaderLifecycle.management:
            return await super().request(client, action, role, body, **kwargs)
        value = dict(body)
        if action not in {"reader_observe", "reader_recover"}:
            value.update({"expected_" + key: self.reader_pin[key] for key in ("binding_head_sha256", "revocation_head_sha256", "context_sha256")})
        if action == "reader_prepare":
            value.update(mode=self.mode, predecessor_sha256=self.reader_pin["last_selection_sha256"],
                         retirement_sha256=self.reader_pin["retirement_sha256"], target_selection_sha256=self.target_selection)
            if self.name.startswith("C07_") and self.mode != "initial":
                value["predecessor_sha256"] = "0" * 64
        result = await raw.Fixture.request(self, client, action, role, value, **kwargs)
        if result.status_code == 200:
            response = result.json()
            if action == "reader_observe":
                self.reader_pin = response
            elif "binding_head_sha256" in response and self.reader_pin:
                self.reader_pin["binding_head_sha256"] = response["binding_head_sha256"]
        return result

    async def retire(self, client):
        return await self.request(client, "reader_retire", "preparer", {"proposal_id": self.reader_id,
                                  "selection_sha256": self.reader_selection["selection_sha256"], "reason_code": "reader_retired"})

    async def next_stage(self, client, suffix):
        self.archive_id, self.archive_restore_id = [e.sha((self.name + suffix + kind).encode())[:32] for kind in ("-backup", "-stage")]
        await self.stage(client)
        self.reader_id = e.sha((self.name + suffix + "-reader").encode())[:32]

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.seed(a, b)
        await self.stage(a)
        await self.bind(a, b)
        first_id, first_selection, first_decision = self.reader_id, dict(self.reader_selection), dict(self.reader_decision)
        previous = (await self.view(a, limit=1)).json()
        if n in {1, 2, 4, 9, 10, 11, 12, 13}:
            if n == 2:
                self.advance(301)
                await self.observe(a)
            if n == 10:
                results = await asyncio.gather(self.retire(a), self.retire(b))
                if sorted(v.status_code for v in results) != [200, 409]:
                    raise ValueError("Competing retirement committed twice")
                return 409
            if n == 11:
                self.backup_fault = "reader_retired_complete"
            if n == 12:
                self.binding_fault = "retired_retained"
            result = await self.retire(a)
            if n in {11, 12}:
                if result.status_code != 400:
                    raise ValueError("Retirement failure was not injected")
                if n == 12:
                    if (await self.observe(b)).status_code != 400:
                        raise ValueError("Unanchored retirement admitted reads")
                    result = await self.request(b, "reader_recover", "reviewer", {"repair": False, "expected_head_sha256": None, "expected_tip_sha256": None})
                    pins = result.json()
                    result = await self.request(b, "reader_recover", "reviewer", {"repair": True, "expected_head_sha256": pins["binding_head_sha256"], "expected_tip_sha256": pins["binding_tip_sha256"]})
                    if result.status_code != 200:
                        raise ValueError("Exact retirement repair rejected")
            elif result.status_code != 200:
                raise ValueError("Retirement setup rejected")
            await self.observe(b)
            if n == 13:
                event = e.decode(e.read(self.reader_controls.root / "0004.json"))
                (self.reader_controls.anchor.path.parent / (event["head"] + ".intent.json")).unlink()
                return (await self.observe(a)).status_code
            if n == 9:
                return (await self.view(a)).status_code
            if n == 4:
                return (await self.select_reader(a)).status_code
            before = self.preserved_files()
            status = await self.status(b)
            if (status.status_code != 200 or not status.json()["retirement_sha256"] or status.json()["usable"]
                    or status.json()["active"] or (await self.view(a)).status_code != 409 or before != self.preserved_files()):
                raise ValueError("Retirement status or read renewed authority or rewrote history")
            if n in {1, 11, 12}:
                return status.status_code
        self.mode = "renewal"
        if n in {3, 8, 21}:
            await self.next_stage(a, "-second")
            await self.bind(a, b)
            self.mode, self.target_selection = "rollback", first_selection["selection_sha256"]
            if n == 21:
                self.target_selection = "f" * 64
        if n == 22:
            await self.withdrawal(a, b)
            await self.observe(a)
            if (await self.view(a)).status_code != 409 or (await self.selected(b)).status_code != 409:
                raise ValueError("Canonical withdrawal did not fence readers")
        await self.next_stage(a, "-successor")
        if n == 20:
            self.mode = "initial"
        result = await self.prepare_reader(a)
        if n in {7, 20, 21}:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Fresh successor setup rejected")
        if n in {8, 18}:
            await self.withdrawal(a, b)
            await self.observe(a)
        if n == 15:
            self.advance(301)
            await self.observe(a)
        result = await self.decide_reader(b, role="preparer" if n == 5 else "reviewer", denied=n == 6)
        if n in {5, 8, 15, 18}:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Fresh independent successor decision rejected")
        if n == 16:
            self.revoke("reviewer")
        if n == 19:
            path = self.archive_restores / self.archive_restore_id / "journal/metadata.json"
            path.write_bytes(path.read_bytes() + b"changed")
        result = await self.select_reader(a)
        if n in {6, 16, 19}:
            return result.status_code
        if result.status_code != 200 or self.reader_selection["selection_sha256"] == first_selection["selection_sha256"]:
            raise ValueError("Fresh selection reused predecessor")
        if n == 14:
            current_id, current_sel = self.reader_id, self.reader_selection
            self.reader_id, self.reader_selection = first_id, first_selection
            result = await self.retire(b)
            self.reader_id, self.reader_selection = current_id, current_sel
            return result.status_code
        if n == 17:
            return (await self.view(a, previous=previous, limit=1)).status_code
        if (await self.view(a, selection=first_selection)).status_code != 409:
            raise ValueError("Historical predecessor became active again")
        if self.reader_decision["decision_sha256"] == first_decision["decision_sha256"]:
            raise ValueError("Historical approval was reused")
        before = self.preserved_files()
        result = await self.view(a)
        if result.status_code != 200 or before != self.preserved_files():
            raise ValueError("Read changed retained evidence")
        if n == 22:
            if not any(v["access_withdrawn"] for v in result.json()["rows"]) or (await self.selected(b)).status_code != 409:
                raise ValueError("Fresh metadata renewed withdrawn ordinary authority")
        return result.status_code

    def result(self, status):
        value = super().result(status)
        value.update(retirement_permanent_per_selection=True, fresh_independent_decision_for_succession=True,
                     historical_approvals_never_reactivated=True, source_writer_unchanged=True)
        return value
