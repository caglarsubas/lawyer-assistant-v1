"""Invented citations test syntax and source spans, not real authority identity."""

import pytest

from app.citation_occurrences import derived_fields, matching_occurrences, query_keys, scan


@pytest.mark.parametrize("text,keys", [
    ("E. 2099/00123 K. 2099/0123", ["esas:2099:00123", "karar:2099:0123"]),
    ("Esas Sayısı : 2099 / 17", ["esas:2099:17"]),
    ("ESAS NO:2099/17", ["esas:2099:17"]),
    ("Karar Numarası: 2099/7", ["karar:2099:7"]),
    ("Başvuru Numarası: 2099/8", ["application:2099:8"]),
    ("B. No: 2099/8", ["application:2099:8"]),
    ("Kanun No: 001234", ["law:001234"]),
    ("Kanun Numarası: 999999", ["law:999999"]),
    ("999999 sayılı Kanun'un", ["law:999999"]),
    ("999999 SAYILI KANUNUN", ["law:999999"]),
    ("(E.\u00a02099/8), K. 2099 / 9", ["esas:2099:8", "karar:2099:9"]),
])
def test_labeled_literal_numbers_have_typed_keys_and_unchanged_spans(text, keys):
    parsed = scan(text)
    assert [row["key"] for row in parsed["occurrences"]] == keys
    assert not parsed["truncated"]
    for row in parsed["occurrences"]:
        assert text[row["start"]:row["end"]] == row["literal"]
        assert set(row) == {"kind", "key", "start", "end", "literal"}


@pytest.mark.parametrize("text", [
    "2099/123", "2099/123 E. 2099/124 K.", "E: 2099/1", "2099/123 E.",
    "m. 12", "TBK m. 12", "999999 sayılı Örnek Kanun", "999999 sayılı Yönetmelik",
    "999999 sayılı Kanun Hükmünde Kararname", "Kanun No: 1234 / 7", "Kanun No: 123.4",
    "1,234 sayılı Kanun", "-1234 sayılı Kanun", "Esas Sayısı:\n2099/123",
    "E. 20999/123", "E. 2099/1234567890", "E. 2099/123/4", "E. 2099/123 /4",
    "E. 2099/123.4", "E. 2099/123,4",
    "E. ２０９９/123", "E. 2099/123x", "xE. 2099/123", "https://example.test/E.2099/123",
])
def test_unsupported_or_malformed_forms_do_not_become_partial_identifiers(text):
    assert query_keys(text) == []


def test_label_families_and_leading_zeros_never_conflate_or_create_a_case_pair():
    keys = query_keys("E. 2099/01, K. 2099/01, B. No: 2099/01, E. 2099/1, Kanun No: 01")
    assert len(keys) == 5
    assert "esas:2099:01" in keys and "esas:2099:1" in keys
    assert all(not key.startswith("pair") for key in keys)


def test_title_text_and_astral_offsets_remain_original_and_unresolved():
    source = {"text": "😀\nE. 2099/0012 metni.", "title": "Karar Sayısı: 2099/0012"}
    before = dict(source)
    assert derived_fields(source) == {"citation_keys": ["esas:2099:0012", "karar:2099:0012"]}
    result = matching_occurrences(source, query_keys("Esas No:2099/0012, K.2099/0012"))
    assert result["resolution"] == "unresolved" and result["offset_unit"] == "unicode_codepoint"
    assert result["occurrences"][0]["start"] == 2
    assert {row["field"] for row in result["occurrences"]} == {"text", "title"}
    assert source == before
    for row in result["occurrences"]:
        assert source[row["field"]][row["start"]:row["end"]] == row["literal"]


def test_source_occurrence_overflow_blocks_indexing_and_query_overflow_is_explicit():
    repeated = "E. 2099/1; " * 65
    assert scan(repeated)["truncated"]
    with pytest.raises(ValueError):
        derived_fields({"text": repeated, "title": "SENTETİK"})
    with pytest.raises(ValueError):
        query_keys(repeated)
    with pytest.raises(ValueError):
        query_keys("; ".join(f"E. 2099/{n}" for n in range(17)))
    # A forged index nomination cannot crash otherwise-valid lexical results.
    result = matching_occurrences({"text": repeated, "title": "SENTETİK"}, ["esas:2099:1"])
    assert result["truncated"] and len(result["occurrences"]) == 32


@pytest.mark.parametrize("value", [None, True, {}, "x" * 12001])
def test_invalid_or_unbounded_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        scan(value)
