"""Engineering fixtures only; no source or provision is legally approved here."""

import hashlib
import json

import pytest

from app.provision_candidates import (
    EXTRACTION_VERSION,
    MAX_SPAN,
    CandidateLookup,
    candidate_for_id,
    find_candidates,
    span_details,
)
from app.public_sources import PublicSourceStore


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def package_factory(tmp_path):
    counter = 0

    def build(text, ranges=None, version="engineering-test-source-v1"):
        nonlocal counter
        counter += 1
        directory = tmp_path / str(counter)
        directory.mkdir()
        metadata = {
            "schema_version": "public-source-v1", "title": "Engineering fixture for heading extraction",
            "source_url": "https://www.mevzuat.gov.tr/mevzuatmetin/1.5.6098.pdf",
            "source_version_id": version, "domain": "contracts", "acquired_at": None,
            "published_on": None, "effective_from": None, "effective_until": None,
            "data_classification": "public", "origin": "public_legal_source",
            "contains_private_matter_data": False, "synthetic": False, "raw_media_type": "text/plain",
        }
        ranges = ranges if ranges is not None else [(i, min(i + 10_000, len(text))) for i in range(0, len(text), 10_000)]
        locators = {
            "schema_version": "public-locators-v1", "offset_unit": "unicode_code_points",
            "raw_sha256": sha(text), "text_sha256": sha(text),
            "passages": [{"id": f"p{i}", "start": start, "end": end,
                          "text_sha256": sha(text[start:end]), "locator": f"engineering slice {i}"}
                         for i, (start, end) in enumerate(ranges)],
        }
        for name, value in (("source.json", metadata), ("locators.json", locators)):
            (directory / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        (directory / "text.txt").write_bytes(text.encode("utf-8"))
        (directory / "raw.bin").write_bytes(text.encode("utf-8"))
        store = PublicSourceStore(tmp_path / "public-staging")
        record = store.import_package(metadata_path=directory / "source.json", raw_path=directory / "raw.bin",
                                      text_path=directory / "text.txt", locators_path=directory / "locators.json")
        return store.verified_package(record["id"])

    return build


def test_explicit_types_and_labels_remain_unresolved_machine_proposals(package_factory):
    package = package_factory("MADDE 1- Deneme.\nGeçici Madde 2: Deneme.\nEk Madde 3 / a – Deneme.")
    result = find_candidates(package)
    assert result["extraction_version"] == EXTRACTION_VERSION
    assert result["source_id"] == package.detail["id"]
    assert result["source_version_id"] == package.metadata.source_version_id
    assert result["text_sha256"] == sha(package.text)
    assert result["total"] == 3
    assert result["next_offset"] is None and result["truncated"] is False
    assert [(item["kind"], item["label"], item["number"]) for item in result["items"]] == [
        ("article", "MADDE 1", "1"), ("temporary_article", "GEÇİCİ MADDE 2", "2"),
        ("additional_article", "EK MADDE 3/A", "3/A"),
    ]
    for item in result["items"]:
        assert item["status"] == "machine_proposed" and item["identity_status"] == "unresolved"
        assert item["warnings"] and item["non_whitespace_covered"] is True
        assert set(item) == {"id", "kind", "label", "number", "heading", "proposed_span", "passage_ids",
                            "warnings", "status", "identity_status", "non_whitespace_covered"}
    assert package.metadata.effective_from is None


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r", "\u2028", "\u2029"])
def test_exact_unicode_spans_hashes_and_line_endings_are_not_normalized(package_factory, newline):
    prefix = f"⚖️ I\u0307 Türkçe ıİğĞşŞçÇöÖüÜ.{newline}\u00a0\t "
    text = f"{prefix}Madde\t1/A- Gövde.{newline}{newline}MADDE 2- Son."
    package = package_factory(text)
    first, second = find_candidates(package)["items"]
    assert first["heading"]["start"] == len(prefix)
    assert first["heading"]["text"] == "Madde\t1/A"
    assert first["proposed_span"]["end"] == second["heading"]["start"]
    assert first["proposed_span"]["text"].endswith(newline * 2)
    for item in (first, second):
        for key in ("heading", "proposed_span"):
            span = item[key]
            assert span["text"] == text[span["start"]:span["end"]]
            assert span["sha256"] == sha(span["text"])
    assert package.text == text
    assert package.artifacts["text.txt"] == text.encode()


@pytest.mark.parametrize("text", [
    "Bu metinde MADDE 1- alıntısı var.", "Madde 1 gereğince başvuru yapılır.",
    "MADDE1- Eksik boşluk.", "MADDE 1234567- Uzun numara.", "MADDE 1.5- Ondalık numara.",
    "MADDESİ 1- Farklı sözcük.", "GEÇİCİ\nMADDE\n1- Bölünmüş başlık.", "MADDE 1/AB- Belirsiz ek.",
])
def test_does_not_extract_inline_references_or_unsupported_heading_forms(package_factory, text):
    result = find_candidates(package_factory(text))
    assert result["items"] == [] and result["total"] == 0
    assert result["next_offset"] is None
    assert "farklı biçimli" in result["limitations"][0]


@pytest.mark.parametrize("separator", ["-", "–", "—", ":", ".", ")", " (1)", "\n"])
def test_explicit_heading_delimiters(package_factory, separator):
    assert find_candidates(package_factory(f"MADDE 1{separator} Deneme."))["total"] == 1


def test_repeated_and_quoted_headings_are_kept_separate(package_factory):
    text = 'MADDE 1- İlk.\n“Madde 1- Alıntı.”\nGEÇİCİ MADDE 1- Ayrı tür.'
    package = package_factory(text)
    items = find_candidates(package)["items"]
    assert len({item["id"] for item in items}) == 3
    assert all(any("birden fazla" in warning for warning in item["warnings"]) for item in items[:2])
    assert any("tırnak" in warning for warning in items[1]["warnings"])
    assert not any("birden fazla" in warning for warning in items[2]["warnings"])
    assert items[1]["heading"]["text"] == "Madde 1"


def test_deterministic_ids_bind_exact_package_version_and_heading_offsets(package_factory):
    package = package_factory("MADDE 1- Deneme.\nMADDE 2- Deneme.")
    first = find_candidates(package)["items"][0]
    identity = json.dumps([package.detail["id"], EXTRACTION_VERSION, first["heading"]["start"],
                           first["heading"]["end"]], ensure_ascii=False, separators=(",", ":"))
    assert first["id"] == sha(identity)
    assert candidate_for_id(package, first["id"]) == first
    assert find_candidates(package)["items"][0] == first
    other = package_factory(package.text, version="engineering-test-source-v2")
    assert find_candidates(other)["items"][0]["id"] != first["id"]
    with pytest.raises(ValueError, match="Unknown provision candidate"):
        candidate_for_id(other, first["id"])


@pytest.mark.parametrize("identifier", [None, "", "a", "A" * 64, "f" * 64, "../source", 5])
def test_unknown_candidate_ids_fail_closed(package_factory, identifier):
    with pytest.raises(ValueError, match="Unknown provision candidate"):
        candidate_for_id(package_factory("MADDE 1- Deneme."), identifier)


@pytest.mark.parametrize("offset,limit", [(-1, 20), (501, 20), (True, 20), (0.0, 20), (0, 0),
                                         (0, 21), (0, True), (0, 1.0), ("0", 20)])
def test_page_bounds_reject_bool_and_coercion(package_factory, offset, limit):
    with pytest.raises(ValueError, match="page bounds"):
        find_candidates(package_factory("MADDE 1- Deneme."), offset=offset, limit=limit)


def test_pagination_preserves_ids_and_reports_end(package_factory):
    package = package_factory("\n".join(f"MADDE {i}- Deneme." for i in range(1, 24)))
    first, second = find_candidates(package), find_candidates(package, offset=20)
    assert first["total"] == second["total"] == 23
    assert len(first["items"]) == 20 and first["next_offset"] == 20
    assert len(second["items"]) == 3 and second["next_offset"] is None
    assert second["items"][0] == candidate_for_id(package, second["items"][0]["id"])
    assert find_candidates(package, offset=500)["items"] == []
    assert find_candidates(package, offset=500)["next_offset"] is None


def test_candidate_cap_is_explicit_and_last_span_stops_at_first_omitted_heading(package_factory):
    text = "\n".join(f"MADDE {i}- Deneme." for i in range(1, 503))
    package = package_factory(text)
    page = find_candidates(package, offset=480)
    assert page["total"] == 500 and page["truncated"] is True and page["next_offset"] is None
    assert len(page["items"]) == 20
    last = page["items"][-1]
    assert last["label"] == "MADDE 500"
    assert last["proposed_span"]["end"] == text.index("MADDE 501-")
    assert "500" in page["limitations"][-1]
    omitted_start = text.index("MADDE 501-")
    omitted_id = sha(json.dumps([package.detail["id"], EXTRACTION_VERSION, omitted_start,
                                omitted_start + len("MADDE 501")], separators=(",", ":")))
    with pytest.raises(ValueError):
        candidate_for_id(package, omitted_id)


def test_proposed_span_cap_is_explicit_and_unicode_based(package_factory):
    text = "MADDE 1- " + "ğ" * MAX_SPAN + "\nMADDE 2- Son."
    candidate = find_candidates(package_factory(text))["items"][0]
    assert candidate["proposed_span"]["end"] == MAX_SPAN
    assert len(candidate["proposed_span"]["text"]) == MAX_SPAN
    assert candidate["proposed_span"]["sha256"] == sha(text[:MAX_SPAN])
    assert any("20.000" in warning for warning in candidate["warnings"])


@pytest.mark.parametrize("gap,covered", [("\r\n\t\u00a0", True), ("\r\nX\n", False)])
def test_locator_gaps_distinguish_whitespace_from_unmapped_text(package_factory, gap, covered):
    first, second = "MADDE 1- İlk.", "Devam."
    text = first + gap + second
    package = package_factory(text, ranges=[(0, len(first)), (len(first + gap), len(text))])
    detail = span_details(package, 0, len(text))
    assert detail["passage_ids"] == ["p0", "p1"]
    assert detail["non_whitespace_covered"] is covered
    assert detail["has_locator_gaps"] is True
    candidate = find_candidates(package)["items"][0]
    assert candidate["non_whitespace_covered"] is covered
    assert any("boşluklar" in warning for warning in candidate["warnings"])
    assert any("Boşluk dışındaki" in warning for warning in candidate["warnings"]) is not covered


def test_partial_locator_intersections_only_include_actual_overlap(package_factory):
    package = package_factory("0123456789", ranges=[(0, 3), (4, 7), (8, 10)])
    assert span_details(package, 3, 8) == {
        "span": {"start": 3, "end": 8, "text": "34567", "sha256": sha("34567")},
        "passage_ids": ["p1"], "non_whitespace_covered": False, "has_locator_gaps": True,
    }
    assert span_details(package, 4, 6)["non_whitespace_covered"] is True
    assert span_details(package, 7, 8)["passage_ids"] == []
    assert span_details(package, 7, 8)["non_whitespace_covered"] is False


@pytest.mark.parametrize("start,end", [(True, 3), (0, True), (0.0, 3), (0, 3.0), (-1, 3),
                                       (0, 0), (3, 2), (0, 11), ("0", 3)])
def test_invalid_exact_spans_rejected(package_factory, start, end):
    with pytest.raises(ValueError, match="Invalid provision span"):
        span_details(package_factory("0123456789"), start, end)


def test_manual_span_over_limit_rejected(package_factory):
    package = package_factory("x" * (MAX_SPAN + 1))
    with pytest.raises(ValueError, match="Invalid provision span"):
        span_details(package, 0, MAX_SPAN + 1)


def test_request_local_lookup_parses_once_and_returns_fresh_evidence(package_factory, monkeypatch):
    import app.provision_candidates as adapter

    package = package_factory("MADDE 1- Bir.\nMADDE 2- İki.")
    expected = find_candidates(package)["items"]
    original, calls = adapter._headings, []

    def tracked(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(adapter, "_headings", tracked)
    lookup = CandidateLookup(package)
    for _ in range(10):
        assert lookup.get(expected[0]["id"]) == expected[0]
        assert lookup.get(expected[1]["id"]) == expected[1]
    assert calls == [package.text]
    mutated = lookup.get(expected[0]["id"])
    mutated["proposed_span"]["text"] = "Changed by a caller"
    mutated["warnings"].clear()
    assert lookup.get(expected[0]["id"]) == expected[0]
    assert CandidateLookup(package).get(expected[0]["id"]) == expected[0]
    assert calls == [package.text, package.text]
