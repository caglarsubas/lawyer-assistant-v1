"""Boundaries of severe and uneven PDF scan recovery."""

import subprocess
import sys
from types import SimpleNamespace

import pytest
from PIL import Image
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

    def existing(_, picture, *, lang, timeout):
        assert picture is context and lang == "tur+eng"
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
