import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import qualify_backend_store as q  # noqa: E402

CASES = json.loads((q.FIXTURES / "backend_store_cases.json").read_text())["cases"]


def events(profile="candidate"):
    package = "github.com/ollama/ollama/qualifier"
    result = []
    for case in CASES:
        test = "TestFrozenReferences/" + case["id"]
        row = {"id": case["id"], "profile": profile, "actual": case["expected"][profile],
               "store_unchanged": True}
        result.extend([
            {"Action": "output", "Package": package, "Test": test,
             "Output": "QUALIFIER_RESULT " + json.dumps(row)},
            {"Action": "pass", "Package": package, "Test": test},
        ])
    return result + [{"Action": "pass", "Package": package}]


def wire(rows):
    return b"\n".join(json.dumps(r).encode() for r in rows) + b"\n"


class Contracts(unittest.TestCase):
    def test_both_complete_logs_match_frozen_results(self):
        for profile in ("release", "candidate"):
            result = q.check_log(wire(events(profile)), profile)
            self.assertEqual(result["expected_results"], 15)
            self.assertTrue(result["store_unchanged"])
            self.assertFalse(result["installed_backend_qualified"])
            self.assertFalse(result["executed_weights_qualified"])
            self.assertFalse(result["production_activation"])

    def test_partial_failed_skipped_duplicate_or_foreign_logs_reject(self):
        original = events()
        variants = [original[:-1], original[2:], original + original[:1], original + original[-1:]]
        for action in ("fail", "skip"):
            variants.append(original + [{"Action": action, "Package": original[-1]["Package"]}])
        variants.append(original + [{"Action": "pass", "Package": "foreign"}])
        for rows in variants:
            with self.subTest(rows=len(rows)), self.assertRaises(q.QualificationRejected):
                q.check_log(wire(rows), "candidate")

    def test_wrong_profile_result_identity_or_mutation_reject(self):
        for key, value in [("id", "Q9999"), ("profile", "release"), ("actual", "invented"),
                           ("store_unchanged", False), ("unexpected", "field")]:
            rows = events()
            row = json.loads(rows[0]["Output"].split("QUALIFIER_RESULT ")[1])
            row[key] = value
            rows[0]["Output"] = "QUALIFIER_RESULT " + json.dumps(row)
            with self.subTest(key=key), self.assertRaises(q.QualificationRejected):
                q.check_log(wire(rows), "candidate")

    def test_bounded_strict_json_and_success_event_binding(self):
        for raw in [b"{", b"{}\n", b"x" * (q.MAX_LOG + 1), b'{"Action":"pass","Action":"fail"}']:
            with self.assertRaises(q.QualificationRejected):
                q.check_log(raw, "candidate")
        rows = events()
        rows[0]["Test"] = "TestFrozenReferences/Q9999"
        with self.assertRaises(q.QualificationRejected):
            q.check_log(wire(rows), "candidate")

    def test_read_regular_rejects_links_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / "source"
            source.write_bytes(b"invented")
            (root / "link").symlink_to(source)
            for p, limit in [(root / "link", 100), (source, 1)]:
                with self.assertRaises(q.QualificationRejected):
                    q.read_regular(p, limit)
            os.link(source, root / "hard")
            with self.assertRaises(q.QualificationRejected):
                q.read_regular(source, 100)

    def fixture(self, root):
        source, fixtures = root / "source", root / "fixtures"
        source.mkdir()
        fixtures.mkdir()
        payload = {"go.mod": b"invented module", "LICENSE": b"invented license",
                   "server/routes.go": b"not compiled", "server/images.go": b"not compiled"}
        payload.update({p: b"package invented\n" for p in (
            "envconfig/config.go", "manifest/manifest.go", "types/model/name.go")})
        for n, raw in payload.items():
            p = source / n
            p.parent.mkdir(exist_ok=True, parents=True)
            p.write_bytes(raw)
        entry = {"commit": "0" * 40, "upstream_go_requirement": "1.26.10",
                 "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in payload.items()},
                 "compile_paths": [n for n in payload if n.endswith(".go") and not n.startswith("server/")]}
        (fixtures / "backend_store_sources.json").write_text(json.dumps({
            "profiles": {"candidate": entry}, "build_scope": "invented"}))
        (fixtures / "backend_store_qualifier.go").write_bytes(b"package qualifier\n")
        (fixtures / "backend_store_cases.json").write_text(json.dumps({"cases": CASES}))
        return source, fixtures

    def test_stage_copies_exact_inventory_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, fixtures = self.fixture(root)
            target = root / "stage"
            with patch.object(q, "FIXTURES", fixtures), patch("socket.socket", side_effect=AssertionError):
                receipt = q.build(source, target, "candidate")
            self.assertFalse(receipt["server_built"])
            self.assertFalse(receipt["model_files_copied"])
            self.assertEqual(receipt["native_inference_calls"], 0)
            self.assertFalse((target / "server").exists())
            self.assertEqual((target / "go.mod").read_bytes(), q.MODULE)
            self.assertEqual(set(receipt["generated_sha256"]), {
                str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()})
            for n, sha in receipt["generated_sha256"].items():
                self.assertEqual(hashlib.sha256((target / n).read_bytes()).hexdigest(), sha)
                self.assertEqual((target / n).stat().st_mode & 0o777, 0o600)

    def test_source_drift_or_extra_package_fails_before_staging(self):
        for variant in ("hash", "extra"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source, fixtures = self.fixture(root)
                (source / ("manifest/manifest.go" if variant == "hash" else "manifest/extra.go")).write_bytes(b"changed")
                with patch.object(q, "FIXTURES", fixtures), self.assertRaises(q.QualificationRejected):
                    q.build(source, root / "stage", "candidate")
                self.assertFalse((root / "stage").exists())

    def test_destination_profile_and_inventory_are_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, fixtures = self.fixture(root)
            existing = root / "existing"
            existing.mkdir()
            (root / "linked").symlink_to(existing, target_is_directory=True)
            with patch.object(q, "FIXTURES", fixtures):
                for target, profile in [(existing, "candidate"), (root / "linked" / "new", "candidate"),
                                        (root / "new", "unknown")]:
                    with self.assertRaises(q.QualificationRejected):
                        q.build(source, target, profile)

    def test_colon_alias_and_missing_layer_never_establish_immutability(self):
        by_fixture = {c["fixture"]: c["expected"] for c in CASES}
        self.assertEqual(by_fixture["colon_blob"], {"release": "missing", "candidate": "missing"})
        self.assertEqual(by_fixture["colon_alias"], {"release": "mismatched", "candidate": "mismatched"})
        self.assertEqual(by_fixture["missing_layer_named"], {"release": "matched", "candidate": "matched"})
        lock = json.loads((q.FIXTURES / "backend_store_sources.json").read_text())
        retained = json.loads((q.FIXTURES / "immutable_ollama_source.json").read_text())
        candidate = lock["profiles"]["candidate"]
        self.assertEqual(candidate["commit"], retained["commit"])
        for name, sha in retained["source_sha256"].items():
            self.assertEqual(candidate["source_sha256"][name], sha)

    def test_retained_actual_candidate_failure_cannot_be_accepted(self):
        raw = (q.FIXTURES / "backend_store_rejected_candidate.jsonl").read_bytes()
        rows = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual(sum(e.get("Action") == "pass" and e.get("Test", "").startswith(
            "TestFrozenReferences/") for e in rows), 14)
        found = [json.loads(e["Output"].split("QUALIFIER_RESULT ", 1)[1]) for e in rows
                 if "QUALIFIER_RESULT " in e.get("Output", "")]
        self.assertEqual(len(found), 15)
        self.assertEqual(next(r for r in found if r["id"] == "Q2412"), {
            "id": "Q2412", "profile": "candidate", "actual": "mismatched", "store_unchanged": True})
        self.assertEqual(next(c for c in CASES if c["id"] == "Q2412")["expected"]["candidate"], "rejected")
        with self.assertRaises(q.QualificationRejected):
            q.check_log(raw, "candidate")


if __name__ == "__main__":
    unittest.main()
