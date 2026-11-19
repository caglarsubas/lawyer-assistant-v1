"""Independent deadline and partial-reader controls over invented raster content.

No native OCR, user documents, provider, database or live runtime is involved.
Literal glyph vectors are nominated solely to isolate scheduling/status behavior.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PIL import Image

from app import ocr_punctuation_amount as amount
from app import punctuation_capture as capture
from app.analysis_punctuation import validate_event

RAW = [("8", (22, 22, 34, 38)), (".", (36, 35, 39, 38))]
SPAN = ((20, 20, 60, 40), None, None)
RAW_NATIVE = "8 9 14 21 30 0\n. 23 14 26 17 0\n"
CONTRAST_NATIVE = "8 9 14 21 30 0\n"


@pytest.fixture
def reader_scope(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(amount, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(amount, "account_amount_ink", lambda *args, **kwargs: True)
    image = Image.new("L", (100, 60), 240)
    frozen = image.tobytes()
    try:
        yield clock, image
        assert image.tobytes() == frozen, "Scheduling checks cannot rewrite source pixels"
    finally:
        image.close()


def assert_partial(event, *, status, raw_present):
    validate_event(event, 100, 60)
    assert event["status"] == status
    assert event["canonical_usable"] is False
    assert event["coordinate_frame"] == "original_raster_top_left_half_open"
    assert event["field_bounds"] == [20, 20, 60, 40]
    assert event["crop_bounds"] == [20, 15, 60, 45]
    expected = ([{"reader": "raw", "text": "8.", "glyphs": [[c, list(box)] for c, box in RAW]}]
                if raw_present else [])
    assert event["readings"] == expected
    assert event["missing_readers"] == (["locally_leveled"] if raw_present else ["raw", "locally_leveled"])


@pytest.mark.parametrize("stage,kind,status,raw_present", [
    ("raw", "blank", "raw_unavailable", False),
    ("raw", "error", "reader_error", False),
    ("contrast", "blank", "contrast_unavailable", True),
    ("contrast", "error", "reader_error", True),
    ("contrast", "invalid", "invalid_glyph_vector", True),
])
def test_partial_results_retain_only_literal_completed_reader(reader_scope, monkeypatch, stage, kind, status, raw_present):
    _, gray = reader_scope
    observed, calls = [], []
    raw = deepcopy(RAW)

    def reader(*args, contrast=False, **kwargs):
        calls.append("contrast" if contrast else "raw")
        if ("contrast" if contrast else "raw") != stage:
            return raw
        if kind == "error":
            raise RuntimeError("SYNTHETIC native OCR failure")
        if kind == "invalid":
            return [("8", (True, 22, 34, 38))]
        return []

    monkeypatch.setattr(amount, "read_amount_character_boxes", reader)
    result = amount.locate_amount_ink(gray, SPAN, 2.0, on_punctuation=observed.append)
    assert result == (amount.GLYPH_UNVERIFIED, "", ())
    assert len(observed) == 1
    assert_partial(observed[0], status=status, raw_present=raw_present)
    assert calls == (["raw", "contrast"] if stage == "contrast" else ["raw"])
    raw[0] = ("9", (22, 22, 34, 38))
    assert_partial(observed[0], status=status, raw_present=raw_present)


def test_source_ink_failure_does_not_start_contrast_or_promote_raw(reader_scope, monkeypatch):
    _, gray = reader_scope
    events, calls = [], []
    monkeypatch.setattr(amount, "account_amount_ink", lambda *args, **kwargs: False)

    def reader(*args, contrast=False, **kwargs):
        calls.append(contrast)
        return deepcopy(RAW)

    monkeypatch.setattr(amount, "read_amount_character_boxes", reader)
    result = amount.locate_amount_ink(gray, SPAN, 2.0, on_punctuation=events.append)
    assert result == (amount.UNCLAIMED_INK, "", ()) and calls == [False]
    assert len(events) == 1
    assert_partial(events[0], status="source_ink_unverified", raw_present=True)


def test_raw_survives_contrast_admission_refusal_without_inventing_second_read(reader_scope, monkeypatch):
    clock, gray = reader_scope
    events, calls = [], []

    def reader(*args, contrast=False, **kwargs):
        calls.append(contrast)
        if contrast:
            raise AssertionError("Contrast work must not start without its native budget and reserve")
        clock.now = 0.55
        return deepcopy(RAW)

    monkeypatch.setattr(amount, "read_amount_character_boxes", reader)
    result = amount.locate_amount_ink(gray, SPAN, 1.0, on_punctuation=events.append)
    assert result == (amount.GLYPH_UNVERIFIED, "", ()) and calls == [False]
    assert len(events) == 1
    assert_partial(events[0], status="page_budget", raw_present=True)


@pytest.mark.parametrize("late_stage", ["raw", "contrast"])
def test_late_native_return_is_budget_not_empty_reader(reader_scope, monkeypatch, late_stage):
    clock, gray = reader_scope
    events, calls = [], []

    def native(*args, **kwargs):
        calls.append(kwargs["timeout"])
        this_stage = "raw" if len(calls) == 1 else "contrast"
        if this_stage == late_stage:
            clock.now = 2.001
        return RAW_NATIVE if len(calls) == 1 else CONTRAST_NATIVE

    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", native)
    result = amount.locate_amount_ink(gray, SPAN, 2.0, on_punctuation=events.append)
    assert result == (amount.GLYPH_UNVERIFIED, "", ())
    assert len(calls) == (1 if late_stage == "raw" else 2) and len(events) == 1
    assert_partial(events[0], status="page_budget", raw_present=late_stage == "contrast")


@pytest.mark.parametrize("late_stage", ["raw", "contrast"])
def test_failure_after_page_deadline_is_budget_and_keeps_earlier_reader(reader_scope, monkeypatch, late_stage):
    clock, gray = reader_scope
    events, calls = [], []

    def native(*args, **kwargs):
        calls.append(kwargs["timeout"])
        this_stage = "raw" if len(calls) == 1 else "contrast"
        if this_stage == late_stage:
            clock.now = 2.001
            raise RuntimeError("SYNTHETIC native deadline failure")
        return RAW_NATIVE

    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", native)
    result = amount.locate_amount_ink(gray, SPAN, 2.0, on_punctuation=events.append)
    assert result == (amount.GLYPH_UNVERIFIED, "", ()) and len(events) == 1
    assert_partial(events[0], status="page_budget", raw_present=late_stage == "contrast")


def test_padding_cost_is_rechecked_before_native_ocr(reader_scope, monkeypatch):
    clock, gray = reader_scope
    calls = []
    expand = amount.ImageOps.expand

    def padding(*args, **kwargs):
        padded = expand(*args, **kwargs)
        clock.now = 0.20
        return padded

    def native(*args, **kwargs):
        calls.append(kwargs["timeout"])
        raise AssertionError("Native OCR was admitted after its guaranteed budget was consumed")

    monkeypatch.setattr(amount.ImageOps, "expand", padding)
    monkeypatch.setattr(amount.pytesseract, "image_to_boxes", native)
    with pytest.raises(RuntimeError):
        amount.read_amount_character_boxes(gray, (20, 15, 60, 45), 0.60)
    assert calls == []


@pytest.mark.parametrize("deadline", [0.0, 0.249, 0.299])
def test_row_admission_requires_native_minimum_and_processing_reserve(reader_scope, monkeypatch, deadline):
    _, gray = reader_scope
    calls = []
    monkeypatch.setattr(amount.pytesseract, "image_to_data", lambda *args, **kwargs: calls.append(kwargs))
    with pytest.raises(amount.OcrBudgetExhausted):
        amount.read_rows(gray, (0, 0, 100, 60), mode=3, profile=None, deadline=deadline)
    assert calls == []


def test_row_admission_rechecks_local_preprocessing_cost(reader_scope, monkeypatch):
    clock, gray = reader_scope
    calls = []
    original_filter = Image.Image.filter

    def filter_image(image, *args, **kwargs):
        filtered = original_filter(image, *args, **kwargs)
        clock.now = 0.31
        return filtered

    monkeypatch.setattr(Image.Image, "filter", filter_image)
    monkeypatch.setattr(amount.pytesseract, "image_to_data", lambda *args, **kwargs: calls.append(kwargs))
    with pytest.raises(amount.OcrBudgetExhausted):
        amount.read_rows(gray, (0, 0, 100, 60), mode=3, profile=(18, 7, 2), deadline=0.60)
    assert calls == []


@pytest.mark.parametrize("failure", ["blank", "timely_error", "late_return", "late_error", "late_parse"])
def test_row_blank_failure_and_budget_are_distinct(reader_scope, monkeypatch, failure):
    clock, gray = reader_scope
    calls, parses = [], []

    def native(*args, **kwargs):
        calls.append(kwargs["timeout"])
        if failure in {"late_return", "late_error"}:
            clock.now = 2.001
        if failure in {"timely_error", "late_error"}:
            raise RuntimeError("SYNTHETIC row-reader failure")
        return "SYNTHETIC empty native response"

    def parse(*args, **kwargs):
        parses.append(True)
        if failure == "late_parse":
            clock.now = 2.001
        return []

    monkeypatch.setattr(amount.pytesseract, "image_to_data", native)
    monkeypatch.setattr(amount.severe, "_partial_words", parse)
    def call():
        return amount.read_rows(gray, (0, 0, 100, 60), mode=3, profile=None, deadline=2.0)
    if failure == "blank":
        assert call() == []
    elif failure == "timely_error":
        with pytest.raises(RuntimeError) as raised:
            call()
        assert not isinstance(raised.value, amount.OcrBudgetExhausted)
    else:
        with pytest.raises(amount.OcrBudgetExhausted):
            call()
    assert calls == [1.20]
    assert len(parses) == (1 if failure in {"blank", "late_parse"} else 0)


@pytest.mark.parametrize("stage", ["nomination_raw", "nomination_contrast"])
@pytest.mark.parametrize("failure", ["budget", "error", "late_error"])
def test_outer_nomination_failure_is_incomplete_without_fabricated_alternatives(
        reader_scope, monkeypatch, stage, failure):
    clock, gray = reader_scope
    monkeypatch.setattr(capture, "time", SimpleNamespace(monotonic=lambda: clock.now))
    calls = []

    def rows(*args, profile, **kwargs):
        current = "nomination_raw" if profile is None else "nomination_contrast"
        calls.append(current)
        if current != stage:
            return []
        if failure == "budget":
            raise amount.OcrBudgetExhausted
        if failure == "late_error":
            clock.now = 2.001
        raise RuntimeError("SYNTHETIC nomination failure")

    def forbidden(*args, **kwargs):
        raise AssertionError("Failed nomination cannot invent a nominated field")

    monkeypatch.setattr(amount, "read_rows", rows)
    monkeypatch.setattr(amount, "observe_disputed_amounts", forbidden)
    events, assessment = capture._observe_page(gray, 2.0)
    assert events == []
    assert assessment == {"status": "incomplete", "reason": "reader_error" if failure == "error" else "page_budget",
                          "stage": stage}
    assert calls == (["nomination_raw"] if stage == "nomination_raw"
                     else ["nomination_raw", "nomination_contrast"])


def test_timely_blank_nomination_has_explicit_completed_scope_check(reader_scope, monkeypatch):
    clock, gray = reader_scope
    monkeypatch.setattr(capture, "time", SimpleNamespace(monotonic=lambda: clock.now))
    calls = []

    def rows(*args, profile, **kwargs):
        calls.append(profile)
        return []

    monkeypatch.setattr(amount, "read_rows", rows)
    events, assessment = capture._observe_page(gray, 2.0)
    assert events == []
    assert assessment == {"status": "complete", "reason": "no_currency_scope", "stage": "currency_fields"}
    assert len(calls) == 2


@pytest.mark.parametrize("decision,expected", [
    ("page_budget", "page_budget"),
    ("source_currency_geometry_unverified", "source_scope_unverified"),
    ("ambiguous_currency_geometry", "source_scope_unverified"),
    ("too_many_currency_regions", "source_scope_unverified"),
])
def test_outer_result_cannot_label_unchecked_scope_as_no_alternatives(reader_scope, monkeypatch, decision, expected):
    clock, gray = reader_scope
    monkeypatch.setattr(capture, "time", SimpleNamespace(monotonic=lambda: clock.now))
    nominated = [[SimpleNamespace(text=word) for word in ("Tahsil", "8.00", "TL")]]
    monkeypatch.setattr(amount, "read_rows", lambda *args, **kwargs: nominated)
    monkeypatch.setattr(amount, "observe_disputed_amounts", lambda *args, **kwargs: amount.outcome(decision))
    events, assessment = capture._observe_page(gray, 2.0)
    assert events == []
    assert assessment == {"status": "incomplete", "reason": expected, "stage": "currency_fields"}


def test_outer_budget_preserves_actual_earlier_readings_and_source_frame(reader_scope, monkeypatch):
    clock, gray = reader_scope
    monkeypatch.setattr(capture, "time", SimpleNamespace(monotonic=lambda: clock.now))
    nominated = [[SimpleNamespace(text=word) for word in ("Tahsil", "8.00", "TL")]]
    literal = amount._punctuation_event("punctuation_disagreement", gray, (20, 20, 60, 40), (20, 15, 60, 45),
                                       deepcopy(RAW), [("8", (22, 22, 34, 38))])
    expected_event = deepcopy(literal)

    def observe(*args, on_punctuation, **kwargs):
        on_punctuation(literal)
        return amount.outcome("page_budget")

    monkeypatch.setattr(amount, "read_rows", lambda *args, **kwargs: nominated)
    monkeypatch.setattr(amount, "observe_disputed_amounts", observe)
    events, assessment = capture._observe_page(gray, 2.0)
    assert events == [expected_event]
    validate_event(events[0], 100, 60)
    assert assessment == {"status": "incomplete", "reason": "page_budget", "stage": "currency_fields"}
    assert events[0]["readings"][0]["text"] == "8."
    assert events[0]["readings"][1]["text"] == "8"


@pytest.mark.parametrize("stage", ["first_locator", "overlap"])
def test_source_cell_work_cannot_turn_deadline_into_empty_scope(reader_scope, stage):
    clock, gray = reader_scope
    calls = []
    cell = (20, 20, 60, 40)

    def locate(*args):
        calls.append(True)
        if stage == "first_locator":
            clock.now = 2.001
            return [cell] * 19
        return [cell]

    def overlap(*args):
        clock.now = 2.001
        return 1.0

    regional = SimpleNamespace(locate=locate, overlap=overlap)
    with pytest.raises(amount.OcrBudgetExhausted):
        amount.source_cells(gray, regional, 2.0)
    assert len(calls) == (1 if stage == "first_locator" else 2)


@pytest.mark.parametrize("partial_status,expected", [
    ("reader_error", "reader_error"),
    ("unbound_or_incomplete", "reader_unavailable"),
    ("amount_glyph_ink_unverified", "source_scope_unverified"),
    ("unaccounted_currency_field_ink", "source_scope_unverified"),
])
def test_non_glyph_partial_reader_still_marks_run_incomplete_without_events(
        reader_scope, monkeypatch, partial_status, expected):
    clock, gray = reader_scope
    monkeypatch.setattr(capture, "time", SimpleNamespace(monotonic=lambda: clock.now))
    nominated = [[SimpleNamespace(text=word) for word in ("Tahsil", "8.00", "TL")]]
    partial = {"reader": "locally_leveled_line", "status": partial_status,
               "region": [20, 20, 60, 40], "canonical_usable": False}
    monkeypatch.setattr(amount, "read_rows", lambda *args, **kwargs: nominated)
    monkeypatch.setattr(amount, "observe_disputed_amounts", lambda *args, **kwargs:
                        amount.outcome("currency_field_observed", observations=[partial]))
    events, assessment = capture._observe_page(gray, 2.0)
    assert events == []
    assert assessment == {"status": "incomplete", "reason": expected, "stage": "currency_fields"}
