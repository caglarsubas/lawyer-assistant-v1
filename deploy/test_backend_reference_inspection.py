import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend_reference_fixture import MODEL, SENTINEL, Fixture  # noqa: E402
from backend_reference_inspection import (  # noqa: E402
    HOST,
    PORT,
    InspectionRejected,
    ReadOnlyBackendHTTP,
    Reply,
    binary_fingerprint,
    inspect_backend,
    observe_listener,
    parsed,
)
from evaluate_backend_reference import evaluate  # noqa: E402


class Socket:
    def settimeout(self, value):
        assert 0 < value <= 4


class Response:
    def __init__(self, raw=b'{"version":"1.2.3"}', status=200):
        self.raw, self.length, self.status, self.closed = raw, len(raw), status, False

    def isclosed(self):
        return self.length == 0

    def read1(self, _):
        value, self.raw = self.raw, b""
        self.length -= len(value)
        return value

    def getheaders(self):
        return (
            ("Content-Type", "application/json"),
            ("Location", "https://external.invalid"),
        )

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, host, port, *, timeout, response=None):
        self.target, self.timeout = (host, port), timeout
        self.sock, self.response, self.calls, self.closed = (
            Socket(),
            response or Response(),
            [],
            False,
        )

    def connect(self):
        self.calls.append("connect")

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class Contracts(unittest.TestCase):
    def test_cloud_and_url_references_reject_before_connection(self):
        for model in (
            "invented:cloud",
            "invented:8b-cloud",
            "invented:Cloud",
            "http://external.invalid/model",
            "invented:tag:cloud",
        ):
            with self.subTest(model=model), self.assertRaises(ValueError):
                ReadOnlyBackendHTTP(
                    connection_factory=lambda *a, **k: self.fail("Connection forbidden")
                ).exchange(
                    "POST",
                    "/api/show",
                    json.dumps({"model": model, "verbose": False}).encode(),
                )

    def test_frozen_twelve_invented_outcomes(self):
        with patch("socket.socket", side_effect=AssertionError("Network prohibited")):
            first = evaluate()
            self.assertEqual(first, evaluate())
        self.assertEqual(first["summary"], {"cases": 12, "expected_results": 12})
        self.assertEqual(first["native_inference_calls"], 0)

    def test_fixed_read_only_request_inventory(self):
        f = Fixture()
        report, _ = f.run()
        self.assertEqual(
            [(m, p) for m, p, _ in f.calls],
            [
                ("GET", "/api/version"),
                ("GET", "/api/tags"),
                ("GET", "/api/ps"),
                ("POST", "/api/show"),
                ("POST", "/api/show"),
                ("GET", "/api/tags"),
                ("GET", "/api/ps"),
            ],
        )
        self.assertEqual(
            json.loads(f.calls[4][2]), {"model": "sha256:" + "a" * 64, "verbose": False}
        )
        for method, path, raw in (
            ("POST", "/api/chat", b"{}"),
            ("POST", "/api/generate", b"{}"),
            ("POST", "/api/pull", b"{}"),
            ("DELETE", "/api/delete", b"{}"),
            ("GET", "/api/tags?host=external", None),
            ("POST", "/api/show", b'{"model":"a","prompt":"private"}'),
        ):
            with self.assertRaises((ValueError, TypeError)):
                ReadOnlyBackendHTTP(
                    connection_factory=lambda *a, **k: self.fail("Connection forbidden")
                ).exchange(method, path, raw)
        self.assertTrue(report["reference_lookup_resolved"])

    def test_transport_is_direct_one_attempt_no_credentials_or_redirect(self):
        connections = []

        def factory(*args, **kwargs):
            item = Connection(*args, **kwargs, response=Response(status=302))
            connections.append(item)
            return item

        reply = ReadOnlyBackendHTTP(connection_factory=factory).exchange(
            "GET", "/api/version", None
        )
        self.assertEqual(reply.status, 302)
        self.assertIsNone(parsed(reply))
        self.assertEqual(len(connections), 1)
        c = connections[0]
        self.assertEqual(c.target, (HOST, PORT))
        self.assertEqual(c.calls[0], "connect")
        self.assertEqual(len(c.calls), 2)
        self.assertEqual(
            set(c.calls[1][1]["headers"]),
            {"Content-Type", "Accept-Encoding", "Connection"},
        )
        self.assertTrue(c.closed and c.response.closed)

    def test_transport_response_budget_and_timeout_close_without_retry(self):
        for mode in ("body", "timeout"):
            with self.subTest(mode=mode):
                c = Connection(
                    HOST,
                    PORT,
                    timeout=1,
                    response=Response(raw=b"X" * (1024 * 1024 + 1)),
                )
                clock_values = iter([0, 0, 0, 0, 5, 5]) if mode == "timeout" else None
                transport = ReadOnlyBackendHTTP(
                    connection_factory=lambda *a, **k: c,
                    clock=(lambda: next(clock_values)) if clock_values else (lambda: 0),
                )
                with self.assertRaises((ValueError, TimeoutError)):
                    transport.exchange("GET", "/api/version", None)
                self.assertTrue(c.closed)
                self.assertEqual(c.calls.count("connect"), 1)

    def test_strict_json_headers_and_bounds(self):
        for reply in (
            Reply(
                200,
                (("Content-Type", "application/json"),),
                b'{"version":"1","version":"2"}',
            ),
            Reply(200, (("Content-Type", "application/json"),), b'{"value":1e999}'),
            Reply(
                200,
                (("Content-Type", "application/json"), ("Content-Encoding", "gzip")),
                b"{}",
            ),
            Reply(
                200,
                (
                    ("Content-Type", "application/json"),
                    ("Content-Type", "application/json"),
                ),
                b"{}",
            ),
            Reply(
                200, (("Content-Type", "application/json"),), b"X" * (1024 * 1024 + 1)
            ),
        ):
            with self.assertRaises((ValueError, TypeError)):
                parsed(reply)

    def test_only_declared_timestamp_exclusions_preserve_raw_hashes(self):
        report, private = Fixture().run()
        self.assertEqual(report["classification"], "lookup_resolved")
        self.assertTrue(report["running_inventory_stable"])
        self.assertEqual(report["show_comparison_excludes"], ["modified_at"])
        self.assertEqual(report["running_comparison_excludes"], ["expires_at"])
        self.assertNotEqual(
            private["frames"][3]["body_sha256"], private["frames"][4]["body_sha256"]
        )
        self.assertEqual(
            Fixture("metadata_mismatch").run()[0]["classification"], "metadata_mismatch"
        )

    def test_private_metadata_and_errors_never_enter_public_projection(self):
        for mode in ("good", "reference404", "version_bad", "timeout"):
            report, private = Fixture(mode).run()
            self.assertNotIn(SENTINEL, json.dumps(report))
            self.assertNotIn(MODEL, json.dumps(report))
            self.assertNotIn("/synthetic/ollama", json.dumps(report))
            self.assertIn("before", private)
        for error in (InspectionRejected(SENTINEL), RuntimeError(SENTINEL)):
            f = Fixture()
            report, _ = inspect_backend(
                MODEL,
                exchange=lambda *a: (_ for _ in ()).throw(error),
                observer=f.observer,
            )
            self.assertNotIn(SENTINEL, json.dumps(report))
            self.assertEqual(report["classification"], "metadata_unmeasured")

    def test_identity_drift_and_unknown_never_become_native_authority(self):
        for mode in ("good", "binary_changed", "tag_changed", "running_changed"):
            report, _ = Fixture(mode).run()
            for name in (
                "signed_identity_qualified",
                "executed_weights_qualified",
                "native_admission",
                "production_activation",
            ):
                self.assertIs(report[name], False)
            self.assertEqual(report["native_execution_compatibility"], "not_tested")
        f = Fixture()
        report, _ = inspect_backend(
            MODEL,
            exchange=f.exchange,
            observer=lambda: (_ for _ in ()).throw(ValueError(SENTINEL)),
        )
        self.assertEqual(report["classification"], "metadata_unmeasured")
        self.assertFalse(report["backend_identity_observed"])

    def test_executable_hashing_is_read_only_and_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / "ollama"
            raw = b"INVENTED-EXECUTABLE-NOT-TO-BE-RUN"
            path.write_bytes(raw)
            path.chmod(0o700)
            before = path.stat()
            value = binary_fingerprint(path)
            self.assertEqual(value["binary_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                binary_fingerprint(path)

    def test_macos_observer_reads_no_arguments_or_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / "ollama"
            path.write_bytes(b"INVENTED-NOT-A-BINARY")
            path.chmod(0o700)
            seen = []

            def run(args, **kwargs):
                seen.append(args)
                if args[0] == "/usr/sbin/lsof":
                    text = "p111\nf3\nn127.0.0.1:11434\n"
                else:
                    text = {
                        "uid=": str(os.getuid()),
                        "lstart=": "invented start",
                        "comm=": str(path),
                    }[args[-1]]
                return SimpleNamespace(returncode=0, stdout=text)

            with (
                patch("backend_reference_inspection.sys.platform", "darwin"),
                patch("backend_reference_inspection.subprocess.run", side_effect=run),
            ):
                value = observe_listener()
            self.assertTrue(value["loopback_only"])
            self.assertEqual(value["pid"], 111)
            self.assertTrue(
                all(
                    "args=" not in args and "command=" not in args and "-e" not in args
                    for args in seen
                )
            )
            with patch("backend_reference_inspection.sys.platform", "unsupported"):
                self.assertIsNone(observe_listener())


if __name__ == "__main__":
    unittest.main()
