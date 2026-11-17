"""Boundaries of severe and uneven PDF scan recovery."""

import subprocess
import sys
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfWriter

from app import pdf_severe_extract as severe
from app.extraction_client import validate_result


def _native_read(text, score=95):
    columns = ["level\tblock_num\tpar_num\tline_num\tconf\ttext"]
    for index, line in enumerate(text.splitlines(), start=1):
        columns.extend(f"5\t1\t1\t{index}\t{score}\t{word}" for word in line.split())
    return text, "\n".join(columns)


@pytest.mark.parametrize(("second", "expected"), [
    (_native_read("Tutar: 2.510,50 TL\nİtiraz edilmedi."), "Tutar: 2.510,50 TL\nİtiraz edilmedi."),
    (_native_read("Tutar: 2.510,80 TL\nİtiraz edilmedi."), ""),
    (_native_read("Tutar: 2.510,50 TL\nİtiraz edildi."), ""),
    (_native_read("Tutar: 2.510,50 TL\nİtiraz edilmedi.", score=69), ""),
])
def test_blank_recovery_requires_native_agreement_on_amount_and_negation(monkeypatch, second, expected):
    base = "Tutar: 2.510,50 TL\nİtiraz edilmedi."
    readings = iter((_native_read(base), second))
    observed = []

    def run(_, extensions, *, lang, timeout):
        assert extensions == ["txt", "tsv"] and lang == "tur+eng"
        observed.append(timeout)
        return next(readings)

    monkeypatch.setattr(severe, "_level_and_deskew", lambda picture, *_: picture.copy())
    with Image.new("L", (128, 128), 200) as picture:
        result = severe._recover_blank(
            SimpleNamespace(run_and_get_multiple_output=run),
            picture, lang="tur+eng", deadline=severe.time.monotonic() + 6,
        )
    assert 0 < observed[1] <= observed[0] <= 6
    assert result == expected


@pytest.mark.parametrize(("layout_token", "accepted"), [(" ", True), ("İtiraz", False)], ids=("space", "word"))
def test_blank_recovery_ignores_only_native_whitespace_rows(monkeypatch, layout_token, accepted):
    text = "Tutar: 2.510,50 TL\nİtiraz edilmedi."
    raw_text, scores = _native_read(text)
    reads = iter(((raw_text + "\n\n", scores + f"\n5\t2\t1\t1\t95\t{layout_token}"), _native_read(text)))
    monkeypatch.setattr(severe, "_level_and_deskew", lambda picture, *_: picture.copy())
    engine = SimpleNamespace(run_and_get_multiple_output=lambda *args, **kwargs: next(reads))

    with Image.new("L", (128, 128), 200) as picture:
        result = severe._recover_blank(engine, picture, lang="tur+eng", deadline=severe.time.monotonic() + 6)

    assert result == (raw_text + "\n\n" if accepted else "")


def test_recovery_cannot_accept_a_late_second_score(monkeypatch):
    timer = SimpleNamespace(now=10.0, scores=0)
    text = "İtiraz edilmedi."

    def check_score(*args):
        timer.scores += 1
        if timer.scores == 2:
            timer.now = 16.1
        return [text.split()]

    monkeypatch.setattr(severe.time, "monotonic", lambda: timer.now)
    monkeypatch.setattr(severe, "_level_and_deskew", lambda picture, *_: picture.copy())
    monkeypatch.setattr(severe, "_confident_lines", check_score)
    engine = SimpleNamespace(run_and_get_multiple_output=lambda *args, **kwargs: _native_read(text))
    with Image.new("L", (128, 128), 200) as picture:
        assert severe._recover_blank(engine, picture, lang="tur+eng", deadline=16.0) == ""
    assert timer.scores == 2


def test_existing_partial_text_survives_and_new_reads_share_deadline(monkeypatch):
    ticks = iter((100.0, 100.2, 105.9))
    monkeypatch.setattr(severe.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(severe, "_is_degraded_scan", lambda _: True)
    context = SimpleNamespace()
    known_partial = "Bakiye tutarı: 37 815,26 TL\nadı."

    def existing(_, picture, *, lang, timeout, allow_terminal_period, recover_partial):
        assert picture is context and lang == "tur+eng" and allow_terminal_period
        assert recover_partial is severe._recover_partial
        assert timeout == pytest.approx(5.8)
        return known_partial

    monkeypatch.setattr(severe, "_recognize", existing)
    assert severe._read_scan(None, context, lang="tur+eng", timeout=6) == (known_partial, True)

    monkeypatch.setattr(severe, "_recognize", lambda *args, **kwargs: "")
    ticks = iter((100.0, 100.2, 105.9))

    def no_preprocessing(*args):
        pytest.fail("Less than 250ms left for recovery")

    monkeypatch.setattr(severe, "_level_and_deskew", no_preprocessing)
    assert severe._read_scan(None, context, lang="tur+eng", timeout=6) == ("", True)


def test_failed_raster_does_not_shift_partial_warning_locator(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.pdf"
    with PdfWriter() as pdf:
        for _ in range(4):
            pdf.add_blank_page(width=100, height=100)
        pdf.write(path)
    before = path.read_bytes()
    visited = []

    def rasterize(command, **kwargs):
        page = int(command[2])
        visited.append(page)
        if page == 1:
            raise subprocess.CalledProcessError(1, command)
        with Image.new("L", (80, 80), page) as raster:
            raster.save(command[-1] + ".png")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", rasterize)
    monkeypatch.setattr(severe, "_is_degraded_scan", lambda picture: picture.getpixel((0, 0)) == 2)
    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(
        run_and_get_multiple_output=lambda picture, *args, **kwargs: (
            "Sentetik kısmi belge." if picture.getpixel((0, 0)) == 2 else "", "",
        ),
    ))
    result = validate_result(severe._extract_pdf(path), ".pdf")
    assert visited == [1, 2, 3] and path.read_bytes() == before
    assert result["passages"] == [{"locator": "Sayfa 2", "text": "Sentetik kısmi belge."}]
    assert [warning for warning in result["warnings"] if "kısmi olabilir" in warning] == [
        severe.PARTIAL_WARNING.format(n=2),
    ]
    assert "Sayfa 1: yerel OCR kullanılamadı." in result["warnings"]
    assert all(f"Sayfa {page}: içerik işlenemedi; bu çalışmaya dahil edilmedi." in result["warnings"]
               for page in (1, 3, 4))


@pytest.mark.parametrize("variation", ["exact", "existing_amount", "disagree", "moved", "faint"])
def test_partial_repair_preserves_prior_numbers_and_requires_two_registered_ink_reads(variation):
    word = severe._Word
    previous = "ar 300,25 TL\n\nBorç kapanmadı."
    old = [[word("ar", 68, (100, 44, 130, 70)), word("300,25", 96, (145, 42, 201, 70)),
            word("TL", 96, (209, 42, 225, 70))],
           [word("Borç", 96, (60, 94, 119, 122)), word("kapanmadı.", 96, (129, 94, 239, 122))]]
    first = [[word("Tarih", 96, (59, 5, 109, 35)), word("18.02.2020", 97, (125, 5, 215, 34))],
             [word("Tutar", 96, (58, 42, 131, 70)),
              old[0][1]._replace(text="900,25") if variation == "existing_amount" else old[0][1], old[0][2]], old[1]]
    second = [line.copy() for line in first]
    if variation == "disagree":
        second[0][1] = second[0][1]._replace(text="18.02.2028")
    if variation == "moved":
        second[0][1] = second[0][1]._replace(box=(125, 150, 215, 174))
    with Image.new("L", (300, 200), 255) as picture:
        paint = ImageDraw.Draw(picture)
        paint.rectangle((62, 9, 79, 28), fill=10)
        paint.rectangle((63, 46, 85, 65), fill=10)
        paint.rectangle((132, 9, 161, 28), fill=223 if variation == "faint" else 10)
        result = severe._reconcile_partial(picture, previous, old, first, second)
    assert result == ("Tarih 18.02.2020\nTutar 300,25 TL\nBorç kapanmadı." if variation == "exact" else previous)


@pytest.mark.parametrize("real_digit", (False, True), ids=("clipped_trace", "visible_digit"))
def test_clipped_prefix_preserves_a_visible_digit(real_digit):
    word = severe._Word
    previous = "4 leme başlığı:"
    anchor = word("başlığı:", 96, (170, 36, 238, 73))
    old = [[word("4", 73, (54, 12, 72, 52)), word("leme", 67, (79, 42, 158, 74)), anchor]]
    restored = word("İnceleme", 97, (43, 34, 158, 73))
    with Image.new("L", (300, 150), 255) as picture:
        draw = ImageDraw.Draw(picture)
        draw.rectangle((56 if real_digit else 54, 31 if real_digit else 48, 65, 51), fill=8)
        draw.rectangle((81, 42, 105, 67), fill=8)
        reconciled = severe._reconcile_partial(picture, previous, old, [[restored, anchor]], [[restored, anchor]])
    assert reconciled == (previous if real_digit else "İnceleme başlığı:")


@pytest.mark.parametrize("shape", ("scuff", "period"))
def test_only_an_elongated_source_scuff_can_remove_a_separate_false_period(shape):
    word = severe._Word
    previous = "İşlem kapanmadı."
    first_word = word("İşlem", 96, (50, 40, 120, 81))
    before = [[first_word, word("kapanmadı.", 81, (129, 40, 257, 81))]]
    tail = word("kapanmadı", 85, (129, 40, 228, 81))
    mark = word(".", 77, (235, 72, 255 if shape == "scuff" else 240, 77))
    with Image.new("L", (300, 150), 255) as picture:
        corners = (mark.box[0], mark.box[1], mark.box[2] - 1, mark.box[3] - 1)
        ImageDraw.Draw(picture).rectangle(corners, fill=8)
        # Keep antialiasing/background inside the claimed punctuation bounds.
        picture.putpixel((mark.box[0], mark.box[1]), 255)
        reconciled = severe._reconcile_partial(picture, previous, before, [[first_word, tail, mark]],
                                                [[first_word, tail, mark]])
    assert reconciled == ("İşlem kapanmadı" if shape == "scuff" else previous)
