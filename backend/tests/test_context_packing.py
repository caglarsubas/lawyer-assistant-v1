"""Exact private-context contracts; all inputs are invented, no provider access."""

import copy
import hashlib
import json

import pytest

from app import context_packing as packing
from app.context_packing import pack_private_context
from app.evidence_prompt import canonical, measure_prompt, quote_messages


def passage(ident="p", text="Ödeme, teslimden sonra yapılır.", document="doc", **values):
    return {"id": ident, "text": text, "document_id": document,
            "document_name": "SYNTHETIC.txt", "document_revision": 2,
            "document_sha256": "a" * 64, "locator": "Satır 1", **values}


def test_exact_unicode_crlf_bytes_and_metadata_are_unchanged():
    originals = [passage(text="😀 İŞÇİ\r\nÖdeme yapılmaz; 1.000,50 TL. IĞDIR’ın koşulu.\r\n")]
    before = copy.deepcopy(originals)
    result = pack_private_context("Ödeme", originals)
    assert originals == before
    selected = result["evidence"][0]
    record = result["manifest"]["selected"][0]
    assert selected["text"] == originals[0]["text"]
    assert record["boundary"] == "full_passage"
    assert record["excerpt_start"] == 0
    assert record["excerpt_end"] == len(originals[0]["text"])
    assert record["original_text_sha256"] == record["excerpt_text_sha256"] == hashlib.sha256(
        originals[0]["text"].encode()).hexdigest()
    assert selected["document_revision"] == 2 and selected["document_sha256"] == "a" * 64
    assert result["manifest"]["offset_unit"] == "unicode_code_points"


def test_document_rounds_keep_distinct_originals_with_equal_text():
    inputs = [passage("a1", "Ödeme teslim.", "a"), passage("a2", "Ödeme teslim.", "a"),
              passage("b1", "Teslim tartışmalı.", "b"), passage("c1", "Tarih bilinmiyor.", "c")]
    result = pack_private_context("Ödeme teslim", inputs)
    assert [item["id"] for item in result["evidence"]] == ["a1", "b1", "c1", "a2"]
    assert result["manifest"]["inventory"]["selected_documents"] == 3
    assert result == pack_private_context("Ödeme teslim", inputs)


def test_shortened_window_preserves_nearby_negation_and_exception_without_rewriting():
    text = "😀 Ön bilgi.\r\n" * 200 + "ÖDEME yapılmaz. Ancak teslim kanıtlanırsa ödeme gerekir.\r\n" + "Son bilgi.\r\n" * 200
    result = pack_private_context("ödeme", [passage(text=text)])
    selected = result["evidence"][0]
    record = result["manifest"]["selected"][0]
    assert "ÖDEME yapılmaz. Ancak teslim kanıtlanırsa ödeme gerekir." in selected["text"]
    assert text[selected["excerpt_start"]:selected["excerpt_end"]] == selected["text"]
    assert 0 < selected["excerpt_start"] < selected["excerpt_end"] < len(text)
    assert record["boundary"] == "punctuation_line_window"
    assert record["original_text_sha256"] != record["excerpt_text_sha256"]


def test_long_sentence_reports_fragment_and_does_not_cut_amount_or_word():
    text = "başlangıç " * 400 + "Ödeme 12.345,67-TL değildir " + "sonuç " * 400
    result = pack_private_context("ödeme", [passage(text=text)], text_byte_budget=200)
    selected = result["evidence"][0]
    assert "Ödeme 12.345,67-TL değildir" in selected["text"]
    assert result["manifest"]["selected"][0]["boundary"] == "token_fragment"
    start, end = selected["excerpt_start"], selected["excerpt_end"]
    assert start == 0 or text[start - 1].isspace()
    assert end == len(text) or text[end].isspace() or text[end - 1].isspace()
    assert len(selected["text"].encode()) <= 200


def test_unsplittable_token_is_omitted_instead_of_fabricating_a_shorter_identifier():
    result = pack_private_context("ödeme", [passage(text="ödeme" + "x" * 2000)])
    assert result["evidence"] == []
    assert result["manifest"]["omission_counts"] == {"no_complete_token": 1}


def test_leading_blank_lines_do_not_nominate_a_whitespace_excerpt():
    result = pack_private_context("hiçbiri", [passage(text="\n" * 2000 + "İçerik.\n")])
    assert "İçerik." in result["evidence"][0]["text"]


def test_literal_escaped_json_question_and_source_fit_the_same_envelope():
    question = '😀 İŞÇİ "\n\\ ödeme' * 20
    # Non-sentence control characters increase JSON bytes; the real serialized
    # envelope, rather than an approximation of raw body size, must still fit.
    inputs = [passage(str(index), 'Ödeme "\t\\ 😀 koşulu. ' * 200, str(index)) for index in range(4)]
    limit = measure_prompt(question, [])["total_upper_bound_units"] + 950
    result = pack_private_context(question, inputs, context_limit=limit)
    manifest = result["manifest"]
    assert result["evidence"]
    assert manifest["prompt"] == measure_prompt(question, result["evidence"])
    assert manifest["prompt"]["total_upper_bound_units"] <= limit
    messages = quote_messages(question, result["evidence"])
    assert json.loads(messages[1]["content"])["question"] == question
    assert manifest["prompt"]["messages_sha256"] == hashlib.sha256(canonical(messages).encode()).hexdigest()
    assert manifest["inventory"]["omitted_passages"] > 0


def test_filename_paths_and_extra_metadata_do_not_consume_model_budget_or_enter_messages():
    item = passage(document_name="PRIVATE NAME " * 4000, private_note="DO NOT DISPATCH",
                   original_path="/never/transmit", arbitrary={"key": "not-a-provider-key"})
    result = pack_private_context("Ödeme", [item])
    payload = json.loads(quote_messages("Ödeme", result["evidence"])[1]["content"])
    assert set(payload) == {"question", "evidence"}
    assert set(payload["evidence"][0]) == {"id", "text", "partial"}
    assert payload["evidence"][0]["partial"] is False
    assert not any(value in canonical(payload) for value in ["PRIVATE NAME", "DISPATCH", "/never", "not-a-provider-key"])
    assert result["evidence"][0]["original_path"] == "/never/transmit"


def test_question_that_does_not_fit_is_recorded_without_silent_question_truncation():
    question = "Ö" * 4000
    result = pack_private_context(question, [passage()], context_limit=2000)
    assert not result["evidence"]
    assert result["manifest"]["omission_counts"] == {"question_exceeds_context": 1}
    assert result["manifest"]["prompt"] == measure_prompt(question, [])
    assert result["manifest"]["provider_use"] == "prepared_only"


@pytest.mark.parametrize("limit", [0, 1, 30, 100, 1799, 1800, 4000])
def test_partition_and_all_byte_budgets_are_explicit(limit):
    inputs = [passage(str(index), ("Ödeme yapılmaz.\n" * (index + 1)), str(index % 3)) for index in range(20)]
    result = pack_private_context("Ödeme", inputs, text_byte_budget=limit)
    manifest = result["manifest"]
    assert len(result["evidence"]) <= 8
    assert sum(len(item["text"].encode()) for item in result["evidence"]) <= limit
    assert all(len(item["text"].encode()) <= 1800 for item in result["evidence"])
    assert manifest["inventory"]["selected_passages"] + manifest["inventory"]["omitted_passages"] == len(inputs)
    assert sum(manifest["omission_counts"].values()) == manifest["inventory"]["omitted_passages"]
    assert len(manifest["selected"]) + len(manifest["omitted"]) == len(inputs)


def test_scan_caps_preserve_unexamined_unknowns_without_whole_inventory_metadata(monkeypatch):
    monkeypatch.setattr(packing, "MAX_CANDIDATES", 3)
    inputs = [passage(str(index)) for index in range(10)]
    result = pack_private_context("Ödeme", inputs)["manifest"]
    assert result["inventory"]["examined_passages"] == 3
    assert result["inventory"]["unexamined_passages"] == 7
    assert result["omission_counts"] == {"scan_budget": 7}
    assert len(result["selected"]) == 3
    assert all(item["passage_id"] in {"0", "1", "2"} for item in result["selected"])


def test_scan_char_budget_never_truncates_the_original_to_claim_complete_scanning(monkeypatch):
    monkeypatch.setattr(packing, "MAX_SCANNED_CODE_POINTS", 5)
    inputs = [passage("a", "Ödeme"), passage("b", "son"), passage("c", "X")]
    result = pack_private_context("Ödeme", inputs)["manifest"]
    assert result["inventory"]["scanned_code_points"] == 5
    assert result["inventory"]["examined_passages"] == 1
    assert result["inventory"]["unexamined_passages"] == 2
    assert result["omission_counts"] == {"scan_budget": 2}


def test_empty_and_zero_evidence_do_not_claim_model_use():
    result = pack_private_context("Ödeme", [passage(text="\n \t")])
    assert result["manifest"]["omission_counts"] == {"empty_text": 1}
    assert pack_private_context("Ödeme", [])["manifest"]["inventory"]["input_passages"] == 0


def test_packing_and_prompt_recipes_are_exact_governance_dependencies():
    from app.governance import dependency_ids

    manifest = pack_private_context("Ödeme", [passage()])["manifest"]
    product = {"snapshots": {"context_pack": {
        "recipe": manifest["recipe"], "prompt_recipe": manifest["prompt"]["recipe"],
        "messages_sha256": manifest["prompt"]["messages_sha256"]}},
        "summary": "Prose never becomes a release dependency"}
    assert dependency_ids(product)["release"] == {"private-evidence-pack-v1", "private-quotes-v2"}


@pytest.mark.parametrize("inputs", [
    [passage(), passage()], [passage(id="")], [passage(id="a" * 129)],
    [passage(text=None)], [passage(text="\ud800")], [passage(document_id=0)], [None],
])
def test_ambiguous_invalid_or_malformed_source_fails_before_any_packing_result(inputs):
    with pytest.raises(ValueError):
        pack_private_context("Ödeme", inputs)


@pytest.mark.parametrize("changes", [
    {"context_limit": 0}, {"context_limit": True}, {"context_limit": "8192"},
    {"text_byte_budget": -1}, {"text_byte_budget": 4001}, {"text_byte_budget": True},
])
def test_unknown_or_invalid_budgets_are_not_coerced(changes):
    with pytest.raises(ValueError):
        pack_private_context("Ödeme", [passage()], **changes)
