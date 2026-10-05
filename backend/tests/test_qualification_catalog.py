"""R01 planning records stay bounded, referentially coherent and non-authorizing."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.qualification_catalog import AssetCatalog, SourceCatalog, summarize_catalogs

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def source_data():
    return json.loads((ROOT / "qualification/source-catalog.json").read_text())


@pytest.fixture
def asset_data():
    return json.loads((ROOT / "qualification/asset-catalog.json").read_text())


def test_seed_inventory_preserves_unknowns_and_pending_reviews(source_data, asset_data):
    sources, assets = SourceCatalog.model_validate(source_data), AssetCatalog.model_validate(asset_data)
    summary = summarize_catalogs(sources, assets)
    assert summary["authority"] == "none"
    assert summary["source_family_count"] == 27
    assert summary["asset_count"] == 21
    assert summary["reported_use_observation_counts"] == {"pending": 480, "blocked": 0, "permitted": 0}
    assert summary["source_review_pending_count"] == 81
    assert summary["asset_review_pending_count"] == 42
    assert summary["asset_unknown_version_count"] == 21
    assert summary["asset_unknown_licence_count"] == 21
    assert summary["source_unknown_coverage_denominator_count"] == 27
    assert summary["source_gap_count"] == 27
    assert summary["asset_gap_count"] == 21
    assert {"resmi-gazete", "mevzuat", "tbmm", "aym", "yargitay", "danistay", "uyap-emsal",
            "uyusmazlik", "historical-archives", "national-long-tail"} <= {item.id for item in sources.sources}
    assert not any(key in json.dumps(summary) for key in ("reviewer_id", "https://", "ready_to_publish"))


@pytest.mark.parametrize("target", ["sources", "references"])
def test_duplicate_source_catalog_ids_rejected(source_data, target):
    source_data[target].append(copy.deepcopy(source_data[target][0]))
    with pytest.raises(ValidationError, match="Duplicate"):
        SourceCatalog.model_validate(source_data)


@pytest.mark.parametrize("target", ["assets", "references"])
def test_duplicate_asset_catalog_ids_rejected(asset_data, target):
    asset_data[target].append(copy.deepcopy(asset_data[target][0]))
    with pytest.raises(ValidationError, match="Duplicate"):
        AssetCatalog.model_validate(asset_data)


def test_missing_candidate_reference_rejected(source_data):
    source_data["sources"][0]["reference_ids"].append("absent-reference")
    with pytest.raises(ValidationError, match="Dangling"):
        SourceCatalog.model_validate(source_data)


def test_missing_cross_catalog_source_reference_rejected(source_data, asset_data):
    asset_data["assets"][0]["related_source_family_ids"] = ["absent-family"]
    with pytest.raises(ValueError, match="Dangling"):
        summarize_catalogs(SourceCatalog.model_validate(source_data), AssetCatalog.model_validate(asset_data))


def _report(observation, reference, status):
    observation.update(status=status, reviewer_id="self-reported-reviewer", reviewed_on="2026-10-01",
                       evidence_reference_ids=[reference])


def test_reported_permission_cannot_create_authorization(source_data, asset_data):
    for use in source_data["sources"][0]["use_observations"].values():
        _report(use, "data-strategy", "permitted")
    summary = summarize_catalogs(SourceCatalog.model_validate(source_data), AssetCatalog.model_validate(asset_data))
    assert summary["authority"] == "none"
    assert summary["reported_use_observation_counts"]["permitted"] == 10
    assert summary["source_gap_count"] == 27
    assert not {"authorized", "approved", "ready", "ready_to_publish", "permitted_uses"} & summary.keys()


@pytest.mark.parametrize("field,value", [("reviewer_id", "some-reviewer"), ("reviewed_on", "2026-10-01"),
                                         ("evidence_reference_ids", ["data-strategy"])])
def test_pending_review_cannot_claim_completed_review_metadata(source_data, field, value):
    source_data["sources"][0]["legal_review"][field] = value
    with pytest.raises(ValidationError, match="Pending observations"):
        SourceCatalog.model_validate(source_data)


@pytest.mark.parametrize("status", ["permitted", "blocked"])
@pytest.mark.parametrize("missing", ["reviewer_id", "reviewed_on", "evidence_reference_ids"])
def test_non_pending_use_requires_full_reported_review(source_data, status, missing):
    observation = source_data["sources"][0]["use_observations"]["storage"]
    _report(observation, "data-strategy", status)
    observation[missing] = [] if missing == "evidence_reference_ids" else None
    with pytest.raises(ValidationError, match="Reported decisions require"):
        SourceCatalog.model_validate(source_data)


def test_review_evidence_must_resolve(source_data):
    _report(source_data["sources"][0]["legal_review"], "absent-evidence", "reported_reviewed")
    with pytest.raises(ValidationError, match="Dangling"):
        SourceCatalog.model_validate(source_data)


@pytest.mark.parametrize("value", ["20261001", "2999-10-01", "2026-13-01"])
def test_invalid_review_dates_rejected(source_data, value):
    review = source_data["sources"][0]["legal_review"]
    _report(review, "data-strategy", "reported_reviewed")
    review["reviewed_on"] = value
    with pytest.raises(ValidationError):
        SourceCatalog.model_validate(source_data)


@pytest.mark.parametrize("url", [
    "http://www.tbmm.gov.tr/", "https://user:secret@www.tbmm.gov.tr/", "https://www.tbmm.gov.tr/?api_key=secret",
    "https://www.tbmm.gov.tr/#token", "https://127.0.0.1/", "https://[::1]/", "https://service.local/",
    "https://www.tbmm.gov.tr:8443/", "https://www.tbmm.gov.tr/api-key/secret", "https://www.tbmm.gov.tr/access_token=abc",
    "https://www.tbmm.gov.tr/%3Fapi_key=secret", "https://www.tbmm.gov.tr/%40secret", "https://www.tbmm.gov.tr/%0Asecret",
    "https://www.tbmm.gov.tr/%2573k-longsecrethere", "https://www.tbmm.gov.tr/sk-longsecrethere",
    "https://www.tbmm.gov.tr\\@evil.tld/", "https://127.000.000.001/",
])
def test_reference_urls_cannot_hold_credentials_or_private_routes(source_data, url):
    source_data["references"][1]["locator"] = url
    with pytest.raises(ValidationError):
        SourceCatalog.model_validate(source_data)


@pytest.mark.parametrize("path", ["/tmp/local.md", "docs/../secrets.md", "docs/.env.md", "docs//nested.md",
                                  "docs/ROADMAP.md?api_key=secret"])
def test_repository_references_are_bounded_document_paths(source_data, path):
    source_data["references"][0]["locator"] = path
    with pytest.raises(ValidationError):
        SourceCatalog.model_validate(source_data)


@pytest.mark.parametrize("mutation", ["missing_use", "unknown_use", "unknown_field", "coerced_count", "too_many_sources",
                                     "empty_gap", "control_text", "duplicate_role"])
def test_strict_bounded_contract(source_data, mutation):
    source = source_data["sources"][0]
    if mutation == "missing_use":
        del source["use_observations"]["external_research"]
    elif mutation == "unknown_use":
        source["use_observations"]["cloud_allowed"] = source["use_observations"]["storage"]
    elif mutation == "unknown_field":
        source["authorization"] = True
    elif mutation == "coerced_count":
        source["coverage_denominator"] = "10"
    elif mutation == "too_many_sources":
        source_data["sources"] *= 10
    elif mutation == "empty_gap":
        source["qualification_gaps"] = []
    elif mutation == "control_text":
        source["representations"] = ["injected\ntext"]
    else:
        source["owner_roles"].append(source["owner_roles"][0])
    with pytest.raises(ValidationError):
        SourceCatalog.model_validate(source_data)


def test_asset_measurement_needs_pinned_version_and_digest(asset_data):
    asset = asset_data["assets"][0]
    asset["suitability"] = "reported_measured"
    _report(asset["suitability_review"], "asset-strategy", "reported_reviewed")
    with pytest.raises(ValidationError, match="exact asset version and hash"):
        AssetCatalog.model_validate(asset_data)
    asset.update(version="candidate-v1", artifact_sha256="0" * 64)
    assert AssetCatalog.model_validate(asset_data).assets[0].suitability == "reported_measured"


def test_asset_licence_review_cannot_conceal_unknown_licence(asset_data):
    _report(asset_data["assets"][0]["licence_review"], "asset-strategy", "reported_reviewed")
    with pytest.raises(ValidationError, match="identify the licence"):
        AssetCatalog.model_validate(asset_data)


def test_summary_revalidates_mutated_models(source_data, asset_data):
    sources = SourceCatalog.model_validate(source_data)
    assets = AssetCatalog.model_validate(asset_data)
    sources.sources[0].reference_ids.append("does-not-exist")
    with pytest.raises(ValidationError, match="Dangling"):
        summarize_catalogs(sources, assets)


def test_summary_never_echoes_confidential_candidate_identifiers(source_data, asset_data):
    fake_credential_id = "sk-" + "a" * 40
    confidential_case_id = "confidentialcaseid-client-allegation"
    original_source_id = source_data["sources"][0]["id"]
    source_data["sources"][0]["id"] = fake_credential_id
    asset_data["assets"][0]["id"] = confidential_case_id
    for asset in asset_data["assets"]:
        asset["related_source_family_ids"] = [
            fake_credential_id if value == original_source_id else value
            for value in asset["related_source_family_ids"]
        ]
    sources, assets = SourceCatalog.model_validate(source_data), AssetCatalog.model_validate(asset_data)
    assert sources.sources[0].id == fake_credential_id
    assert assets.assets[0].id == confidential_case_id
    summary = summarize_catalogs(sources, assets)
    serialized = json.dumps(summary)
    assert fake_credential_id not in serialized
    assert confidential_case_id not in serialized
    assert "source_gap_ids" not in summary and "asset_gap_ids" not in summary
    assert summary["source_gap_count"] == 27
    assert summary["asset_gap_count"] == 21
