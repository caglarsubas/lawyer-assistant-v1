"""Recheck the retained disposable campaign without regenerating its outcomes."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from qualify_recipient_observations import CASES, NEW  # noqa: E402


def test_frozen_recipient_campaign_preserves_source_versions_and_original_histories():
    report = json.loads((ROOT / "docs/evidence/recipient-observation-2026-11-05.json").read_bytes())
    prior_path = ROOT / "docs/evidence/metadata-handoff-2026-11-05.json"
    prior = json.loads(prior_path.read_bytes())
    assert report["status"] == "qualified" and not report["production_activation"] and not report["legal_qualification"]
    assert report["prior_metadata_report_sha256"] == hashlib.sha256(prior_path.read_bytes()).hexdigest()
    assert len(report["source_sha256"]) == 790 and len(prior["source_sha256"]) == 785
    assert set(report["source_sha256"]) - set(prior["source_sha256"]) == set(NEW)
    for name, digest in report["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert all(report["source_sha256"][name] == digest for name, digest in prior["source_sha256"].items())
    evidence = report["evidence"]
    assert len(evidence["cases"]) == len(CASES) == 26
    assert [row["id"] for row in evidence["cases"]] == list(CASES)
    assert all(row["state"] == "verified" for row in evidence["cases"])
    assert report["case_plan_sha256"] == hashlib.sha256(json.dumps(CASES, separators=(",", ":")).encode()).hexdigest()
    assert evidence["isolated_account_contexts"] == 8 and evidence["original_input_reviews_retained"] == 4
    assert evidence["original_metadata_packages"] == evidence["declared_fixture_session_deletions"] == 2
    assert evidence["fixture_signed_review_sets"] == 10 and evidence["disposable_review_keys"] == 20
    assert evidence["service_reads"] >= 20 and evidence["service_writes"] == 0
    assert evidence["original_versions_and_histories_exact"] and evidence["account_changes_only_declared_session_deletions"]
    assert evidence["profile_markers_exact"] and not evidence["retention_authorized"]
    assert not evidence["genuine_acknowledgement_verified"] and not evidence["durability_qualified"]
