"""OCR comparison safeguards use only invented outputs and pixels."""

from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from app import pdf_scan_extract as parser

HEADER = "level\tblock_num\tpar_num\tline_num\tconf\ttext\n"


def reading(*lines):
    text = "\n".join(" ".join(word for word, _ in line) for line in lines)
    scores = HEADER + "".join(
        f"5\t1\t1\t{number}\t{confidence}\t{word}\n"
        for number, line in enumerate(lines, 1)
        for word, confidence in line
    )
    return text, scores


def test_enhanced_requires_same_numeric_tokens_lines_and_meaningful_confidence():
    baseline = reading([("Tarih;", 80), ("17.09.2026", 88)], [("500,18", 72), ("Tİ.", 42)])
    accepted = [("Tarih:", 94), ("17.09.2026", 99)], [("500,18", 97), ("TL.", 98)]
    assert parser._prefer_enhanced(baseline, reading(*accepted))
    assert not parser._prefer_enhanced(baseline, reading(accepted[0], [("500,81", 97), ("TL.", 98)]))
    assert not parser._prefer_enhanced(baseline, reading(accepted[0], [("500,18", 97), ("TL.", 50)]))
    assert not parser._prefer_enhanced(baseline, reading([*accepted[0], *accepted[1]]))
    assert not parser._prefer_enhanced(baseline, reading(accepted[0], [*accepted[1], ("değil", 99)]))
    assert not parser._prefer_enhanced(("", HEADER), reading(*accepted))


def test_ocr_timeout_and_inconsistent_scores_preserve_original(monkeypatch):
    class Clock:
        now = 100.0

        def __call__(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr(parser.time, "monotonic", clock)
    monkeypatch.setattr(parser, "_enhance_scan", lambda source: source.copy())

    baseline = reading([("Tİ.", 42)])
    calls = []

    def recognize(_, outputs, *, lang, timeout):
        assert outputs == ["txt", "tsv"] and lang == "tur+eng"
        calls.append(timeout)
        if len(calls) == 1:
            clock.now += 2
            return baseline
        raise RuntimeError("hypothetical second pass timeout")

    with Image.new("L", (30, 30), 255) as picture:
        api = SimpleNamespace(run_and_get_multiple_output=recognize)
        assert parser._recognize(api, picture, lang="tur+eng", timeout=6) == baseline[0]
        assert calls == [6, 4]
        candidates = iter((baseline, ("TL.", reading([("EL.", 98)])[1])))
        api.run_and_get_multiple_output = lambda *args, **kwargs: next(candidates)
        assert parser._recognize(api, picture, lang="tur+eng", timeout=6) == baseline[0]
        candidates = iter((baseline, ("TL.",)))
        api.run_and_get_multiple_output = lambda *args, **kwargs: next(candidates)
        assert parser._recognize(api, picture, lang="tur+eng", timeout=6) == baseline[0]

        def preprocess(_):
            clock.now += 0.5
            return None

        def plain(_, outputs, *, lang, timeout):
            assert outputs == ["txt", "tsv"] and lang == "tur+eng" and timeout == 5.5
            return baseline

        monkeypatch.setattr(parser, "_enhance_scan", preprocess)
        assert parser._recognize(SimpleNamespace(run_and_get_multiple_output=plain), picture,
                                 lang="tur+eng", timeout=6) == baseline[0]

        def english(_, *, lang, timeout):
            assert lang == "eng" and timeout == 5.5
            return "INVOICE"

        assert parser._recognize(SimpleNamespace(image_to_string=english), picture,
                                 lang="eng", timeout=6) == "INVOICE"


def test_enhancement_is_local_to_moderately_faint_raster():
    with Image.new("L", (500, 700), 255) as picture:
        assert parser._enhance_scan(picture) is None
        draw = ImageDraw.Draw(picture)
        draw.rectangle((40, 100, 320, 130), fill=140)
        before = picture.tobytes()
        with parser._enhance_scan(picture) as enhanced:
            assert enhanced.getextrema()[0] < 140
        assert picture.tobytes() == before
        draw.rectangle((40, 100, 320, 130), fill=218)
        assert parser._enhance_scan(picture) is None


@pytest.mark.parametrize("change", [
    "none", "missing_dot", "wrong_glyph", "altered_id", "ambiguous_ink", "moved_box", "late",
])
def test_dotted_i_retry_requires_source_dots_and_only_preserves_exact_aligned_text(monkeypatch, change):
    baseline = "KIR  000783\n\n  IKI.\n"
    calls = []
    moment = [100.0]
    monkeypatch.setattr(parser.time, "monotonic", lambda: moment[0])
    monkeypatch.setattr(parser, "_enhance_scan", lambda _: None)

    def word_data(current):
        rows = [
            (1, 5, 5, 26, 20, "KİR" if current == "wrong_glyph" else "KIR"),
            (1, 35, 5, 20, 20, "000873" if current == "altered_id" else "000783"),
            (2, 4 if current == "moved_box" else 5, 35, 34, 26, "IKI." if current == "original" else "İKİ."),
        ]
        return "level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n" + "".join(
            f"5\t1\t1\t{line}\t{x}\t{y}\t{w}\t{h}\t97\t{word}\n" for line, x, y, w, h, word in rows
        )

    def primary(_, outputs, *, lang, timeout):
        calls.append((outputs, lang, timeout))
        moment[0] += 4.5
        return baseline, word_data("original")

    def alternate(_, *, lang, config, timeout):
        calls.append((lang, config, timeout))
        if change == "late":
            moment[0] += 1.51
        return word_data(change)

    with Image.new("L", (100, 100), 255) as picture:
        draw = ImageDraw.Draw(picture)
        for x, right in [(5, 10), (15, 19), (23, 30)]:
            draw.rectangle((x, 5, right, 22), fill=10)
        for x, right in [(5, 10), (14, 20), (24, 29)]:
            draw.rectangle((x, 41, right, 60), fill=10)
        draw.rectangle((34, 58, 37, 60), fill=10)
        draw.rectangle((7, 35, 9, 37), fill=10)
        if change != "missing_dot":
            draw.rectangle((26, 35, 28, 37), fill=10)
        if change == "ambiguous_ink":
            draw.line((9, 42, 15, 42), fill=10)
        before = picture.tobytes()
        engine = SimpleNamespace(run_and_get_multiple_output=primary, image_to_data=alternate)
        got = parser._recognize(engine, picture, lang="tur+eng", timeout=6)
        assert got == ("KIR  000783\n\n  İKİ.\n" if change == "none" else baseline)
        assert picture.tobytes() == before
    assert calls == [(["txt", "tsv"], "tur+eng", 6), ("tur+eng", "--psm 6", 1.5)]


@pytest.mark.parametrize("case", [
    "confirmed", "missing", "multiple", "elongated", "raised", "low", "touching", "already",
    "clean", "numeric_tail", "moved_box", "changed_number", "separate_period", "late",
])
def test_terminal_period_requires_compact_source_ink_and_exact_bounded_line_read(monkeypatch, case):
    last_word = "741" if case == "numeric_tail" else "tamamlandı"
    end = "." if case == "already" else ""
    text = f"Belge 000741\n\n  Kayıt 741 {last_word}{end}"
    whitespace = "  \r\n\n\t"
    baseline = text + whitespace
    calls = []
    now = [100.0]
    monkeypatch.setattr(parser.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(parser, "_enhance_scan", lambda _: None)

    def tsv(*lines):
        header = "level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        return header + "".join(
            f"5\t1\t1\t{number}\t{x}\t{y}\t{w}\t{h}\t97\t{word}\n"
            for number, words in enumerate(lines, 1) for x, y, w, h, word in words
        )

    def primary(_, outputs, *, lang, timeout):
        calls.append((outputs, lang, timeout))
        now[0] += 4.75
        return baseline, tsv([(30, 5, 25, 25, "Belge"), (63, 5, 30, 25, "000741")],
                             [(30, 46, 25, 29, "Kayıt"), (63, 46, 15, 29, "741"),
                              (94, 45, 46, 30, last_word + end)])

    def alternate(strip, *, lang, config, timeout):
        assert strip.size == (134, 54)
        calls.append((lang, config, timeout))
        if case == "late":
            now[0] += 1.26
        words = [(12, 13, 25, 29, "Kayıt"), (45, 13, 15, 29, "742" if case == "changed_number" else "741"),
                 (83 if case == "moved_box" else 76, 12, 55, 30,
                  last_word if case == "separate_period" else last_word + ".")]
        if case == "separate_period":
            words.append((126, 37, 5, 5, "."))
        return tsv(words)

    with Image.new("L", (220, 120), 255) as picture:
        draw = ImageDraw.Draw(picture)
        draw.rectangle((94, 45, 139, 74), fill=10)
        if case != "missing":
            shape = {
                "elongated": (143, 72, 151, 74), "raised": (144, 50, 148, 54),
                "low": (144, 76, 148, 80), "touching": (139, 70, 148, 74),
            }.get(case, (144, 70, 148, 74))
            draw.rectangle(shape, fill=10)
        if case == "multiple":
            draw.point((149, 75), fill=10)  # Disconnected with contiguous row and column projections.
        original = picture.tobytes()
        engine = SimpleNamespace(run_and_get_multiple_output=primary, image_to_data=alternate)
        got = parser._recognize(engine, picture, lang="tur+eng", timeout=6, allow_terminal_period=case != "clean")
        assert got == (text + "." + whitespace if case == "confirmed" else baseline)
        assert picture.tobytes() == original
    expected = [(["txt", "tsv"], "tur+eng", 6)]
    if case in {"confirmed", "moved_box", "changed_number", "separate_period", "late"}:
        expected.append(("tur+eng", "--psm 7", 1.25))
    assert calls == expected
