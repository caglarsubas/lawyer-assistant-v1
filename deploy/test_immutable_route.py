import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / "scripts"),
    str(Path(__file__).resolve().parents[1] / "backend"),
]
from build_signed_route_stage import build_route  # noqa: E402
from evaluate_immutable_route import evaluate_async  # noqa: E402
from immutable_provider_hook import ManifestSnapshot  # noqa: E402
from immutable_route_fixture import NativeBytes, RouteFixture  # noqa: E402
from provider_stage_adapters import ReceiptStore  # noqa: E402
from provider_stage_fixture import CREDENTIAL  # noqa: E402
from provider_trust_stage import write  # noqa: E402
from signed_provider_contract import decode, encode, sha  # noqa: E402
from staged_signed_route import COMPLETION_PATH, IDENTITY_PATH  # noqa: E402


class Contracts(unittest.IsolatedAsyncioTestCase):
    async def test_frozen_sixteen_invented_outcomes(self):
        first = await evaluate_async()
        self.assertEqual(first, await evaluate_async())
        self.assertEqual(first["summary"], {"cases": 16, "expected_results": 16})
        self.assertFalse(first["executed_weights_qualified"])
        self.assertEqual(first["native_inference_calls"], 0)

    async def test_exact_wire_binding_and_owned_digest_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFixture(Path(folder).resolve())
            await f.prepare(f.base.request + b" \n")
            response = await f.post(COMPLETION_PATH, f.envelope)
            self.assertEqual(response.status_code, 200)
            proof = f.pending.consume(response.content, now=f.now)
            self.assertEqual(proof["request_sha256"], sha(f.raw))
            self.assertFalse(proof["native_execution_authorization"])
            self.assertEqual(len(f.sent), 1)
            sent = f.sent[0]
            self.assertEqual(str(sent.url), "http://127.0.0.1:11434/api/chat")
            self.assertEqual(sent.method, "POST")
            value = decode(sent.content)
            self.assertEqual(value["model"], f.reference)
            self.assertEqual(value["messages"], decode(f.raw)["messages"])
            self.assertEqual(
                value["options"]["num_ctx"], f.base.pin["model_context_units"]
            )
            self.assertNotIn("authorization", sent.headers)
            self.assertNotIn(CREDENTIAL.encode(), sent.content)
            data = f.receipts.path.read_bytes()
            self.assertNotIn(b"Invented protocol input", data)
            self.assertNotIn(b"Invented staged answer", data)
            self.assertNotIn(CREDENTIAL.encode(), data)

    async def test_failure_and_restart_do_not_replay_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFixture(Path(folder).resolve(), "http502")
            await f.prepare()
            self.assertEqual(
                (await f.post(COMPLETION_PATH, f.envelope)).status_code, 400
            )
            f.route.receipts = ReceiptStore(f.receipts.path)
            f.mode = "good"
            self.assertEqual(
                (await f.post(COMPLETION_PATH, f.envelope)).status_code, 400
            )
            self.assertEqual(len(f.sent), 1)

    async def test_authentication_and_artifact_changes_during_dispatch_reject(self):
        for mode in ("revoked_during", "changed_during", "late_expiry"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                f = RouteFixture(Path(folder).resolve(), mode)
                status, calls = await f.run()
                self.assertEqual((status, calls), (400, 1))
                self.assertEqual(
                    (await f.post(COMPLETION_PATH, f.envelope)).status_code, 400
                )
                self.assertEqual(len(f.sent), 1)

    async def test_snapshot_file_ownership_links_and_digests(self):
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFixture(Path(folder).resolve())
            path = f.artifacts / ("sha256-" + sha(f.model))
            for mode in ("permissions", "hardlink", "symlink", "corrupt"):
                with self.subTest(mode=mode):
                    if mode == "permissions":
                        path.chmod(0o644)
                    elif mode == "hardlink":
                        os.link(path, f.artifacts / "other-link")
                    elif mode == "symlink":
                        path.rename(f.artifacts / "held")
                        path.symlink_to(f.artifacts / "held")
                    else:
                        path.write_bytes(b"X" * len(f.model))
                    with self.assertRaises((ValueError, OSError)):
                        f.snapshot.verify()
                    if mode == "permissions":
                        path.chmod(0o600)
                    elif mode == "hardlink":
                        (f.artifacts / "other-link").unlink()
                    elif mode == "symlink":
                        path.unlink()
                        (f.artifacts / "held").rename(path)

    async def test_remote_manifest_list_and_unsupported_layers_rejected(self):
        for mode in ("remote", "list", "adapter", "multiple"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                f = RouteFixture(Path(folder).resolve())
                manifest = decode(encode(f.manifest))
                if mode == "remote":
                    raw = encode(
                        {
                            "model_format": "gguf",
                            "remote_host": "https://external.invalid",
                        }
                    )
                    write(f.artifacts / ("sha256-" + sha(raw)), raw)
                    manifest["config"].update(
                        digest="sha256:" + sha(raw), size=len(raw)
                    )
                elif mode == "list":
                    manifest["mediaType"] = "application/vnd.oci.image.index.v1+json"
                elif mode == "adapter":
                    manifest["layers"][0]["mediaType"] = (
                        "application/vnd.ollama.image.adapter"
                    )
                else:
                    manifest["layers"] *= 2
                raw = encode(manifest)
                write(f.artifacts / ("sha256-" + sha(raw)), raw)
                p = dict(f.base.pin, model_digest_sha256=sha(raw))
                with self.assertRaises(ValueError):
                    ManifestSnapshot(f.artifacts, p)
                self.assertFalse(f.sent)

    async def test_unknown_routes_duplicate_auth_and_query_do_not_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFixture(Path(folder).resolve())
            await f.prepare()
            for path, headers in (
                ("/v1/admin", None),
                (COMPLETION_PATH + "?redirect=external", None),
                (
                    COMPLETION_PATH,
                    [
                        ("Authorization", "Bearer " + CREDENTIAL),
                        ("authorization", "Bearer SECRET-SENTINEL"),
                        ("Content-Type", "application/json"),
                    ],
                ),
            ):
                response = await f.post(path, f.envelope, headers=headers)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.content, b'{"error":"staged_request_rejected"}'
                )
                self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertFalse(f.sent)

    async def test_cancelled_execution_burns_nonce_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFixture(Path(folder).resolve(), "cancel")
            await f.prepare()
            with self.assertRaises(asyncio.CancelledError):
                await f.post(COMPLETION_PATH, f.envelope)
            self.assertFalse(f.route.lock.locked())
            f.mode = "good"
            self.assertEqual(
                (await f.post(COMPLETION_PATH, f.envelope)).status_code, 400
            )
            self.assertEqual(len(f.sent), 1)

    async def test_bounded_concurrent_route_capacity(self):
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFixture(Path(folder).resolve())
            await f.prepare()
            entered, release = asyncio.Event(), asyncio.Event()
            native = f.native

            async def blocked(request):
                entered.set()
                await release.wait()
                return await native(request)

            f.hook.transport = httpx.MockTransport(blocked)
            first = asyncio.create_task(f.post(COMPLETION_PATH, f.envelope))
            await asyncio.wait_for(entered.wait(), 2)
            second = await f.post(COMPLETION_PATH, f.envelope)
            self.assertEqual(second.status_code, 503)
            release.set()
            self.assertEqual((await first).status_code, 200)
            self.assertEqual(len(f.sent), 1)

    async def test_deadline_usage_and_context_admission(self):
        for mode in ("timeout", "bool_usage", "too_many_tokens", "context"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                f = RouteFixture(Path(folder).resolve())

                async def invalid(request):
                    f.sent.append(request)
                    if mode == "timeout":
                        raise httpx.ReadTimeout("SECRET-SENTINEL")
                    body = {
                        "model": f.reference,
                        "message": {"role": "assistant", "content": "Invented."},
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 1,
                        "eval_count": True if mode == "bool_usage" else 101,
                    }
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/json"},
                        stream=NativeBytes(encode(body)),
                    )

                f.hook.transport = httpx.MockTransport(invalid)
                raw = None
                if mode == "context":
                    value = decode(f.base.request)
                    value["messages"][0]["content"] = (
                        "X" * f.base.pin["application_context_units"]
                    )
                    raw = encode(value)
                await f.prepare(raw)
                response = await f.post(COMPLETION_PATH, f.envelope)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(b"SECRET-SENTINEL", response.content)
                self.assertEqual(len(f.sent), 0 if mode == "context" else 1)

    async def test_portable_package_retains_prior_contract_and_no_app_import(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            manifest = build_route(root / "bundle")
            self.assertEqual(len(manifest["package_sha256"]), 8)
            package = root / "bundle/lawyer_provider_stage"
            for n, h in manifest["package_sha256"].items():
                self.assertEqual(
                    hashlib.sha256((package / n).read_bytes()).hexdigest(), h
                )
            code = (
                "import sys;sys.path.insert(0,"
                + repr(str(root / "bundle"))
                + ");import lawyer_provider_stage.route,lawyer_provider_stage.hook;assert not any(n=='app' or n.startswith('app.') for n in sys.modules)"
            )
            subprocess.run(
                [sys.executable, "-I", "-c", code],
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.assertFalse(manifest["production_activation"])
            self.assertFalse(manifest["executed_weights_qualified"])
            self.assertFalse(manifest["private_material_included"])

    async def test_duplicate_json_unknown_envelope_and_identity_are_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            f = RouteFixture(Path(folder).resolve())
            await f.prepare()
            value = dict(
                f.envelope,
                execution_handle="client-supplied",
                attempts=1,
                executed_reference=f.reference,
            )
            self.assertEqual((await f.post(COMPLETION_PATH, value)).status_code, 400)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=f.route),
                base_url="http://staged.invalid",
            ) as client:
                response = await client.post(
                    IDENTITY_PATH,
                    content=b'{"model":"a","model":"b"}',
                    headers={
                        "Authorization": "Bearer " + CREDENTIAL,
                        "Content-Type": "application/json",
                    },
                )
                self.assertEqual(response.status_code, 400)
            self.assertFalse(f.sent)


if __name__ == "__main__":
    unittest.main()
