"""Read disputed currency fields from registered original-raster regions.

The result contains observations only. The caller owns the selected passage.
"""

import re
import time

import pytesseract
from PIL import ImageChops, ImageDraw, ImageFilter, ImageOps

from app import pdf_scan_extract as scan
from app import pdf_severe_extract as severe

LANG = "tur+eng"
AMOUNT = re.compile(r"(?:[0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]{2})?|[0-9]+(?:[,.][0-9]{2})?)\Z")
CURRENCIES = {"TL": "TRY", "TRY": "TRY", "₺": "TRY", "USD": "USD", "$": "USD",
              "EUR": "EUR", "€": "EUR", "GBP": "GBP", "£": "GBP"}
FAILURES = (ValueError, TypeError, IndexError, KeyError, RuntimeError, OSError, AttributeError)
CELL_LIMIT = 18
REGION_LIMIT = 2
LABEL_MIN_CONFIDENCE = 80
AMOUNT_MIN_CONFIDENCE = 65
MAX_GLYPHS = 20
MAX_FIELD_WIDTH = 640
MAX_FIELD_HEIGHT = 150
GLYPH_MAX_SECONDS = .65
GLYPH_EDGE_PADDING = 7
MIN_NATIVE_GLYPH_SECONDS = .35
GLYPH_POSTPROCESS_RESERVE_SECONDS = .12
MIN_GLYPH_MARGIN_SECONDS = MIN_NATIVE_GLYPH_SECONDS + GLYPH_POSTPROCESS_RESERVE_SECONDS
MIN_NATIVE_ROW_SECONDS = .25
ROW_POSTPROCESS_RESERVE_SECONDS = .05
MIN_ROW_MARGIN_SECONDS = MIN_NATIVE_ROW_SECONDS + ROW_POSTPROCESS_RESERVE_SECONDS
ROW_MAX_SECONDS = 1.20
GLYPH_UNVERIFIED = "amount_glyph_ink_unverified"
UNCLAIMED_INK = "unaccounted_currency_field_ink"
LAYOUT_CONFLICT = "conflicting_amount_layout_review_only"
SIGN_MARKS = ("-", "−", "–")
READ_PROFILES = (
    ("raw_line", 7, None),
    ("locally_leveled_line", 7, (30, 7, 1)),
    ("locally_leveled_block", 6, (18, 3, 9)),
)


class OcrBudgetExhausted(RuntimeError):
    """The source reader cannot complete inside its admitted page budget."""


class GlyphBudgetExhausted(OcrBudgetExhausted):
    """The glyph reader cannot meet its native minimum and processing reserve."""


class GlyphVectorInvalid(ValueError):
    """Native output cannot form a bounded source-coordinate glyph vector."""


def _glyph_timeout(deadline):
    remaining = deadline - time.monotonic()
    if remaining < MIN_GLYPH_MARGIN_SECONDS:
        raise GlyphBudgetExhausted
    timeout = min(GLYPH_MAX_SECONDS, remaining - GLYPH_POSTPROCESS_RESERVE_SECONDS)
    if timeout < MIN_NATIVE_GLYPH_SECONDS:
        raise GlyphBudgetExhausted
    return timeout


def currency(token):
    return CURRENCIES.get(token.rstrip(".:;").upper())


def field(tokens):
    """Require one complete printed amount with an adjacent currency marker."""
    hits = []
    for index, token in enumerate(tokens):
        if not AMOUNT.fullmatch(token):
            continue
        neighbors = [(offset, currency(tokens[offset])) for offset in (index - 1, index + 1)
                     if 0 <= offset < len(tokens) and currency(tokens[offset])]
        if len(neighbors) > 1:
            return None
        if neighbors:
            offset, unit = neighbors[0]
            hits.append((index, offset, unit))
    if len(hits) != 1:
        return None
    amount, unit, code = hits[0]
    labels = tuple((index, token.casefold()) for index, token in enumerate(tokens) if index not in (amount, unit))
    return (amount, unit, code, labels) if any(token.strip(".,:;?!").isalpha() for _, token in labels) else None


def amount_cents(token):
    """Compare supported OCR strings numerically without changing their text."""
    if "," in token:
        whole, cents = token.split(",")
    elif "." in token and len(token.rsplit(".", 1)[1]) == 2:
        whole, cents = token.rsplit(".", 1)
    else:
        whole, cents = token, "00"
    return int(whole.replace(".", "")) * 100 + int(cents)


def outcome(decision, regions=(), observations=()):
    return {"decision": decision, "regions": list(regions), "observations": list(observations),
            "canonical_usable": False}


def expanded(box, size):
    left, top, right, bottom = box
    x_pad = max(18, min(31, (bottom - top) * 3 // 5))
    y_pad = max(12, min(24, (bottom - top) // 2))
    return (max(0, left - x_pad), max(0, top - y_pad), min(size[0], right + x_pad), min(size[1], bottom + y_pad))


def read_rows(gray, bounds, *, mode, profile, deadline):
    if deadline - time.monotonic() < MIN_ROW_MARGIN_SECONDS:
        raise OcrBudgetExhausted

    def recognize(view):
        remaining = deadline - time.monotonic()
        timeout = min(ROW_MAX_SECONDS, remaining - ROW_POSTPROCESS_RESERVE_SECONDS)
        if remaining < MIN_ROW_MARGIN_SECONDS or timeout < MIN_NATIVE_ROW_SECONDS:
            raise OcrBudgetExhausted
        try:
            tsv = pytesseract.image_to_data(view, lang=LANG, config=f"--psm {mode}", timeout=timeout)
        except FAILURES:
            if time.monotonic() >= deadline:
                raise OcrBudgetExhausted from None
            raise
        if time.monotonic() >= deadline:
            raise OcrBudgetExhausted
        rows = severe._partial_words(tsv, gray, bounds[:2])
        if time.monotonic() >= deadline:
            raise OcrBudgetExhausted
        return rows

    with gray.crop(bounds) as crop:
        if profile is None:
            return recognize(crop)
        radius, floor, gain = profile
        with crop.filter(ImageFilter.GaussianBlur(radius)) as paper, ImageChops.subtract(paper, crop) as detail:
            with detail.point([255 - min(255, max(0, shade - floor) * gain) for shade in range(256)]) as view:
                return recognize(view)


def source_cells(gray, regional, deadline):
    if deadline - time.monotonic() < .45:
        raise OcrBudgetExhausted
    with gray.filter(ImageFilter.GaussianBlur(18)) as paper, ImageChops.subtract(paper, gray) as detail:
        first = regional.locate(detail, 16)
        if time.monotonic() >= deadline:
            raise OcrBudgetExhausted
        if len(first) > CELL_LIMIT:
            return []
        if deadline - time.monotonic() < .35:
            raise OcrBudgetExhausted
        second = regional.locate(detail, 20)
    if time.monotonic() >= deadline:
        raise OcrBudgetExhausted
    if len(second) > CELL_LIMIT:
        return []
    cells = [cell for cell in first if sum(regional.overlap(cell, view) >= .72 for view in second) == 1]
    if time.monotonic() >= deadline:
        raise OcrBudgetExhausted
    return cells


def printed_columns(detail, height, threshold):
    """Locate substantial upright ink within a narrow row strip."""
    min_column_ink = max(2, height // 14)
    min_rise = max(6, height // 3)
    min_width = max(3, height // 9)
    min_ink = max(10, height * height // 36)
    with detail.point([255 if value >= threshold else 0 for value in range(256)]) as ink:
        pixels = ink.load()
        counts = [sum(pixels[x, y] != 0 for y in range(ink.height)) for x in range(ink.width)]
        for left, right in scan._runs([count >= min_column_ink for count in counts]):
            if right - left < min_width or sum(counts[left:right]) < min_ink:
                continue
            with ink.crop((left, 0, right, ink.height)) as component:
                _, top, _, bottom = component.getbbox()
            if bottom - top >= min_rise:
                yield left, right


def field_boundary_word(gray, region, line, amount, unit, step):
    """Find the next printed currency marker or a source-backed label."""
    stop = len(line) if step > 0 else -1
    for index in range(amount + step, stop, step):
        word = line[index]
        if index == unit:
            return word
        spelling = word.text.strip('"\'“”‘’.:;!?')
        if (len(spelling) < 2 or not spelling.isalpha() or word.confidence < LABEL_MIN_CONFIDENCE
                or severe._fraction_covered(word.box, region) < .65):
            continue
        left, top, right, bottom = word.box
        if not 0 <= left < right <= gray.width or not 0 <= top < bottom <= gray.height:
            continue
        with gray.crop(word.box) as source:
            histogram = source.histogram()
        if severe._percentile(histogram, .78) - severe._percentile(histogram, .06) >= 16:
            return word
    return None


def currency_field_span(gray, region, line, key):
    """Bound the source field to its printed label and currency marker."""
    amount, unit, _, _ = key
    left, top, right, bottom = line[amount].box
    _, unit_top, _, unit_bottom = line[unit].box
    height = min(bottom - top, unit_bottom - unit_top)
    if height < 10 or min(bottom, unit_bottom) - max(top, unit_top) < height * .60:
        return None
    tolerance = max(2, min(5, height // 10))
    previous = field_boundary_word(gray, region, line, amount, unit, -1)
    following = field_boundary_word(gray, region, line, amount, unit, 1)
    x1 = max(region[0], previous.box[2] + tolerance) if previous else region[0]
    x2 = min(region[2], following.box[0] - tolerance) if following else region[2]
    y1 = max(region[1], min(top, unit_top) - tolerance)
    y2 = min(region[3], max(bottom, unit_bottom) + tolerance)
    if not (0 <= x1 <= left + tolerance < right - tolerance <= x2 <= gray.width
            and 0 <= y1 < y2 <= gray.height):
        return None
    return ((x1, y1, x2, y2), height, tolerance)


def ink_registration(gray, region, line, key, span=None):
    """Check original printed bounds of the monetary field, not only line overlap."""
    span = span or currency_field_span(gray, region, line, key)
    if span is None:
        return "currency_field_ink_unverified"
    (x1, y1, x2, y2), height, tolerance = span
    left, _, right, _ = line[key[0]].box
    pad = 18
    crop = (max(0, x1 - pad), max(0, y1 - pad), min(gray.width, x2 + pad), min(gray.height, y2 + pad))
    local = (x1 - crop[0], y1 - crop[1], x2 - crop[0], y2 - crop[1])
    with gray.crop(crop) as source, source.filter(ImageFilter.GaussianBlur(12)) as paper:
        with ImageChops.subtract(paper, source) as contrast, contrast.crop(local) as detail:
            inner_left = max(0, left - tolerance - x1)
            inner_right = min(detail.width, right + tolerance - x1)
            strips = ((0, inner_left), (inner_left, inner_right), (inner_right, detail.width))
            supported = []
            for start, stop in strips:
                with detail.crop((start, 0, stop, detail.height)) as strip:
                    stronger = list(printed_columns(strip, height, 29))
                    lighter = list(printed_columns(strip, height, 20)) if stronger else []
                    supported.append(any(a < d and c < b for a, b in stronger for c, d in lighter))
    if supported[0] or supported[2]:
        return "incomplete_currency_field_ink"
    return "source_registered" if supported[1] else "currency_field_ink_unverified"


def glyph_shape(text):
    if not 1 <= len(text) <= MAX_GLYPHS or any(c not in "0123456789.," for c in text):
        return ""
    return "".join(c if c in ".," else "#" for c in text)


def read_amount_character_boxes(gray, bounds, deadline, *, contrast=False):
    """Localize source characters with native OCR, without a numeric whitelist."""
    _glyph_timeout(deadline)
    x1, y1, x2, y2 = bounds
    width, height = x2 - x1, y2 - y1
    if not (0 < width <= MAX_FIELD_WIDTH and 0 < height <= MAX_FIELD_HEIGHT
            and 0 <= x1 < x2 <= gray.width and 0 <= y1 < y2 <= gray.height):
        raise GlyphVectorInvalid
    padding = GLYPH_EDGE_PADDING

    def read(view):
        with ImageOps.expand(view, border=padding, fill=255) as bordered:
            # Cropping, contrast preparation and padding all consume the same
            # deadline. Admit native work only after that preparation finishes.
            timeout = _glyph_timeout(deadline)
            try:
                native_boxes = pytesseract.image_to_boxes(
                    bordered, lang=LANG, config="--psm 8", timeout=timeout,
                )
            except FAILURES:
                if time.monotonic() >= deadline:
                    raise GlyphBudgetExhausted from None
                raise
        if time.monotonic() >= deadline:
            raise GlyphBudgetExhausted
        if not isinstance(native_boxes, str) or len(native_boxes) > 2000:
            raise GlyphVectorInvalid
        glyphs = []
        for entry in native_boxes.splitlines():
            try:
                char, a, b, c, d, page = entry.split()
                a, b, c, d = map(int, (a, b, c, d))
            except (TypeError, ValueError) as error:
                raise GlyphVectorInvalid from error
            left, top, right, bottom = a - padding, height + padding - d, c - padding, height + padding - b
            if (len(char) != 1 or page != "0" or len(glyphs) >= MAX_GLYPHS
                    or not (0 <= left < right <= width and 0 <= top < bottom <= height)):
                raise GlyphVectorInvalid
            glyphs.append((char, (x1 + left, y1 + top, x1 + right, y1 + bottom)))
        if time.monotonic() >= deadline:
            raise GlyphBudgetExhausted
        return glyphs

    with gray.crop(bounds) as original:
        if not contrast:
            return read(original)
        with original.filter(ImageFilter.GaussianBlur(12)) as paper, ImageChops.subtract(paper, original) as detail:
            with detail.point([255 - min(255, max(0, shade - 4) * 6) for shade in range(256)]) as flat:
                return read(flat)


def unmatched_leading_ink(residual, bounds, glyphs, nominal_box, height):
    if nominal_box is None:
        return False
    x1, y1, x2, y2 = bounds
    first = glyphs[0][1]
    left, top, right, bottom = nominal_box
    # Lower contrast is used only in the unclaimed leading part of the same
    # nominal source word and within the independently located digit band.
    crop = (max(x1, left), max(y1, top, first[1]), min(x2, right, first[0] - 2), min(y2, bottom, first[3]))
    if crop[2] - crop[0] < max(3, height // 9) or crop[3] - crop[1] < height * .70:
        return False
    with residual.crop((crop[0] - x1, crop[1] - y1, crop[2] - x1, crop[3] - y1)) as leading:
        weaker = list(printed_columns(leading, height, 14))
        stronger = list(printed_columns(leading, height, 16)) if weaker else []
    return any(min(b, d) - max(a, c) >= .70 * min(b - a, d - c)
               for a, b in weaker for c, d in stronger)


def account_amount_ink(gray, bounds, glyphs, *, nominal_box=None):
    """Require independently localized glyphs to account for visible field ink."""
    x1, y1, x2, y2 = bounds
    if not (0 < x2 - x1 <= MAX_FIELD_WIDTH and 0 < y2 - y1 <= MAX_FIELD_HEIGHT
            and 0 <= x1 < x2 <= gray.width and 0 <= y1 < y2 <= gray.height
            and "#" in glyph_shape("".join(char for char, _ in glyphs))):
        return False
    boxes = [box for _, box in glyphs]
    if (any(not (x1 <= a < c <= x2 and y1 <= b < d <= y2) for a, b, c, d in boxes)
            or any(left[2] > right[0] + 2 or left[0] >= right[0] for left, right in zip(boxes, boxes[1:]))):
        return False
    height = max(d - b for char, (_, b, _, d) in glyphs if char not in ".,")
    with gray.crop(bounds) as original, original.filter(ImageFilter.GaussianBlur(12)) as paper:
        with ImageChops.subtract(paper, original) as detail, detail.copy() as unclaimed:
            fill = ImageDraw.Draw(unclaimed)
            for char, (a, b, c, d) in glyphs:
                local = (a - x1, b - y1, c - x1, d - y1)
                with detail.crop(local) as glyph:
                    histogram = glyph.histogram()
                    if sum(histogram[20:]) < max(2, (glyph.width * glyph.height) // 20):
                        return False
                    if char not in ".," and len(list(printed_columns(glyph, height, 20))) != 1:
                        return False
                u, v, w, z = local
                fill.rectangle((u - 2, v - 2, w + 1, z + 1), fill=0)
            return (not any(printed_columns(unclaimed, height, 20))
                    and not unmatched_leading_ink(unclaimed, bounds, glyphs, nominal_box, height))


def detached_stray_mark(gray, bounds, mark, first, nominal_box):
    """Check original pixels for a faint elevated scuff outside the amount word."""
    if nominal_box is None or mark[0] != "-":
        return False
    left, top, right, bottom = mark[1]
    x1, y1, _, y2 = first[1]
    height = y2 - y1
    if (right - left > height / 4 or bottom - top > 3 or y1 > top or bottom > y1 + .40 * height
            or min(x1, nominal_box[0]) - right < max(6, height // 5)):
        return False
    bx, by, end_x, end_y = bounds
    scope = (max(bx, left - 4), max(by, top - 4), min(end_x, right + 4), min(end_y, bottom + 4))
    local = (scope[0] - bx, scope[1] - by, scope[2] - bx, scope[3] - by)
    with gray.crop(bounds) as original, original.filter(ImageFilter.GaussianBlur(12)) as paper:
        with ImageChops.subtract(paper, original) as detail:
            with detail.crop(local) as mark_ink:
                histogram = mark_ink.histogram()
                if sum(histogram[29:]) or not sum(histogram[20:]):
                    return False
                with mark_ink.point([255 if value >= 16 else 0 for value in range(256)]) as printed:
                    a, b, c, d = printed.getbbox()
            ink_box = (a + scope[0], b + scope[1], c + scope[0], d + scope[1])
            return (d - b <= 3 and c - a <= height / 4
                    and min(x1, nominal_box[0]) - ink_box[2] >= max(6, height // 5)
                    and severe._fraction_covered(mark[1], ink_box) >= .65)


def _punctuation_reading(reader, glyphs, crop):
    if not isinstance(glyphs, (tuple, list)) or not 0 < len(glyphs) <= MAX_GLYPHS:
        return None
    snapshots = []
    for item in glyphs:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            return None
        char, box = item
        if (not isinstance(char, str) or len(char) != 1 or char not in "0123456789.,-"
                or not isinstance(box, (tuple, list)) or len(box) != 4
                or any(type(value) is not int for value in box)):
            return None
        a, b, c, d = box
        if not crop[0] <= a < c <= crop[2] or not crop[1] <= b < d <= crop[3]:
            return None
        snapshots.append([char, list(box)])
    return {"reader": reader, "text": "".join(char for char, _ in snapshots), "glyphs": snapshots}


def _punctuation_event(status, gray, field, crop, raw, leveled):
    def valid(box):
        return (isinstance(box, (tuple, list)) and len(box) == 4
                and all(type(value) is int for value in box)
                and 0 <= box[0] < box[2] <= gray.width and 0 <= box[1] < box[3] <= gray.height)

    if (not valid(field) or not valid(crop) or crop[2] - crop[0] > MAX_FIELD_WIDTH
            or crop[3] - crop[1] > MAX_FIELD_HEIGHT
            or not crop[0] <= field[0] < field[2] <= crop[2]
            or not crop[1] <= field[1] < field[3] <= crop[3]):
        return {"status": "field_unavailable", "field_bounds": None, "crop_bounds": None,
                "coordinate_frame": "original_raster_top_left_half_open", "readings": [],
                "missing_readers": ["raw", "locally_leveled"], "canonical_usable": False}
    readings = []
    invalid = False
    for reader, glyphs in (("raw", raw), ("locally_leveled", leveled)):
        snapshot = _punctuation_reading(reader, glyphs, crop)
        if snapshot is not None:
            readings.append(snapshot)
        elif glyphs:
            invalid = True
    return {"status": "invalid_glyph_vector" if invalid else status,
            "field_bounds": list(field), "crop_bounds": list(crop),
            "coordinate_frame": "original_raster_top_left_half_open", "readings": readings,
            "missing_readers": [label for label in ("raw", "locally_leveled")
                                if not any(reading["reader"] == label for reading in readings)],
            "canonical_usable": False}


def locate_amount_ink(gray, span, deadline, *, nominal_box=None, on_punctuation=None):
    field = bounds = None
    raw, native_leveled = [], []
    reported = False

    def report(status):
        nonlocal reported
        if on_punctuation is not None and not reported:
            reported = True
            on_punctuation(_punctuation_event(status, gray, field, bounds, raw, native_leveled))

    if span is None:
        report("field_unavailable")
        return (GLYPH_UNVERIFIED, "", ())
    try:
        (x1, y1, x2, y2), _, _ = span
        field = (x1, y1, x2, y2)
        bounds = (x1, max(0, y1 - 5), x2, min(gray.height, y2 + 5))
    except FAILURES:
        report("field_unavailable")
        return (GLYPH_UNVERIFIED, "", ())
    if deadline - time.monotonic() < MIN_GLYPH_MARGIN_SECONDS:
        report("page_budget")
        return (GLYPH_UNVERIFIED, "", ())
    try:
        candidate_raw = read_amount_character_boxes(gray, bounds, deadline)
        if time.monotonic() >= deadline:
            raise GlyphBudgetExhausted
        raw = candidate_raw
        if not raw:
            report("raw_unavailable")
            return (GLYPH_UNVERIFIED, "", ())
        if _punctuation_reading("raw", raw, bounds) is None:
            report("invalid_glyph_vector")
            return (GLYPH_UNVERIFIED, "", ())
        shape = glyph_shape("".join(char for char, _ in raw))
        if "#" not in shape or deadline - time.monotonic() < MIN_GLYPH_MARGIN_SECONDS:
            report("raw_unavailable" if not raw else "page_budget" if "#" in shape else "invalid_glyph_vector")
            return (GLYPH_UNVERIFIED, "", ())
        if not account_amount_ink(gray, bounds, raw, nominal_box=nominal_box):
            report("source_ink_unverified")
            return (UNCLAIMED_INK, "", ())
        if deadline - time.monotonic() < MIN_GLYPH_MARGIN_SECONDS:
            report("page_budget")
            return (GLYPH_UNVERIFIED, "", ())
        leveled = read_amount_character_boxes(gray, bounds, deadline, contrast=True)
        if time.monotonic() >= deadline:
            raise GlyphBudgetExhausted
        native_leveled = leveled
        # Preserve the actual native vectors before the existing stray-mark handling.
        if not leveled:
            report("contrast_unavailable")
            return (GLYPH_UNVERIFIED, "", ())
        if _punctuation_reading("locally_leveled", leveled, bounds) is None:
            report("invalid_glyph_vector")
            return (GLYPH_UNVERIFIED, "", ())
        # Keep the existing leading-scuff treatment separate from punctuation.
        if len(leveled) == len(raw) + 1 and detached_stray_mark(gray, bounds, leveled[0], raw[0], nominal_box):
            leveled = leveled[1:]
        raw_marks = [(index, char) for index, (char, _) in enumerate(raw) if char in ".,"]
        leveled_marks = [(index, char) for index, (char, _) in enumerate(leveled) if char in ".,"]
        leveled_shape = glyph_shape("".join(char for char, _ in leveled))
        same_layout = leveled_shape == shape and all(
            severe._fraction_covered(first[1], second[1]) >= .65
            for first, second in zip(raw, leveled, strict=True)
        )
        if time.monotonic() >= deadline:
            raise GlyphBudgetExhausted
        if not leveled_shape:
            report("invalid_glyph_vector")
        elif raw_marks != leveled_marks:
            report("punctuation_disagreement")
        if not same_layout:
            return (GLYPH_UNVERIFIED, "", ())
    except GlyphBudgetExhausted:
        report("page_budget")
        return (GLYPH_UNVERIFIED, "", ())
    except GlyphVectorInvalid:
        report("invalid_glyph_vector")
        return (GLYPH_UNVERIFIED, "", ())
    except FAILURES:
        report("page_budget" if time.monotonic() >= deadline else "reader_error")
        return (GLYPH_UNVERIFIED, "", ())
    return ("source_registered", shape, tuple(box for _, box in raw))


def proposals(rows, cells, regional):
    proposed = []
    for line in rows:
        key = field([word.text for word in line])
        if not key:
            continue
        bounds = severe._line_bounds(line)
        matched = [cell for cell in cells if regional.overlap(bounds, cell) >= .68]
        if len(matched) == 1:
            proposed.append((matched[0], line, key))
    return proposed


def suffix_layout_conflict(first, second):
    short, long = sorted((first, second), key=lambda word: len(word.text))
    short_shape, long_shape = glyph_shape(short.text), glyph_shape(long.text)
    return (
        round(short.confidence, 2) >= AMOUNT_MIN_CONFIDENCE
        and round(long.confidence, 2) >= AMOUNT_MIN_CONFIDENCE
        and short_shape and long_shape
        and short_shape.count("#") < long_shape.count("#")
        and long.text.endswith(short.text)
        and severe._fraction_covered(short.box, long.box) >= .75
    )


def same_field(previous, old_key, current, key, regional):
    old_amount, old_unit, old_code, old_labels = old_key
    amount, unit, code, labels = key
    return (
        (old_amount, old_unit, old_code, old_labels) == (amount, unit, code, labels)
        and len(previous) == len(current)
        and all(regional.overlap(previous[index].box, current[index].box) >= .70
                for index in (unit, *(i for i, _ in labels)))
        and (regional.overlap(previous[old_amount].box, current[amount].box) >= .70
             or suffix_layout_conflict(previous[old_amount], current[amount]))
    )


def baseline_binding(lines, reference, reference_key):
    amount, unit, code, labels = reference_key
    matches = []
    for line in lines:
        tokens = line.split()
        key = field(tokens)
        if key == (amount, unit, code, labels) and len(tokens) == len(reference):
            matches.append((line, tokens[amount]))
    return matches[0] if len(matches) == 1 else ("", "")


def observation(reader, region, line, key, status="source_registered"):
    amount, unit, code, _ = key
    confidence = round(line[amount].confidence, 2)
    if status == "source_registered" and confidence < AMOUNT_MIN_CONFIDENCE:
        status = "insufficient_amount_read_confidence"
    result = {"reader": reader, "status": status, "region": region, "amount_box": line[amount].box,
              "text": " ".join(word.text for word in line), "word_boxes": [word.box for word in line],
              "canonical_usable": False}
    if status == "source_registered":
        result.update(amount=line[amount].text, confidence=confidence,
                      currency=line[unit].text, currency_code=code, currency_box=line[unit].box)
    elif status in ("insufficient_amount_read_confidence", GLYPH_UNVERIFIED, UNCLAIMED_INK, LAYOUT_CONFLICT):
        result["confidence"] = confidence
    return result


def layout_conflict(region, span, recorded):
    if span is None:
        return None
    physical, _, _ = span
    eligible = [(reader, line, key) for reader, line, key in recorded
                if severe._fraction_covered(line[key[0]].box, physical) >= .80]
    disputed = set()
    for i, (_, a, key_a) in enumerate(eligible):
        for j, (_, b, key_b) in enumerate(eligible[i + 1:], i + 1):
            if suffix_layout_conflict(a[key_a[0]], b[key_b[0]]):
                disputed.update((i, j))
    if not disputed:
        return None
    options = []
    for i in sorted(disputed):
        reader, line, key = eligible[i]
        amount, unit, code, _ = key
        record = observation(reader, region, line, key, LAYOUT_CONFLICT)
        record.update(observed_token=line[amount].text, currency=line[unit].text,
                      currency_box=line[unit].box, currency_code=code)
        options.append(record)
    return {"status": LAYOUT_CONFLICT, "readings": options, "canonical_usable": False}


def observe_region(gray, region, original, key, reader, regional, deadline, *, on_punctuation=None):
    span = currency_field_span(gray, region, original, key)
    status = ink_registration(gray, region, original, key, span)
    layout = None
    nominal_box = original[key[0]].box
    recorded = [(reader, original, key)]

    def qualify(label, line, current, observed):
        nonlocal layout
        word = line[current[0]]
        if observed == "source_registered" and round(word.confidence, 2) >= AMOUNT_MIN_CONFIDENCE:
            if layout is None:
                report = None
                if on_punctuation is not None:
                    def report(event):
                        on_punctuation({**event, "region": list(region)})
                layout = locate_amount_ink(gray, span, deadline, nominal_box=nominal_box, on_punctuation=report)
            observed, shape, boxes = layout
            if current[0] and line[current[0] - 1].text in SIGN_MARKS:
                observed = GLYPH_UNVERIFIED
            if observed == "source_registered" and (glyph_shape(word.text) != shape or any(
                severe._fraction_covered(box, word.box) < .75 for box in boxes
            )):
                observed = UNCLAIMED_INK
        return observation(label, region, line, current, observed)

    findings = [qualify(reader, original, key, status)]
    if status != "source_registered":
        return findings, None
    crop = expanded(region, gray.size)
    for label, mode, profile in READ_PROFILES:
        if deadline - time.monotonic() < MIN_ROW_MARGIN_SECONDS:
            raise OcrBudgetExhausted
        try:
            rows = read_rows(gray, crop, mode=mode, profile=profile, deadline=deadline)
            readings = [(line, current) for line in rows if (current := field([word.text for word in line]))
                        and same_field(original, key, line, current, regional)]
            if len(readings) == 1:
                line, current = readings[0]
                recorded.append((label, line, current))
                findings.append(qualify(label, line, current, ink_registration(gray, region, line, current)))
                continue
        except OcrBudgetExhausted:
            raise
        except FAILURES:
            findings.append({"reader": label, "status": "reader_error", "region": region,
                             "canonical_usable": False})
            continue
        findings.append({"reader": label, "status": "unbound_or_incomplete", "region": region,
                         "canonical_usable": False})
    conflict = layout_conflict(region, span, recorded)
    if conflict:
        for finding in findings:
            if finding["status"] == "source_registered":
                finding["status"] = LAYOUT_CONFLICT
                for key_to_remove in ("amount", "currency", "currency_code", "currency_box"):
                    del finding[key_to_remove]
    return findings, conflict


def observe_disputed_amounts(gray, original, baseline, regional, deadline, *, on_punctuation=None):
    if deadline - time.monotonic() < .55:
        return outcome("page_budget")
    lines = baseline.splitlines()
    if not (any(field(line.split()) for line in lines)
            or any(field([word.text for word in line]) for line in original)):
        return outcome("no_retained_currency_scope")
    try:
        cells = source_cells(gray, regional, deadline)
        nominated = proposals(original, cells, regional)
        by_region = {}
        for cell, line, key in nominated:
            if cell not in by_region:
                by_region[cell] = (line, key, "original_page_raw")
            else:
                # Multiple original readings in one physical cell need layout review.
                return outcome("ambiguous_currency_geometry")
        if not by_region and cells:
            if deadline - time.monotonic() < .65:
                raise OcrBudgetExhausted
            # Re-register an OCR amount in original coordinates when the selected
            # passage came from a later pass without authoritative raw boxes.
            rows = read_rows(gray, (0, 0, gray.width, gray.height), mode=3, profile=(18, 7, 2), deadline=deadline)
            for cell, line, key in proposals(rows, cells, regional):
                if cell in by_region:
                    return outcome("ambiguous_currency_geometry")
                by_region[cell] = (line, key, "leveled_page_nomination")
    except OcrBudgetExhausted:
        return outcome("page_budget")
    except FAILURES:
        return outcome("source_currency_geometry_unverified")
    if not by_region:
        return outcome("page_budget" if deadline - time.monotonic() < .30 else "source_currency_geometry_unverified")
    if len(by_region) > REGION_LIMIT:
        return outcome("too_many_currency_regions")
    regions, observations = [], []
    for bounds, (line, key, reader) in sorted(by_region.items(), key=lambda item: (item[0][1], item[0][0])):
        try:
            found, conflict = observe_region(gray, bounds, line, key, reader, regional, deadline, on_punctuation=on_punctuation)
        except OcrBudgetExhausted:
            return outcome("page_budget", regions, observations)
        observations.extend(found)
        registered = found[0]["status"] == "source_registered"
        retained, amount = baseline_binding(lines, line, key) if registered else ("", "")
        values = [o for o in found if o["status"] == "source_registered"]
        distinct = {amount_cents(o["amount"]) for o in values}
        regional_reads = [o for o in values if o["reader"] not in ("original_page_raw", "leveled_page_nomination")]
        status = (LAYOUT_CONFLICT if conflict else
                  "conflicting_amount_observations" if len(distinct) > 1 and regional_reads else
                  "currency_field_observed" if regional_reads else "unresolved_currency_field")
        scope = "retained_currency_line" if retained else "currency_region_unbound_to_selected"
        regions.append({"bounds": bounds, "scope": scope if registered else found[0]["status"],
                        "retained_line": retained, "retained_amount": amount, "status": status,
                        "amounts_seen": sorted({o["amount"] for o in values}),
                        "regional_read_count": len(regional_reads), "canonical_usable": False})
        if conflict:
            regions[-1]["layout_conflict"] = conflict
    if time.monotonic() >= deadline:
        return outcome("page_budget", regions, observations)
    if any(region["status"] == LAYOUT_CONFLICT for region in regions):
        decision = LAYOUT_CONFLICT
    elif any(region["status"] == "conflicting_amount_observations" for region in regions):
        decision = "conflicting_amount_observations"
    elif any(region["regional_read_count"] for region in regions):
        decision = "currency_field_observed"
    else:
        decision = "unresolved_currency_field"
    return outcome(decision, regions, observations)
