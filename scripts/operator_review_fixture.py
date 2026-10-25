"""Invented accounts and operator metadata. Never opens live auth or matter stores."""

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import operator_enrollment_evidence as evidence
import operator_enrollment_fixture as enrollment
import portable_controller_fixture as portable
from authenticated_operator_review import DECISIONS, PREFIX, ReviewHandoff, Target
from cryptography.fernet import Fernet
from operator_review_auth import PROFILE, SessionAuthority
from sqlalchemy import delete, select

from app.auth import check_password, create_session, hash_password
from app.db import EmployeeRole, FirmRole, LoginSession, Store, User
from app.firm_rbac import CATALOG, initialize_firm

CASES = [("F01_valid", 200), ("F02_bad_cookie", 401), ("F03_no_csrf", 400), ("F04_origin", 403),
         ("F05_duplicate_cookie", 400), ("F06_self_review", 403), ("F07_unassigned_reviewer", 403),
         ("F08_foreign_firm", 403), ("F09_revoked_reviewer_session", 401), ("F10_expired_reviewer_session", 401),
         ("F11_disabled_reviewer", 401), ("F12_removed_reviewer_roles", 403), ("F13_reviewer_role_revision", 409),
         ("F14_preparer_session_revoked", 403), ("F15_preparer_role_revision", 403), ("F16_packet_changed", 400),
         ("F17_observation_changed", 400), ("F18_candidate_changed", 409), ("F19_operation_revoked", 409),
         ("F20_handoff_expired", 409), ("F21_identity_field_in_body", 400), ("F22_decision_replay", 409),
         ("F23_changes_required", 200), ("F24_rejected", 200), ("F25_handoff_hash", 409),
         ("F26_decision_hash", 409), ("F27_revoked_after_commit", 403), ("F28_prepare_revoked_before_commit", 403),
         ("F29_review_revoked_before_commit", 403), ("F30_lost_acknowledgement", 400),
         ("F31_no_privileged_helpers", 200), ("F32_malformed_json", 400), ("F33_body_budget", 413),
         ("F34_query", 400), ("F35_path_in_body", 400), ("F36_profile_tampered", 403),
         ("F37_store_contains_record", 403), ("F38_concurrent_decision", 409), ("F39_unrelated_inspection", 403),
         ("F40_expired_after_commit", 409), ("F41_expired_packet_history", 200), ("F42_wrong_csrf", 403),
         ("F43_roles_revoked_history", 200), ("F44_prepare_replay", 409)]
POLICY = {"schema": "authenticated-operator-review-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "actual_local_auth": True, "disposable_accounts_only": True,
          "review_max_age_seconds": 300, "body_max_bytes": 8192, "model_verification_seconds": 20,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}
ORIGIN = "http://operator.invalid"
FIRM = "disposable-operator-firm"


@lru_cache(maxsize=1)
def credential_seed():
    # Test-only hashes are built once. Every new account gets a fresh subject ID,
    # every login still verifies its password and creates an independent session.
    passwords = {role: secrets.token_urlsafe(24) for role in ("preparer", "reviewer", "other", "foreign")}
    return passwords, {role: hash_password(value) for role, value in passwords.items()}


class Fixture:
    def __init__(self, name, models, work, anchors, api):
        self.name, self.api, self.now, self.armed = name, api, evidence.utc(), False
        self.base = portable.Fixture(name, models, work, anchors, api)
        self.work = self.base.work
        self.profile = self.work / "accounts"
        self.profile.mkdir(mode=0o700)
        self.store = Store(SimpleNamespace(data_dir=self.profile, encryption_key=Fernet.generate_key().decode(),
                                          demo_mode=True, database_url="sqlite:///" + str(self.profile / "disposable-identities.sqlite")))
        (self.profile / "disposable-identities.sqlite").chmod(0o600)
        self.ids = {role: evidence.sha((name + role).encode())[:32] for role in ("preparer", "reviewer", "other", "foreign")}
        passwords, hashes = credential_seed()
        self.passwords = dict(passwords)
        self.cookies, self.csrf, self.session_ids = {}, {}, {}
        with self.store.session() as session:
            for role, ident in self.ids.items():
                session.add(User(id=ident, username="invented-" + role, name="Invented operator", firm_id=FIRM if role != "foreign" else "foreign-firm",
                                 role="admin", password_hash=hashes[role], active=True))
            session.flush()
            initialize_firm(session, FIRM)
            initialize_firm(session, "foreign-firm")
            for role, ident in self.ids.items():
                session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == ident))
                rid = evidence.sha((name + role + "-role").encode())[:32]
                session.add(FirmRole(id=rid, firm_id=FIRM if role != "foreign" else "foreign-firm", name="Invented isolated role",
                                     permissions=evidence.encode(sorted(CATALOG)).decode(), revision=1, starter=False))
                session.flush()
                session.add(EmployeeRole(user_id=ident, role_id=rid))
            session.commit()
        for role in ("preparer", "reviewer"):
            self.login(role)
        evidence.retain(self.profile / "disposable-profile.json", evidence.encode({"schema": PROFILE, "profile_id": evidence.sha((name + "-profile").encode())[:32], "production_activation": False}))
        self.authority = SessionAuthority(self.store, self.profile, firm_id=FIRM,
                                          bindings={self.ids["preparer"]: "preparer", self.ids["reviewer"]: "reviewer", self.ids["other"]: "reviewer", self.ids["foreign"]: "reviewer"},
                                          origins=(ORIGIN,))
        candidate_path, confirmation_path = self.base.trust / "candidate.json", self.base.trust / "key-confirmation.json"
        candidate = evidence.decode(candidate_path.read_bytes())
        candidate["created_at"] = self.now - 100
        candidate_path.write_bytes(evidence.encode(candidate))
        confirmation = evidence.decode(confirmation_path.read_bytes())
        confirmation.update(reviewer=self.ids["reviewer"], confirmed_at=self.now - 50, expires_at=self.now - 50 + 86400)
        confirmation_path.write_bytes(evidence.encode(confirmation))
        expectations = enrollment.expectations(self.base, evidence.sha((Path(api.readiness.__file__).parent.parent / "guarded-stage-manifest.json").read_bytes()))
        expectations["enrollment"].update(reviewer=self.ids["reviewer"], provisioned_by=self.ids["preparer"])
        packet = evidence.packet(expectations, packet_id=evidence.sha(name.encode())[:32], now=self.now)
        self.packet_path, self.packet_sha = self.work / "packet.json", evidence.sha(packet)
        evidence.retain(self.packet_path, packet)
        stage = Path(api.readiness.__file__).parent.parent
        observation = evidence.reconcile(self.packet_path, self.packet_sha, stage, self.base.model, self.base.journal,
                                         self.base.binding, self.base.trust, api=api, clock=lambda: self.now)
        if observation["status"] != "reconciled_for_disposable_mock_validation":
            raise ValueError("Invented authentication source fixture rejected")
        self.observation_path = self.work / "observation.json"
        self.observation_sha = evidence.retain(self.observation_path, evidence.encode(observation))["sha256"]
        self.target = Target(self.packet_path, self.packet_sha, self.observation_path, self.observation_sha, stage,
                             self.base.model, self.base.journal, self.base.binding, self.base.trust, api)
        self.ledger = self.work / "reviews"
        self.ledger.mkdir(mode=0o700)
        self.service = ReviewHandoff(self.authority, self.target, self.ledger, clock=lambda: self.now, checkpoint=self.point)
        self.request_id = evidence.sha((name + "-request").encode())[:32]
        self.handoff = self.decision = None
        self.responses = []

    def login(self, role):
        with self.store.session() as session:
            user = session.get(User, self.ids[role])
            if not check_password(self.passwords[role], user.password_hash):
                raise ValueError("Disposable password authentication failed")
            token, csrf = create_session(session, user, 1)
            from app.db import digest
            self.cookies[role], self.csrf[role], self.session_ids[role] = token, csrf, digest(token)

    def headers(self, role):
        if role not in self.cookies:
            self.login(role)
        return {"cookie": "la_session=" + self.cookies[role], "x-csrf-token": self.csrf[role], "origin": ORIGIN, "content-type": "application/json"}

    def revoke(self, role):
        with self.store.session() as session:
            session.execute(delete(LoginSession).where(LoginSession.token_hash == self.session_ids[role]))
            session.commit()

    def revise_role(self, role):
        with self.store.session() as session:
            rid = session.scalar(select(EmployeeRole.role_id).where(EmployeeRole.user_id == self.ids[role]))
            row = session.get(FirmRole, rid)
            row.revision += 1
            session.commit()

    def point(self, stage):
        if not self.armed:
            return
        if self.name == "F28_prepare_revoked_before_commit" and stage == "before_commit":
            self.revoke("preparer")
        if self.name == "F29_review_revoked_before_commit" and stage == "before_commit":
            self.revoke("reviewer")
        if self.name == "F27_revoked_after_commit" and stage == "after_commit":
            self.revoke("reviewer")
        if self.name == "F30_lost_acknowledgement" and stage == "after_commit":
            raise ValueError("Invented lost acknowledgement")
        if self.name == "F40_expired_after_commit" and stage == "after_commit":
            self.now += 301

    async def request(self, client, action, role, body, *, headers=None, raw=None, suffix=""):
        response = await client.post(PREFIX + action + suffix, content=evidence.encode(body) if raw is None else raw,
                                     headers=self.headers(role) if headers is None else headers)
        self.responses.append(response)
        if response.headers.get("cache-control") != "no-store":
            raise ValueError("Private response caching enabled")
        return response

    async def run(self, client):
        prepare = {"request_id": self.request_id, "packet_sha256": self.packet_sha, "observation_sha256": self.observation_sha}
        if self.name == "F28_prepare_revoked_before_commit":
            self.armed = True
        headers, raw, suffix = self.headers("preparer"), None, ""
        if self.name == "F02_bad_cookie":
            headers["cookie"] = "la_session=invalid-cookie"
        if self.name == "F03_no_csrf":
            headers.pop("x-csrf-token")
        if self.name == "F04_origin":
            headers["origin"] = "https://foreign.invalid"
        if self.name == "F42_wrong_csrf":
            headers["x-csrf-token"] = "invalid-csrf"
        if self.name == "F05_duplicate_cookie":
            headers["cookie"] += "; la_session=" + self.cookies["preparer"]
        if self.name == "F32_malformed_json":
            raw = b"{"
        if self.name == "F33_body_budget":
            raw = b"x" * 8193
        if self.name == "F34_query":
            suffix = "?scope=other"
        if self.name == "F35_path_in_body":
            prepare["path"] = "/invented-unapproved-path"
        if self.name == "F36_profile_tampered":
            path = self.profile / "disposable-profile.json"
            path.write_bytes(path.read_bytes() + b" ")
        if self.name == "F37_store_contains_record":
            with self.store.session() as session:
                self.store.add(session, "matter", session.get(User, self.ids["preparer"]), {"text": "Invented forbidden record"})
                session.commit()
        response = await self.request(client, "prepare", "preparer", prepare, headers=headers, raw=raw, suffix=suffix)
        if response.status_code != 200:
            return response.status_code
        self.handoff = response.json()
        if self.name == "F44_prepare_replay":
            return (await self.request(client, "prepare", "preparer", prepare)).status_code
        self.armed = True
        role = "reviewer"
        if self.name == "F06_self_review":
            role = "preparer"
        if self.name == "F07_unassigned_reviewer":
            role = "other"
        if self.name == "F08_foreign_firm":
            role = "foreign"
        if self.name == "F09_revoked_reviewer_session":
            self.revoke("reviewer")
        if self.name == "F10_expired_reviewer_session":
            with self.store.session() as session:
                session.get(LoginSession, self.session_ids["reviewer"]).expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
                session.commit()
        if self.name == "F11_disabled_reviewer":
            with self.store.session() as session:
                session.get(User, self.ids["reviewer"]).active = False
                session.commit()
        if self.name == "F12_removed_reviewer_roles":
            with self.store.session() as session:
                session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == self.ids["reviewer"]))
                session.commit()
        if self.name in {"F13_reviewer_role_revision", "F15_preparer_role_revision"}:
            self.revise_role("reviewer" if self.name.startswith("F13") else "preparer")
        if self.name == "F14_preparer_session_revoked":
            self.revoke("preparer")
        if self.name in {"F16_packet_changed", "F17_observation_changed", "F18_candidate_changed"}:
            path = self.packet_path if self.name.startswith("F16") else self.observation_path if self.name.startswith("F17") else self.base.trust / "candidate.json"
            path.write_bytes(path.read_bytes() + b" ")
        if self.name == "F19_operation_revoked":
            self.base.journal.revoke(self.base.operation)
        if self.name == "F20_handoff_expired":
            self.now += 301
        choice = "changes_required" if self.name == "F23_changes_required" else "reject" if self.name == "F24_rejected" else "accept"
        decision = {"handoff_id": self.request_id, "handoff_sha256": self.handoff["handoff_sha256"], "decision": choice, "reason_code": DECISIONS[choice]}
        if self.name == "F21_identity_field_in_body":
            decision["reviewer_id"] = self.ids["reviewer"]
        if self.name == "F25_handoff_hash":
            decision["handoff_sha256"] = "0" * 64
        if self.name == "F38_concurrent_decision":
            responses = await asyncio.gather(self.request(client, "decide", role, decision), self.request(client, "decide", role, decision))
            if sorted(r.status_code for r in responses) != [200, 409]:
                raise ValueError("Duplicate decision admitted")
            return 409
        response = await self.request(client, "decide", role, decision)
        if response.status_code == 200:
            self.decision = response.json()
        inspect = {"handoff_id": self.request_id, "handoff_sha256": self.handoff["handoff_sha256"], "decision_sha256": None}
        if self.name in {"F27_revoked_after_commit", "F30_lost_acknowledgement", "F40_expired_after_commit"}:
            original = evidence.read(self.ledger / (self.request_id + ".decision.json"))
            observed = await self.request(client, "inspect", "preparer", inspect)
            if observed.status_code != 200 or observed.json()["status"] != "observed_decision_needs_pin":
                raise ValueError("Committed history could not be observed")
            inspect["decision_sha256"] = observed.json()["decision_sha256"]
            read = await self.request(client, "inspect", "preparer", inspect)
            expected = "reviewed_for_disposable_handoff" if self.name == "F30_lost_acknowledgement" else "stale_review_retained"
            if read.status_code != 200 or read.json()["status"] != expected or evidence.read(self.ledger / (self.request_id + ".decision.json")) != original:
                raise ValueError("Failed acknowledgement rewrote history")
            return response.status_code
        if response.status_code != 200:
            return response.status_code
        inspect["decision_sha256"] = self.decision["decision_sha256"]
        if self.name == "F41_expired_packet_history":
            self.now += 901
        if self.name == "F43_roles_revoked_history":
            with self.store.session() as session:
                session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == self.ids["reviewer"]))
                session.commit()
        if self.name == "F22_decision_replay":
            original = evidence.read(self.ledger / (self.request_id + ".decision.json"))
            repeated = await self.request(client, "decide", role, decision)
            if evidence.read(self.ledger / (self.request_id + ".decision.json")) != original:
                raise ValueError("Review history overwritten")
            return repeated.status_code
        if self.name == "F26_decision_hash":
            inspect["decision_sha256"] = "0" * 64
        role = "other" if self.name == "F39_unrelated_inspection" else "preparer"
        read = await self.request(client, "inspect", role, inspect)
        expected = "stale_review_retained" if self.name in {"F41_expired_packet_history", "F43_roles_revoked_history"} else "reviewed_for_disposable_handoff"
        if read.status_code == 200 and read.json()["status"] != expected:
            raise ValueError("Fresh decision not reconciled")
        return read.status_code

    def result(self, status):
        files = {p.name: evidence.sha(evidence.read(p)) for p in self.ledger.iterdir()}
        raw = b"".join(evidence.read(p) for p in self.ledger.iterdir()) + b"".join(r.content for r in self.responses)
        if any(value.encode() in raw for value in [*self.passwords.values(), *self.cookies.values(), *self.csrf.values()]):
            raise ValueError("Disposable credential leaked into review metadata")
        if any(any(response.json().get(k) is not False for k in evidence.FLAGS) for response in self.responses):
            raise ValueError("Review granted execution or trust authority")
        return {"id": self.name, "status": status, "HTTP_requests": len(self.responses), "decision_records": sum(n.endswith(".decision.json") for n in files),
                "handoff_records": sum(n.endswith(".handoff.json") for n in files), "ledger_sha256": evidence.sha(evidence.encode(files)),
                "credentials_absent_from_responses_and_review_records": True, "all_authority_flags_false": True,
                "actual_app_session_auth": True, "runtime_installation": False, "real_trust_enrolled": False}

    def close(self):
        self.store.engine.dispose()


def forbid_provider_helpers(api):
    from contextlib import ExitStack
    stack = ExitStack()
    for name in ("create_issuer", "load_signer", "confirm_key", "revoke_key"):
        stack.enter_context(patch.object(api.trust, name, side_effect=AssertionError("Forbidden real-trust helper")))
    return stack
