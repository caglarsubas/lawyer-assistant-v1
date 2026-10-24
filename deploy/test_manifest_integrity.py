import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import manifest_integrity_stage as m  # noqa: E402


def events(variant="patched", corrupt=False):
    cases = json.loads(m.locked("manifest_integrity_cases.json", m.CASES_SHA256))["cases"]
    package, prefix = "github.com/ollama/ollama/manifest", "TestFreshFrozenManifestIntegrity/"
    result = []
    for i, c in enumerate(cases):
        mismatch = corrupt and i == 1
        row = {"id": c["id"], "variant": variant, "reader": c["reader"],
               "actual": "mismatched" if mismatch else c["expected"], "store_unchanged": True}
        result.extend([
            {"Action": "output", "Package": package, "Test": prefix + c["id"],
             "Output": "INTEGRITY_RESULT " + json.dumps(row)},
            {"Action": "fail" if mismatch else "pass", "Package": package, "Test": prefix + c["id"]},
        ])
    status = "fail" if corrupt else "pass"
    return result + [{"Action": status, "Package": package, "Test": prefix[:-1]},
                     {"Action": status, "Package": package}]


def wire(rows):
    return b"\n".join(json.dumps(r).encode() for r in rows) + b"\n"


class Contracts(unittest.TestCase):
    def fixture(self, root):
        source, fixtures = root / "source", root / "fixtures"
        source.mkdir()
        fixtures.mkdir()
        raw, changed = b"package manifest\n// before\n", b"package manifest\n// after\n"
        patch_doc = {"path": "manifest/manifest.go", "before_sha256": m.digest(raw),
                     "after_sha256": m.digest(changed), "replacements": [{"before": "before", "after": "after"}]}
        payload = {"manifest/manifest.go": raw, "types/model/name.go": b"package model\n",
                   "envconfig/config.go": b"package envconfig\n", "go.mod": b"original",
                   "LICENSE": b"invented license"}
        for n, b in payload.items():
            p = source / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        lock = {"profiles": {"candidate": {"commit": "0" * 40,
                "compile_paths": [n for n in payload if n.endswith(".go")],
                "source_sha256": {n: m.digest(b) for n, b in payload.items()}}}}
        resources = {"backend_store_sources.json": json.dumps(lock).encode(),
                     "manifest_integrity_patch.json": json.dumps(patch_doc).encode(),
                     "manifest_integrity_cases.json": b"invented frozen case bytes",
                     "manifest_integrity_qualifier.go": b"package manifest\n"}
        for n, b in resources.items():
            (fixtures / n).write_bytes(b)
        pins = {"SOURCE_LOCK_SHA256": m.digest(resources["backend_store_sources.json"]),
                "PATCH_SHA256": m.digest(resources["manifest_integrity_patch.json"]),
                "CASES_SHA256": m.digest(resources["manifest_integrity_cases.json"]),
                "TEST_SHA256": m.digest(resources["manifest_integrity_qualifier.go"])}
        return source, fixtures, pins, raw, changed

    def test_patch_is_exact_hash_bound_and_cannot_reapply(self):
        with tempfile.TemporaryDirectory() as temp:
            source, fixtures, pins, raw, changed = self.fixture(Path(temp).resolve())
            with patch.object(m, "FIXTURES", fixtures), patch.multiple(m, **pins):
                self.assertEqual(m.patched_manifest(raw), changed)
                for wrong in (changed, raw + b" "):
                    with self.assertRaises(m.QualificationRejected):
                        m.patched_manifest(wrong)
            self.assertEqual((source / "manifest/manifest.go").read_bytes(), raw)

    def test_stage_changes_only_manifest_and_preserves_upstream(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, fixtures, pins, raw, changed = self.fixture(root)
            with patch.object(m, "FIXTURES", fixtures), patch.multiple(m, **pins), patch(
                "socket.socket", side_effect=AssertionError("Network prohibited")
            ):
                a = m.stage(source, root / "baseline", "baseline")
                b = m.stage(source, root / "patched", "patched")
            self.assertEqual((source / "manifest/manifest.go").read_bytes(), raw)
            self.assertEqual((root / "baseline/manifest/manifest.go").read_bytes(), raw)
            self.assertEqual((root / "patched/manifest/manifest.go").read_bytes(), changed)
            self.assertEqual(b["modified_upstream_paths"], ["manifest/manifest.go"])
            self.assertEqual([n for n in a["generated_sha256"] if a["generated_sha256"][n] !=
                              b["generated_sha256"][n]], ["manifest/manifest.go"])
            self.assertFalse(b["production_activation"])
            for variant, receipt in [("baseline", a), ("patched", b)]:
                for n, sha in receipt["generated_sha256"].items():
                    p = root / variant / n
                    self.assertEqual(m.digest(p.read_bytes()), sha)
                    self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_source_or_patch_drift_rejects_before_destination(self):
        for field in ("source", "patch"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source, fixtures, pins, _, _ = self.fixture(root)
                p = source / "manifest/manifest.go" if field == "source" else fixtures / "manifest_integrity_patch.json"
                p.write_bytes(p.read_bytes() + b" ")
                with patch.object(m, "FIXTURES", fixtures), patch.multiple(m, **pins):
                    with self.assertRaises(m.QualificationRejected):
                        m.stage(source, root / "stage", "patched")
                self.assertFalse((root / "stage").exists())

    def test_extra_source_links_destinations_and_variants_reject(self):
        for kind in ("extra", "link", "destination", "variant"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source, fixtures, pins, _, _ = self.fixture(root)
                target, variant = root / "stage", "patched"
                if kind == "extra":
                    (source / "manifest/extra.go").write_bytes(b"package manifest\n")
                elif kind == "link":
                    p = source / "manifest/manifest.go"
                    p.rename(source / "original")
                    p.symlink_to(source / "original")
                elif kind == "destination":
                    target.mkdir()
                else:
                    variant = "live"
                with patch.object(m, "FIXTURES", fixtures), patch.multiple(m, **pins):
                    with self.assertRaises(m.QualificationRejected):
                        m.stage(source, target, variant)

    def test_complete_patched_log_has_twenty_frozen_results(self):
        report = m.qualify_log(wire(events()))
        self.assertEqual((report["expected_results"], report["failed_results"]), (20, 0))
        for key in ("installed_backend_qualified", "executed_weights_qualified", "production_activation",
                    "owner_review_completed"):
            self.assertFalse(report[key])

    def test_baseline_negative_and_patched_failure_never_qualify(self):
        report = m.observe_log(wire(events("baseline", True)), "baseline")
        self.assertEqual(report["failed_results"], 1)
        for raw in (wire(events("baseline", True)), wire(events("patched", True))):
            with self.assertRaises(m.QualificationRejected):
                m.qualify_log(raw)

    def test_log_rejects_duplicates_partial_skip_foreign_and_strict_json(self):
        rows = events()
        for candidate in (rows[:-1], rows[2:], rows + rows[:1], rows + rows[-1:],
                          rows + [{"Package": "other", "Action": "pass"}],
                          rows + [{"Package": rows[0]["Package"], "Action": "skip"}]):
            with self.assertRaises(m.QualificationRejected):
                m.qualify_log(wire(candidate))
        for raw in (b"{", b'{"Action":"pass","Action":"fail"}', b"x" * (m.MAX_LOG + 1)):
            with self.assertRaises(m.QualificationRejected):
                m.qualify_log(raw)

    def test_wrong_case_reader_variant_or_mutation_cannot_bind(self):
        for key, value in [("id", "U9999"), ("reader", "other"), ("variant", "baseline"),
                           ("store_unchanged", False), ("actual", "unknown")]:
            rows = events()
            row = json.loads(rows[0]["Output"].split("INTEGRITY_RESULT ")[1])
            row[key] = value
            rows[0]["Output"] = "INTEGRITY_RESULT " + json.dumps(row)
            with self.assertRaises(m.QualificationRejected):
                m.qualify_log(wire(rows))

    def test_completion_must_agree_with_case_result(self):
        rows = events()
        rows[1]["Action"] = "fail"
        with self.assertRaises(m.QualificationRejected):
            m.qualify_log(wire(rows))

    def test_case_and_harness_pins_cannot_be_silently_changed(self):
        for name, pin in [("manifest_integrity_cases.json", "CASES_SHA256"),
                          ("manifest_integrity_qualifier.go", "TEST_SHA256")]:
            with self.assertRaises(m.QualificationRejected):
                m.locked(name, "0" * 64)
            self.assertEqual(m.digest(m.locked(name, getattr(m, pin))), getattr(m, pin))
        cases = json.loads(m.locked("manifest_integrity_cases.json", m.CASES_SHA256))["cases"]
        self.assertEqual(next(c for c in cases if c["fixture"] == "missing_layer")["expected"], "matched")
        self.assertEqual({c["reader"] for c in cases}, {"parse", "data", "file"})

    def test_retained_actual_red_green_logs_keep_the_same_frozen_gate(self):
        baseline = (m.FIXTURES / "manifest_integrity_baseline.jsonl").read_bytes()
        patched = (m.FIXTURES / "manifest_integrity_patched.jsonl").read_bytes()
        red = m.observe_log(baseline, "baseline")
        green = m.qualify_log(patched)
        self.assertEqual((red["expected_results"], red["failed_results"]), (13, 7))
        self.assertEqual((green["expected_results"], green["failed_results"]), (20, 0))
        self.assertTrue(red["scratch_store_unchanged"] and green["scratch_store_unchanged"])
        self.assertEqual([r["id"] for r in red["cases"]], [r["id"] for r in green["cases"]])
        self.assertEqual([r["expected"] for r in red["cases"]], [r["expected"] for r in green["cases"]])
        with self.assertRaises(m.QualificationRejected):
            m.qualify_log(baseline)


if __name__ == "__main__":
    unittest.main()
