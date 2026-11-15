"""OCR comparison safeguards use only invented outputs and pixels."""

from types import SimpleNamespace

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

        def plain(_, *, lang, timeout):
            assert lang == "tur+eng" and timeout == 5.5
            return baseline[0]

        monkeypatch.setattr(parser, "_enhance_scan", preprocess)
        assert parser._recognize(SimpleNamespace(image_to_string=plain), picture, lang="tur+eng", timeout=6) == baseline[0]


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
