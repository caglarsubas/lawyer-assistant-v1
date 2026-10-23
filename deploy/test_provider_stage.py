import ast
import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / "scripts"),
    str(Path(__file__).resolve().parents[1] / "backend"),
]
from build_provider_stage import build  # noqa: E402
from evaluate_provider_stage import evaluate  # noqa: E402
from provider_stage_adapters import ReceiptStore, authenticated_principal  # noqa: E402
from provider_stage_fixture import CREDENTIAL, NOW, StageFixture  # noqa: E402
from provider_trust_stage import (  # noqa: E402
    confirm_key,
    create_issuer,
    import_candidate,
    load_signer,
    public_record,
    read,
    revoke_key,
    trusted_key,
)
from signed_provider_contract import (  # noqa: E402
    IdentityChallenge,
    ResponseChallenge,
    decode,
    encode,
)
from signed_provider_fixture import I_NONCE, R_NONCE  # noqa: E402


class Contracts(unittest.TestCase):
    def test_frozen_twelve_outcomes_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("Network prohibited")):
            report = evaluate()
            self.assertEqual(report, evaluate())
        self.assertEqual(
            report["summary"], {"cases": 12, "expected_results": 12, "consumed_synthetic_receipts": 1}
        )
        self.assertFalse(report["live_execution_identity_qualified"])

    def test_actual_auth_record_interface_current_snapshot_and_no_logging(self):
        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve())
            self.assertEqual(
                authenticated_principal(f.auth, CREDENTIAL, now=NOW)["key_id"], f.base.pin["key_id"]
            )
            for credential in ("SYNTHETIC-UNKNOWN", "bad\r\nheader"):
                with self.assertRaisesRegex(ValueError, "Current authenticated principal unavailable"):
                    authenticated_principal(f.auth, credential, now=NOW)
            f.auth._keys_by_value = {}
            with self.assertRaises(ValueError):
                f.identity(CREDENTIAL, f.base.pin["model_id"], f.base.pin["route_sha256"])
            f.auth._keys_loaded = False
            with self.assertRaises(ValueError):
                authenticated_principal(f.auth, CREDENTIAL, now=NOW)

    def test_loaded_manager_has_no_load_or_resolution_and_rejects_current_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve(), "mutable_tag")
            with self.assertRaisesRegex(ValueError, "immutable_reference_required"):
                f.prepare()
            self.assertFalse((Path(folder) / "receipts.sqlite3").exists())
            f.adapter._model_id = "sha256:" + f.base.pin["model_digest_sha256"]
            # The descriptor still references the tag: cannot silently use it.
            with self.assertRaises(ValueError):
                f.prepare()

    def test_completed_receipt_integrates_with_signed_v2_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve())
            f.prepare()
            f.store.complete(
                f.handle,
                f.base.response,
                f.resolved,
                "sha256:" + f.resolved["model_digest_sha256"],
                attempts=1,
                now=NOW + 1,
            )
            reopened = ReceiptStore(f.store.path)
            f.base.issuer.resolve_execution = lambda handle: reopened.consume(handle, now=NOW + 1)
            raw = f.base.issuer.bind_response(
                CREDENTIAL,
                f.base.request,
                f.base.response,
                f.pending.expectation(),
                f.proof,
                f.handle,
                now=NOW + 1,
            )
            self.assertFalse(f.pending.consume(raw, now=NOW + 1)["native_execution_authorization"])
            with self.assertRaises(ValueError):
                ReceiptStore(f.store.path).consume(f.handle, now=NOW + 1)
            payload = read(f.store.path)
            self.assertNotIn(CREDENTIAL.encode(), payload)
            self.assertNotIn(b"Invented protocol input", payload)
            self.assertNotIn(b"Invented response", payload)

    def test_bad_finalization_burns_receipt_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve())
            f.prepare()
            ref = "sha256:" + f.resolved["model_digest_sha256"]
            with self.assertRaises(ValueError):
                f.store.complete(f.handle, f.base.response, f.resolved, ref, attempts=2, now=NOW + 1)
            with self.assertRaises(ValueError):
                f.store.complete(f.handle, f.base.response, f.resolved, ref, attempts=1, now=NOW + 1)
            with self.assertRaises(ValueError):
                f.store.consume(f.handle, now=NOW + 1)

    def test_concurrent_consumption_and_duplicate_challenge(self):
        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve())
            f.prepare()
            with self.assertRaises(sqlite3.IntegrityError):
                f.store.begin(f.resolved, f.base.request, f.pending.expectation(), now=NOW)
            f.store.complete(
                f.handle,
                f.base.response,
                f.resolved,
                "sha256:" + f.resolved["model_digest_sha256"],
                attempts=1,
                now=NOW + 1,
            )

            def consume(_):
                try:
                    ReceiptStore(f.store.path).consume(f.handle, now=NOW + 1)
                    return True
                except ValueError:
                    return False

            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sum(pool.map(consume, range(2))), 1)

    def test_unfinished_and_expired_receipts_never_become_execution_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve())
            f.prepare()
            with self.assertRaises(ValueError):
                ReceiptStore(f.store.path).consume(f.handle, now=NOW + 1)
            f.store.complete(
                f.handle,
                f.base.response,
                f.resolved,
                "sha256:" + f.resolved["model_digest_sha256"],
                attempts=1,
                now=NOW + 1,
            )
            with self.assertRaises(ValueError):
                f.store.consume(f.handle, now=NOW + 120)
            with self.assertRaises(ValueError):
                f.store.consume(f.handle, now=NOW + 1)

    def setup_keys(self, root):
        issuer = root / "issuer"
        trust = root / "consumer"
        result = create_issuer(issuer, "synthetic-stage-issuer", now=NOW)
        import_candidate(read(issuer / "public-candidate.json"), trust)
        return issuer, trust, result["public_fingerprint"]

    def test_encrypted_key_material_and_independent_confirmation_default_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            issuer, trust, fp = self.setup_keys(Path(folder).resolve())
            self.assertTrue(
                read(issuer / "signer.encrypted.pem").startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")
            )
            self.assertEqual({p.name for p in trust.iterdir()}, {"candidate.json"})
            for p in issuer.iterdir():
                self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            with self.assertRaises((ValueError, OSError)):
                trusted_key(trust, fp, now=NOW)
            with self.assertRaises(ValueError):
                load_signer(issuer, "0" * 64)
            with self.assertRaises(ValueError):
                confirm_key(trust, "0" * 64, "synthetic-reviewer", now=NOW)
            confirm_key(trust, fp, "synthetic-reviewer", now=NOW)
            key = load_signer(issuer, fp)
            public = trusted_key(trust, fp, now=NOW)
            public.verify(key.sign(b"synthetic-key-integrity"), b"synthetic-key-integrity")
            self.assertFalse(decode(read(trust / "key-confirmation.json"))["production_activation"])

    def test_revocation_expiry_and_confirmation_history_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            issuer, trust, fp = self.setup_keys(Path(folder).resolve())
            confirm_key(trust, fp, "synthetic-reviewer", now=NOW)
            old = read(trust / "key-confirmation.json")
            with self.assertRaises(OSError):
                confirm_key(trust, fp, "other", now=NOW + 1)
            self.assertEqual(read(trust / "key-confirmation.json"), old)
            with self.assertRaises(ValueError):
                trusted_key(trust, fp, now=NOW + 86400)
            revoke_key(trust, "synthetic-reviewer", now=NOW + 2)
            with self.assertRaises(ValueError):
                trusted_key(trust, fp, now=NOW + 3)
            self.assertTrue((issuer / "signer.encrypted.pem").exists())

    def test_symlink_hardlink_permissions_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            issuer, trust, fp = self.setup_keys(root)
            with self.assertRaises(OSError):
                create_issuer(issuer, "synthetic-stage-issuer", now=NOW)
            file = issuer / "signer.encrypted.pem"
            file.chmod(0o644)
            with self.assertRaises(ValueError):
                load_signer(issuer, fp)
            file.chmod(0o600)
            os.link(file, issuer / "hardlink")
            with self.assertRaises(ValueError):
                load_signer(issuer, fp)
            (issuer / "hardlink").unlink()
            link = root / "symlink"
            link.symlink_to(issuer, target_is_directory=True)
            with self.assertRaises(ValueError):
                load_signer(link, fp)
            confirm_key(trust, fp, "synthetic-reviewer", now=NOW)
            (trust / "revoked.json").symlink_to(trust / "missing")
            with self.assertRaises(ValueError):
                trusted_key(trust, fp, now=NOW + 1)

    def test_public_key_tampering_and_password_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            issuer, trust, fp = self.setup_keys(Path(folder).resolve())
            record = decode(read(trust / "candidate.json"))
            record["fingerprint"] = "0" * 64
            with self.assertRaises(ValueError):
                public_record(encode(record))
            (issuer / "signer-password").write_bytes(b"SYNTHETIC-WRONG-PASSWORD")
            with self.assertRaisesRegex(ValueError, "Staged encrypted signer unavailable"):
                load_signer(issuer, fp)

    def test_bundle_is_portable_and_imports_preserve_contract_AST(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            manifest = build(root / "public-bundle")
            package = root / "public-bundle/lawyer_provider_stage"
            self.assertFalse(manifest["private_material_included"])
            original = ast.parse(
                (Path(__file__).resolve().parents[1] / "scripts/signed_provider_contract.py").read_text()
            )
            bundled = ast.parse((package / "contract.py").read_text())

            def filtered(tree):
                return [
                    ast.dump(n, include_attributes=False)
                    for n in tree.body
                    if not isinstance(n, (ast.Import, ast.ImportFrom))
                ]

            self.assertEqual(filtered(original), filtered(bundled))
            for p in package.iterdir():
                self.assertNotIn("from app", p.read_text())
            self.assertEqual(len(manifest["package_sha256"]), 6)

    def test_portable_producer_interoperates_with_original_consumer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            build(root / "public-bundle")
            sys.path.insert(0, str(root / "public-bundle"))
            try:
                contract = importlib.import_module("lawyer_provider_stage.contract")
                adapters = importlib.import_module("lawyer_provider_stage.adapters")
                issuer_dir, trust_dir, fp = self.setup_keys(root)
                confirm_key(trust_dir, fp, "synthetic-reviewer", now=NOW)
                private = load_signer(issuer_dir, fp)
                public = trusted_key(trust_dir, fp, now=NOW)
                f = StageFixture(root)
                store = adapters.ReceiptStore.create(root / "portable.sqlite3")
                resolver = adapters.EngineIdentityAdapter(f.auth, f.manager, f.base.pin, clock=lambda: NOW)
                issuer = contract.Issuer(
                    private,
                    "synthetic-stage-issuer",
                    resolve_identity=resolver,
                    resolve_execution=lambda h: store.consume(h, now=NOW + 1),
                )
                client = IdentityChallenge(public, "synthetic-stage-issuer", f.base.pin, challenge=I_NONCE)
                proof = client.consume(
                    issuer.issue_identity(
                        CREDENTIAL, f.base.pin["model_id"], f.base.pin["route_sha256"], I_NONCE, now=NOW
                    ),
                    now=NOW,
                )
                pending = ResponseChallenge(
                    f.base.request,
                    proof,
                    trusted_key=public,
                    issuer_key_id="synthetic-stage-issuer",
                    expected_pin=f.base.pin,
                    identity_nonce=I_NONCE,
                    now=NOW,
                    challenge=R_NONCE,
                )
                handle = store.begin(f.base.pin, f.base.request, pending.expectation(), now=NOW)
                store.complete(
                    handle,
                    f.base.response,
                    f.base.pin,
                    "sha256:" + f.base.pin["model_digest_sha256"],
                    attempts=1,
                    now=NOW + 1,
                )
                raw = issuer.bind_response(
                    CREDENTIAL,
                    f.base.request,
                    f.base.response,
                    pending.expectation(),
                    proof,
                    handle,
                    now=NOW + 1,
                )
                self.assertFalse(pending.consume(raw, now=NOW + 1)["production_activation"])
            finally:
                sys.path.remove(str(root / "public-bundle"))
                for name in list(sys.modules):
                    if name.startswith("lawyer_provider_stage"):
                        del sys.modules[name]

    def test_no_body_or_credential_in_durable_receipt_records(self):
        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve())
            f.prepare()
            f.finish()
            with f.store.connect() as db:
                rows = db.execute("SELECT record,status FROM receipts").fetchall()
            self.assertEqual(rows[0][1], "consumed")
            self.assertNotIn(CREDENTIAL, rows[0][0])
            self.assertNotIn("Invented", rows[0][0])

    def test_runtime_policy_is_inspected_instead_of_copied_from_the_pin(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as folder:
            f = StageFixture(Path(folder).resolve())
            original = vars(f.auth.settings).copy()
            for changes in (
                {"openrouter_fallback_enabled": True},
                {"upstream_retry_enabled": True},
                {"model_substitution_groups": "synthetic-a,synthetic-b"},
            ):
                f.auth.settings = SimpleNamespace(**{**original, **changes})
                with self.assertRaisesRegex(ValueError, "runtime_policy_unqualified"):
                    f.identity(CREDENTIAL, f.base.pin["model_id"], f.base.pin["route_sha256"])
