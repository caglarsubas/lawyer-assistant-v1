import base64
import copy
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import server_http_qualification as q  # noqa: E402


class Socket:
    def settimeout(self, value):
        assert 0 < value <= 2


class Response:
    def __init__(self, raw=b'{"version":"invented"}', status=200, encoding=""):
        self.raw, self.status, self.encoding = raw, status, encoding

    def getheader(self, name, default=""):
        return self.encoding if name == "Content-Encoding" else "application/json"

    def read1(self, count):
        value, self.raw = self.raw[:count], self.raw[count:]
        return value


class Connection:
    def __init__(self, host, port, timeout):
        self.target, self.timeout, self.sock = (host, port), timeout, Socket()
        self.response, self.closed, self.calls = Response(), False, []

    def connect(self):
        self.calls.append("connect")

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def invented_evidence():
    """Parser-only unit evidence; never an actual server/runtime qualification."""
    spec = q.cases()
    info = {k: char * 64 for k, char in zip(("valid", "legacy", "corrupt", "link", "alias"), "abcde")}
    inv = {"fixture.json": {"sha256": q.digest(q.canonical(info)), "bytes": len(q.canonical(info))}}
    build = {"fixture_inventory_sha256": q.digest(q.canonical(inv)), "binary_sha256": q.BINARY_SHA256}
    rows, frames = [], []

    def frame(ident, method, path, status, request, response):
        return {"id": ident, "method": method, "path": path, "status": status,
                "request_sha256": q.digest(request), "response_sha256": q.digest(response),
                "request_base64": base64.b64encode(request).decode(),
                "response_base64": base64.b64encode(response).decode(), "content_type": "application/json"}

    frames.append(frame("startup", "GET", "/api/version", 200, b"", q.canonical({"version": q.VERSION})))
    for c in spec["cases"]:
        f = c["fixture"]
        value = {"model_info": {"general.architecture": "llama", "general.parameter_count": 0},
                 "details": {"format": "gguf"}}
        if c["expected_status"] >= 400:
            value = {"error": "invented failure"}
            if f == "corrupt_manifest":
                value["error"] = "digest mismatch"
            if f == "direct_link":
                value["error"] = "invalid regular manifest blob"
        elif f == "version":
            value = {"version": q.VERSION}
        elif f == "tags":
            value = {"models": [{"name": q.NAMED, "digest": info["valid"]}]}
        elif f == "empty_inventory":
            value = {"models": []}
        raw = q.canonical(value)
        v = frame(c["id"], c["method"], c["path"], c["expected_status"], q.payload(f, info), raw)
        frames.append(v)
        rows.append({"id": c["id"], "fixture": f, "status": v["status"],
                     "expected_status": c["expected_status"], "matches_expected": True,
                     "request_sha256": v["request_sha256"], "response_sha256": v["response_sha256"]})
    private = {"frames": frames, "fixture_inventory": inv, "fixture_info": info, "invented_only": True}
    wire = q.canonical(private)
    report = {"case_count": 26, "expected_results": 26, "binary_sha256": q.BINARY_SHA256,
              "version_label": q.VERSION, "child_exit_code": 0, "error": None,
              "qualified_metadata_HTTP": True, "fixture_inventory_unchanged": True,
              "observed_child_executable_matches_binary": True, "completion_requests": 0,
              "startup_probe_attempts": 1, "successful_startup_probe_responses": 1,
              "exact_wire_receipt_sha256": q.digest(wire), "cases": rows,
              "request_inventory": [{k: f[k] for k in ("id", "method", "path", "status",
                                     "request_sha256", "response_sha256")} for f in frames]}
    report.update({k: False for k in ("forced_kill", "private_case_inputs", "provider_credentials_used",
                   "native_inference_qualified", "executed_weights_qualified", "installed_backend_qualified",
                   "full_artifact_store_qualified", "production_activation", "owner_review_completed",
                   "independent_trust_confirmed")})
    return report, wire, build


class Contracts(unittest.TestCase):
    def test_fixture_is_metadata_only_and_prepare_is_fresh(self):
        raw = q.minimal_gguf()
        self.assertEqual(raw[:4], b"GGUF")
        version, tensors, keys = struct.unpack("<IQQ", raw[4:24])
        self.assertEqual((version, tensors, keys), (3, 0, 6))
        self.assertEqual(len(raw) % 32, 0)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "fixtures"
            result = q.prepare(root)
            self.assertFalse(result["model_weights"])
            self.assertEqual(result["model_tensors"], 0)
            before = q.inventory(root)
            with self.assertRaises(q.QualificationRejected):
                q.prepare(root)
            self.assertEqual(before, q.inventory(root))

    def test_fixture_rejects_linked_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "real").mkdir()
            (root / "link").symlink_to(root / "real", target_is_directory=True)
            with self.assertRaises(q.QualificationRejected):
                q.prepare(root / "link/new")

    def test_generation_admin_and_external_targets_reject_before_connection(self):
        client = q.MetadataHTTP(lambda *a, **k: self.fail("Connection prohibited"))
        for method, path in [("POST", "/api/chat"), ("POST", "/api/generate"), ("POST", "/api/pull"),
                             ("DELETE", "/api/delete"), ("GET", "http://external.invalid"),
                             ("POST", "/api/show?next=external")]:
            with self.assertRaises(q.QualificationRejected):
                client.exchange(method, path)
        with self.assertRaises(q.QualificationRejected):
            client.exchange("POST", "/api/show", b"x" * 2049)

    def test_transport_uses_one_fixed_loopback_connection_and_exact_wire(self):
        made = []

        def factory(*a, **k):
            c = Connection(*a, **k)
            made.append(c)
            return c

        client = q.MetadataHTTP(factory)
        row, raw = client.exchange("POST", "/api/show", b'{"model":"invented"}', "S0000")
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0].target, ("127.0.0.1", 11579))
        self.assertTrue(made[0].closed)
        self.assertEqual(row["response_sha256"], q.digest(raw))
        self.assertEqual(base64.b64decode(row["request_base64"]), b'{"model":"invented"}')
        self.assertEqual(len(client.frames), 1)

    def test_transport_compression_bounds_deadlines_and_faults_fail_closed(self):
        for response in [Response(encoding="gzip"), Response(b"x" * (q.MAX_REPLY + 1))]:
            c = Connection(q.HOST, q.PORT, 2)
            c.response = response
            with self.assertRaises(q.QualificationRejected):
                q.MetadataHTTP(lambda *a, **k: c).exchange("GET", "/api/version")
            self.assertTrue(c.closed)
        c = Connection(q.HOST, q.PORT, 2)
        with patch.object(q.time, "monotonic", side_effect=[0, 3]), self.assertRaises(q.QualificationRejected):
            q.MetadataHTTP(lambda *a, **k: c).exchange("GET", "/api/version")
        self.assertTrue(c.closed)
        with patch.object(c, "getresponse", side_effect=OSError("invented fault")):
            client = q.MetadataHTTP(lambda *a, **k: c)
            with self.assertRaises(OSError):
                client.exchange("GET", "/api/version")
            self.assertEqual(client.frames, [])

    def test_cases_and_build_are_pinned_and_no_generation_is_in_inventory(self):
        spec = q.cases()
        self.assertEqual(len(spec["cases"]), 26)
        self.assertTrue(all((c["method"], c["path"]) in q.MetadataHTTP.ALLOWED for c in spec["cases"]))
        self.assertEqual(spec["generation_requests_authorized"], 0)
        self.assertEqual(q.build_definition()["binary_sha256"], q.BINARY_SHA256)
        with patch.object(q, "CASES_SHA256", "0" * 64), self.assertRaises(q.QualificationRejected):
            q.cases()
        with patch.object(q, "BUILD_SHA256", "0" * 64), self.assertRaises(q.QualificationRejected):
            q.build_definition()

    def test_runtime_refuses_host_or_implicit_startup(self):
        with patch.dict(os.environ, {"QUALIFICATION_ISOLATED": ""}), patch.object(
            q.subprocess, "Popen", side_effect=AssertionError("No process may start")
        ), self.assertRaises(q.QualificationRejected):
            q.run_campaign()

    def test_complete_unit_wire_binds_all_cases_without_native_claims(self):
        report, wire, build = invented_evidence()
        with patch.object(q, "build_definition", return_value=build):
            result = q.qualify_report(report, wire)
        self.assertEqual(result["metadata_HTTP_cases"], 26)
        for key in ("installed_backend_qualified", "completion_or_executed_weights_qualified",
                    "full_artifact_store_qualified", "production_activation", "owner_review_completed"):
            self.assertFalse(result[key])

    def test_wrong_wire_case_projection_or_partial_result_cannot_qualify(self):
        report, wire, build = invented_evidence()
        variants = []
        for field, value in [("case_count", 25), ("binary_sha256", "0" * 64),
                             ("forced_kill", True), ("native_inference_qualified", True),
                             ("owner_review_completed", True), ("fixture_inventory_unchanged", False)]:
            v = copy.deepcopy(report)
            v[field] = value
            variants.append((v, wire))
        altered = copy.deepcopy(report)
        altered["cases"][0]["status"] = 500
        variants.extend([(altered, wire), (report, wire + b" "), (report, b"{")])
        with patch.object(q, "build_definition", return_value=build):
            for v, raw in variants:
                with self.assertRaises(q.QualificationRejected):
                    q.qualify_report(v, raw)

    def test_metadata_equivalence_rechecks_actual_fields_and_error_support(self):
        report, wire, build = invented_evidence()
        raw = json.loads(wire)
        frame = next(f for f in raw["frames"] if f["id"] == "S2605")
        body = json.loads(base64.b64decode(frame["response_base64"]))
        body["model_info"]["general.architecture"] = "different"
        changed = q.canonical(body)
        frame["response_base64"], frame["response_sha256"] = base64.b64encode(changed).decode(), q.digest(changed)
        wire = q.canonical(raw)
        report["exact_wire_receipt_sha256"] = q.digest(wire)
        with patch.object(q, "build_definition", return_value=build), self.assertRaises(q.QualificationRejected):
            q.qualify_report(report, wire)

    def test_production_source_identity_has_only_the_two_declared_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            a, b = root / "original", root / "derived"
            for target in [a, b]:
                (target / "manifest").mkdir(parents=True)
                (target / "go.mod").write_bytes(b"module invented\n")
            (a / "go.sum").write_text("old v1 h1:old\n")
            (b / "go.sum").write_text("old v1 h1:old\nnew v1 h1:new\n")
            (a / "manifest/manifest.go").write_bytes(b"before")
            (b / "manifest/manifest.go").write_bytes(b"after")
            before, after = q.regular_source_tree(a), q.regular_source_tree(b)
            spec = {"upstream_files": 3, "upstream_tree_sha256": q.digest(q.canonical(before)),
                    "derived_tree_sha256": q.digest(q.canonical(after)), "added_checksum_lines": ["new v1 h1:new"]}
            with patch.object(q, "build_definition", return_value=spec):
                self.assertTrue(q.verify_build_inputs(a, b)["go_mod_unchanged"])
                (b / "extra").write_bytes(b"unexpected")
                with self.assertRaises(q.QualificationRejected):
                    q.verify_build_inputs(a, b)

    def test_source_links_and_unexpected_nodes_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "source").write_bytes(b"invented")
            (root / "link").symlink_to(root / "source")
            with self.assertRaises(q.QualificationRejected):
                q.regular_source_tree(root)

    def test_retained_actual_server_campaign_revalidates_exact_wire(self):
        report = json.loads((q.FIXTURES / "server_http_first_report.json").read_bytes())
        wire = (q.FIXTURES / "server_http_first_wire.json").read_bytes()
        qualified = q.qualify_report(report, wire)
        self.assertEqual(qualified["metadata_HTTP_cases"], 26)
        self.assertTrue(qualified["exact_wire_binding"])
        self.assertEqual(report["child_exit_code"], 0)
        self.assertFalse(report["forced_kill"])
        self.assertEqual(report["completion_requests"], 0)
        self.assertFalse(qualified["completion_or_executed_weights_qualified"])


if __name__ == "__main__":
    unittest.main()
