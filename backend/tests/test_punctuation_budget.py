"""Deterministic admission and partial-result contracts; no private data or OCR calls."""

import math
from types import SimpleNamespace

import pytest
from PIL import Image

from app import ocr_punctuation_amount as amount

BOUNDS = (10, 10, 60, 40)
NATIVE = "8 8 8 20 25 0"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr(amount, "time", SimpleNamespace(monotonic=value))
    return value


@pytest.fixture
def page():
    with Image.new("L", (80, 60), 255) as image:
        yield image


@pytest.mark.parametrize("remaining", [0, .12, .35, math.nextafter(.47, -math.inf)])
def test_glyph_does_not_start_below_native_minimum_plus_reserve(page, clock, monkeypatch, remaining):
    calls = []
    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", lambda *a, **kw: calls.append(kw) or NATIVE)
    with pytest.raises(amount.GlyphBudgetExhausted):
        amount.read_amount_character_boxes(page, BOUNDS, remaining)
    assert calls == []


@pytest.mark.parametrize("contrast", [False, True])
def test_exact_glyph_admission_boundary_reserves_processing_time(page, clock, monkeypatch, contrast):
    calls = []
    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", lambda *a, **kw: calls.append(kw) or NATIVE)
    glyphs = amount.read_amount_character_boxes(page, BOUNDS, .47, contrast=contrast)
    assert glyphs == [("8", (11, 22, 23, 39))]
    assert len(calls) == 1 and calls[0]["timeout"] == pytest.approx(.35)
    assert calls[0]["lang"] == "tur+eng" and calls[0]["config"] == "--psm 8"


@pytest.mark.parametrize("contrast", [False, True])
def test_glyph_admission_is_rechecked_after_padding(page, clock, monkeypatch, contrast):
    calls = []
    expand = amount.ImageOps.expand

    def consume_preparation(*args, **kwargs):
        result = expand(*args, **kwargs)
        clock.now = .02
        return result

    monkeypatch.setattr(amount.ImageOps, "expand", consume_preparation)
    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", lambda *a, **kw: calls.append(kw) or NATIVE)
    with pytest.raises(amount.GlyphBudgetExhausted):
        amount.read_amount_character_boxes(page, BOUNDS, .48, contrast=contrast)
    assert calls == []


def test_glyph_native_cap_is_unchanged_when_budget_is_sufficient(page, clock, monkeypatch):
    calls = []
    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", lambda *a, **kw: calls.append(kw) or NATIVE)
    assert amount.read_amount_character_boxes(page, BOUNDS, 2)
    assert len(calls) == 1 and calls[0]["timeout"] == .65


@pytest.mark.parametrize("profile", [None, (18, 7, 2)])
def test_rows_do_not_start_after_preparation_spends_the_minimum_window(page, clock, monkeypatch, profile):
    calls = []
    crop = Image.Image.crop

    def consume_crop(image, *args, **kwargs):
        result = crop(image, *args, **kwargs)
        clock.now = .01
        return result

    monkeypatch.setattr(Image.Image, "crop", consume_crop)
    monkeypatch.setattr(amount.pytesseract, "image_to_data", lambda *a, **kw: calls.append(kw) or "synthetic")
    with pytest.raises(amount.OcrBudgetExhausted):
        amount.read_rows(page, BOUNDS, mode=3, profile=profile, deadline=.30)
    assert calls == []


def test_exact_row_boundary_and_full_budget_keep_native_caps(page, clock, monkeypatch):
    calls = []
    result = [SimpleNamespace(text="SYNTHETIC", box=(11, 12, 30, 20))]
    monkeypatch.setattr(amount.pytesseract, "image_to_data", lambda *a, **kw: calls.append(kw) or "synthetic")
    monkeypatch.setattr(amount.severe, "_partial_words", lambda *a: result)
    assert amount.read_rows(page, BOUNDS, mode=3, profile=None, deadline=.30) is result
    assert calls[-1]["timeout"] == .25
    assert amount.read_rows(page, BOUNDS, mode=3, profile=None, deadline=2) is result
    assert calls[-1]["timeout"] == 1.20 and len(calls) == 2


@pytest.mark.parametrize("stage", ["entry", "native", "parse"])
def test_row_budget_is_explicit_at_entry_native_and_parse_completion(page, clock, monkeypatch, stage):
    calls = []
    parsed = []

    def native(*args, **kwargs):
        calls.append(kwargs)
        if stage == "native":
            clock.now = 1
        return "synthetic"

    def parse(*args):
        parsed.append(True)
        if stage == "parse":
            clock.now = 1
        return ["SYNTHETIC completed too late"]

    monkeypatch.setattr(amount.pytesseract, "image_to_data", native)
    monkeypatch.setattr(amount.severe, "_partial_words", parse)
    with pytest.raises(amount.OcrBudgetExhausted):
        amount.read_rows(page, BOUNDS, mode=3, profile=None, deadline=.29 if stage == "entry" else 1)
    assert len(calls) == (0 if stage == "entry" else 1)
    assert len(parsed) == (1 if stage == "parse" else 0)


@pytest.mark.parametrize("late", [False, True])
def test_native_row_error_is_not_a_timely_blank_or_late_success(page, clock, monkeypatch, late):
    def native(*args, **kwargs):
        clock.now = 1 if late else .1
        raise RuntimeError("synthetic native failure")

    monkeypatch.setattr(amount.pytesseract, "image_to_data", native)
    expected = amount.OcrBudgetExhausted if late else RuntimeError
    with pytest.raises(expected) as raised:
        amount.read_rows(page, BOUNDS, mode=3, profile=None, deadline=1)
    if not late:
        assert type(raised.value) is RuntimeError


def test_timely_blank_row_read_remains_empty_not_a_budget_failure(page, clock, monkeypatch):
    monkeypatch.setattr(amount.pytesseract, "image_to_data", lambda *a, **kw: "")
    monkeypatch.setattr(amount.severe, "_partial_words", lambda *a: [])
    assert amount.read_rows(page, BOUNDS, mode=3, profile=None, deadline=1) == []


def test_source_cell_preparation_budget_is_not_reported_as_absent_geometry(page, clock):
    calls = []

    def locate(*args):
        calls.append(True)
        clock.now = .7
        return [(10, 10, 60, 40)]

    with pytest.raises(amount.OcrBudgetExhausted):
        amount.source_cells(page, SimpleNamespace(locate=locate), 1)
    assert calls == [True]


@pytest.mark.parametrize("stage", ["first_locator", "overlap"])
def test_late_geometry_completion_is_not_reported_as_absent_cells(page, clock, stage):
    calls = []

    def locate(*args):
        calls.append(True)
        if stage == "first_locator":
            clock.now = 1
            return [BOUNDS] * (amount.CELL_LIMIT + 1)
        return [BOUNDS]

    def overlap(*args):
        clock.now = 1
        return 1

    with pytest.raises(amount.OcrBudgetExhausted):
        amount.source_cells(page, SimpleNamespace(locate=locate, overlap=overlap), 1)
    assert len(calls) == (1 if stage == "first_locator" else 2)


def test_completed_regions_survive_a_later_region_budget_stop(page, clock, monkeypatch):
    regions = [(0, 0, 80, 20), (0, 30, 80, 50)]
    line = [SimpleNamespace(text=text, confidence=99, box=box) for text, box in (
        ("Tutar", (1, 1, 15, 18)), ("8", (20, 1, 30, 18)), ("TL", (35, 1, 50, 18)),
    )]
    key = amount.field([word.text for word in line])
    monkeypatch.setattr(amount, "source_cells", lambda *a: regions)
    monkeypatch.setattr(amount, "proposals", lambda *a: [(bounds, line, key) for bounds in regions])
    completed = amount.observation("raw_line", regions[0], line, key)
    callbacks = []

    def observe(gray, bounds, *args, on_punctuation=None, **kwargs):
        if bounds == regions[0]:
            if on_punctuation:
                on_punctuation({"status": "synthetic_completed_literal", "canonical_usable": False})
            return [completed], None
        raise amount.OcrBudgetExhausted

    monkeypatch.setattr(amount, "observe_region", observe)
    result = amount.observe_disputed_amounts(page, [line], "Tutar 8 TL", SimpleNamespace(), 2,
                                            on_punctuation=callbacks.append)
    assert result["decision"] == "page_budget" and result["canonical_usable"] is False
    assert result["observations"] == [completed] and len(result["regions"]) == 1
    assert callbacks == [{"status": "synthetic_completed_literal", "canonical_usable": False}]


@pytest.mark.parametrize("bad", ["broken", "8 1 1 2 2 1", "8 -10 0 1 2 0", "8 1 2 3 4 nope", 12])
def test_malformed_native_glyph_vector_is_not_classified_as_blank(page, clock, monkeypatch, bad):
    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", lambda *a, **kw: bad)
    with pytest.raises(amount.GlyphVectorInvalid):
        amount.read_amount_character_boxes(page, BOUNDS, 1)
