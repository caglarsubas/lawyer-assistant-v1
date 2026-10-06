"""Synthetic spelling examples; no claim about legal equivalence or corpus recall."""

import pytest

from app.search_normalization import derived_fields, match_spans, terms, tokens


@pytest.mark.parametrize("text,normalized,folded", [
    ("İŞÇİ IŞIK ıslah işveren", "işçi ışık ıslah işveren", "isci isik islah isveren"),
    ("I\u0307s\u0327c\u0327i", "işçi", "isci"),
    ("ANKARA’NIN İzmir'in", "ankara'nın izmir'in", "ankara'nin izmir'in"),
    ("hâkim hâlî şûra ÇÖĞÜ", "hâkim hâlî şûra çöğü", "hakim hali sura cogu"),
    ("değil değildir hariç olmadıkça", "değil değildir hariç olmadıkça", "degil degildir haric olmadikca"),
    ("E. 2020/00123 K. 2021/9 01.02.2020 -1.250,50 +12,00 %10", "e 2020/00123 k 2021/9 01.02.2020 -1.250,50 +12,00 10", "e 2020/00123 k 2021/9 01.02.2020 -1.250,50 +12,00 10"),
    ("Madde ¹ ① ﬁ", "madde ¹ ① ﬁ", "madde ¹ ① ﬁ"),
])
def test_separate_variants_preserve_critical_words_numbers_and_canonical_turkish(text, normalized, folded):
    result = terms(text)
    assert result["normalized"] == normalized
    assert result["folded"] == folded
    for token in tokens(text):
        assert text[token.start:token.end] == token.original
        assert token.start < token.end


def test_composed_and_decomposed_text_share_normalized_terms_but_keep_distinct_exact_spans():
    composed, decomposed = "İşçi", "I\u0307s\u0327c\u0327i"
    assert terms(composed)["normalized"] == terms(decomposed)["normalized"]
    assert terms(composed)["original"] != terms(decomposed)["original"]
    passage = "😀\n" + decomposed + " — yanlış değil"
    result = match_spans({"text": passage, "title": "SENTETİK"}, "isci")
    assert result["offset_unit"] == "unicode_codepoint"
    match = result["spans"][0]
    assert match["start"] == 2 and match["end"] == 2 + len(decomposed)
    assert passage[match["start"]:match["end"]] == decomposed
    assert match["channels"] == ["lexical_folded"]


def test_lossy_aliases_do_not_replace_original_or_turkish_spelling():
    assert terms("sık")["normalized"] != terms("sik")["normalized"]
    assert terms("sık")["folded"] == terms("sik")["folded"]
    source = {"text": "IŞIK değildir.", "title": "Başlık"}
    before = dict(source)
    result = derived_fields(source)
    assert source == before and result["text_original"] == "IŞIK değildir"
    assert result["text_normalized"] == "ışık değildir"
    assert result["text_folded"] == "isik degildir"


def test_spans_are_bounded_stable_and_never_generated_html_or_rewritten_quotes():
    source = {"text": "İŞÇİ " * 40, "title": "işçi"}
    result = match_spans(source, "işçi")
    assert len(result["spans"]) == 32 and result["truncated"]
    assert all(source[span["field"]][span["start"]:span["end"]] == "İŞÇİ" for span in result["spans"])
    assert match_spans({"text": "İşçi", "title": "Başlık"}, "Başlık")["spans"] == [
        {"field": "title", "start": 0, "end": 6,
         "channels": ["lexical_original", "lexical_normalized", "lexical_folded"]}]
    assert terms(" \n!!! 😀") == dict.fromkeys(("original", "normalized", "folded"), "")


@pytest.mark.parametrize("value", [None, True, [], "a" * 12001])
def test_normalization_rejects_invalid_or_unbounded_text(value):
    with pytest.raises(ValueError):
        terms(value)
