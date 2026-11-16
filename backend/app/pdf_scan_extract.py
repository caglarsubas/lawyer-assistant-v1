"""Run the existing PDF parser with a conservative, bounded scan enhancement."""

import builtins
import csv
import json
import re
import resource
import sys
import time
from contextlib import nullcontext
from itertools import groupby
from pathlib import Path
from types import FunctionType, SimpleNamespace

from PIL import Image, ImageDraw, ImageOps

from .extract import extract
from .pdf_image_coverage import add_pdf_coverage_warnings


def _percentile(histogram, fraction):
    remaining = sum(histogram) * fraction
    for shade, count in enumerate(histogram):
        remaining -= count
        if remaining <= 0:
            return shade
    return 255


def _enhance_scan(picture):
    # Poppler already limits the raster to 2,000 pixels on the longest edge.
    if max(picture.size) > 2000:
        return None
    with picture.convert("L") as gray:
        histogram = gray.histogram()
        ink = _percentile(histogram, 0.0025)
        paper = _percentile(histogram, 0.85)
        # Leave strong-contrast, predominantly dark, and barely visible images
        # on the standard path. Very weak pages can generate plausible garbage.
        if not (110 <= ink <= 195 and paper >= 230 and paper - ink >= 40):
            return None
        with gray.copy() as preview:
            preview.thumbnail((448, 448), Image.Resampling.BILINEAR)
            threshold = (ink + paper) // 2
            with preview.point([255 if level < threshold else 0 for level in range(256)]) as mask:
                projections = {}
                for angle in range(-7, 8):
                    with mask.rotate(angle, resample=Image.Resampling.NEAREST, expand=True) as rotated:
                        with rotated.resize((1, rotated.height), Image.Resampling.BOX) as rows:
                            projections[angle] = sum(shade * shade for shade in rows.tobytes())
        angle = max(projections, key=lambda step: (projections[step], -abs(step)))
        if projections[angle] > projections[0] * 1.06:
            with gray.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=paper) as rotated:
                return ImageOps.autocontrast(rotated, cutoff=0.1)
        return ImageOps.autocontrast(gray, cutoff=0.1)


def _ocr_lines(text, tsv):
    # Keep only native word-level scores and line groupings. TSV must correspond
    # exactly to the reported text before its scores can support a switch.
    lines = []
    line = ()
    for row, word in _word_rows(tsv):
        key = (row["block_num"], row["par_num"], row["line_num"])
        score = float(row["conf"])
        if not 0 <= score <= 100:
            raise ValueError("Invalid OCR confidence score")
        if key != line:
            lines.append([])
            line = key
        lines[-1].append((word, score))
    if [word for group in lines for word, _ in group] != text.split():
        raise ValueError("Inconsistent OCR text and scores")
    return lines


def _word_rows(tsv):
    rows = csv.DictReader(tsv.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in rows:
        # Tesseract can emit level-5 layout rows containing only spaces.
        if row.get("level") == "5" and (word := row.get("text")) and word.strip():
            yield row, word


def _runs(projection):
    start = 0
    for ink, band in groupby(projection):
        stop = start + sum(1 for _ in band)
        if ink:
            yield start, stop
        start = stop


def _has_detached_dot(glyph):
    _, rows = glyph.getprojection()
    runs = list(_runs(rows))
    if len(runs) != 2:
        return False
    (dot_top, dot_bottom), (stem_top, stem_bottom) = runs
    with glyph.crop((0, dot_top, glyph.width, dot_bottom)) as dot:
        dot_left, _, dot_right, _ = dot.getbbox()
    with glyph.crop((0, stem_top, glyph.width, stem_bottom)) as stem:
        stem_left, _, stem_right, _ = stem.getbbox()
    stem_height = stem_bottom - stem_top
    return (
        stem_height >= 12
        and 2 <= dot_bottom - dot_top <= stem_height / 3
        and 2 <= dot_right - dot_left <= stem_height / 3
        and max(2, stem_height / 20) <= stem_top - dot_bottom <= stem_height / 3
        and stem_left <= dot_left <= dot_right <= stem_right
        and abs((dot_left + dot_right) - (stem_left + stem_right)) <= (stem_right - stem_left) / 2
        and stem_right - stem_left <= stem_height * 0.65
    )


def _word_box(row):
    return tuple(int(row[key]) for key in ("left", "top", "width", "height"))


def _confirm_source_dots(picture, box, word, positions):
    left, top, width, height = box
    right, bottom = left + width, top + height
    if not (0 <= left < right <= picture.width and 0 <= top < bottom <= picture.height):
        return False
    with picture.crop((left, top, right, bottom)) as crop, crop.convert("L") as gray:
        dark, light = gray.getextrema()
        if light - dark < 64:
            return False
        midpoint = (dark + light) // 2
        with gray.point([255 if shade < midpoint else 0 for shade in range(256)]) as mask:
            columns, _ = mask.getprojection()
            glyphs = list(_runs(columns))
            # Require identifiable glyph slots in source pixels. Connected
            # letters, touching accents or dust can make alignment ambiguous.
            if len(glyphs) != len(word):
                return False
            for position in positions:
                a, b = glyphs[position]
                with mask.crop((a, 0, b, height)) as glyph:
                    if not _has_detached_dot(glyph):
                        return False
    return True


def _word_lines(tsv):
    def line(entry):
        row, _ = entry
        return row["block_num"], row["par_num"], row["line_num"]

    return [list(group) for _, group in groupby(_word_rows(tsv), key=line)]


def _recover_dotted_i(ocr, picture, baseline, original_tsv, *, lang, deadline):
    raw_lines = baseline.splitlines(keepends=True)
    tokens = [list(re.finditer(r"\S+", line)) for line in raw_lines]
    if not any("I" in token[0] and token[0].isupper() for line in tokens for token in line):
        return baseline
    remaining = deadline - time.monotonic()
    if remaining < 0.25:
        return baseline
    # Single-block segmentation can retain dots that automatic layout misses.
    # Its text is never used wholesale: preserve the original layout verbatim.
    tsv = ocr.image_to_data(picture, lang=lang, config="--psm 6", timeout=min(2, remaining))
    original = _word_lines(original_tsv)
    candidate = _word_lines(tsv)
    if list(map(len, original)) != list(map(len, candidate)) or list(map(len, candidate)) != [
        len(line) for line in tokens if line
    ]:
        return baseline

    repairs = []
    offset = 0
    aligned = iter(zip(original, candidate, strict=True))
    for raw_line, row_tokens in zip(raw_lines, tokens, strict=True):
        if row_tokens:
            first, second = next(aligned)
            for token, (prior_row, before), (row, after) in zip(row_tokens, first, second, strict=True):
                box = _word_box(row)
                if token[0] != before or _word_box(prior_row) != box:
                    return baseline
                if before == after:
                    continue
                if not (
                    len(before) == len(after) and before.isupper() and not any(c.isnumeric() for c in before)
                    and 95 <= float(row["conf"]) <= 100 and time.monotonic() < deadline
                ):
                    return baseline
                differences = [(i, a, b) for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
                if any((a, b) != ("I", "İ") for _, a, b in differences):
                    return baseline
                positions = [i for i, _, _ in differences]
                if not _confirm_source_dots(picture, box, after, positions):
                    return baseline
                repairs.append((offset + token.start(), offset + token.end(), after))
        offset += len(raw_line)
    if time.monotonic() >= deadline:
        return baseline
    for start, end, replacement in reversed(repairs):
        baseline = baseline[:start] + replacement + baseline[end:]
    return baseline


def _word_edges(row, origin=(0, 0)):
    left, top, width, height = _word_box(row)
    left += origin[0]
    top += origin[1]
    return left, top, left + width, top + height


def _terminal_period_ink(picture, word_box):
    _, top, right, bottom = word_box
    height = bottom - top
    right_limit = min(picture.width, right + height // 2)
    bottom_limit = min(picture.height, bottom + height // 5)
    if right_limit - right < 6:
        return None
    with picture.crop((right, top, right_limit, bottom_limit)) as strip, strip.convert("L") as gray:
        dark, light = gray.getextrema()
        if light - dark < 64:
            return None
        boxes = []
        # A real compact mark survives nearby thresholds. Detached noise,
        # stroke fragments and ambiguous neighboring ink are insufficient.
        for ratio in (0.45, 0.60):
            threshold = round(dark + (light - dark) * ratio)
            with gray.point([255 if value < threshold else 0 for value in range(256)]) as mask:
                box = mask.getbbox()
                if box is None:
                    return None
                left, mark_top, mark_right, mark_bottom = box
                width, mark_height = mark_right - left, mark_bottom - mark_top
                if not (
                    2 <= left <= height // 3 and mark_right < gray.width
                    and 2 <= width <= height // 3 and 2 <= mark_height <= height // 3
                    and mark_height * 0.75 <= width <= mark_height * 1.33
                    and mark_top >= height // 2
                    and height - height // 4 <= mark_bottom <= height + height // 10
                ):
                    return None
                with mask.crop(box) as mark:
                    if mark.histogram()[255] < width * mark_height * 0.65:
                        return None
                    seed = mark.tobytes().index(255)
                    ImageDraw.floodfill(mark, (seed % width, seed // width), 128)
                    if mark.getextrema()[1] != 128:
                        return None
                boxes.append(box)
    if any(abs(a - b) > 2 for a, b in zip(*boxes, strict=True)):
        return None
    left, mark_top, mark_right, mark_bottom = boxes[-1]
    return right + left, top + mark_top, right + mark_right, top + mark_bottom


def _recover_terminal_period(ocr, picture, baseline, original_tsv, *, lang, deadline):
    text = baseline.rstrip()
    remaining = deadline - time.monotonic()
    if not text or not text[-1].isalpha() or remaining < 0.25:
        return baseline
    lines = _word_lines(original_tsv)
    words = text.splitlines()[-1].split()
    if len(words) < 2 or not words[-1].isalpha() or not lines or words != [word for _, word in lines[-1]]:
        return baseline
    before = lines[-1]
    bounds = [_word_edges(row) for row, _ in before]
    if any(not (0 <= left < right <= picture.width and 0 <= top < bottom <= picture.height)
           for left, top, right, bottom in bounds):
        return baseline
    if any(first[2] > second[0] for first, second in zip(bounds, bounds[1:])):
        return baseline
    left, right = bounds[0][0], bounds[-1][2]
    top = min(box[1] for box in bounds)
    bottom = max(box[3] for box in bounds)
    height = bottom - top
    if not 16 <= height <= 160 or not 95 <= float(before[-1][0]["conf"]) <= 100:
        return baseline
    period = _terminal_period_ink(picture, bounds[-1])
    if period is None:
        return baseline

    # Read only the original last line. Whole-page segmentation can omit a
    # terminal period on a skewed scan even when its source ink is visible.
    pad = round(height * 0.4)
    crop = (left - pad, top - pad, right + pad, bottom + pad)
    if not (0 <= crop[0] < crop[2] <= picture.width and 0 <= crop[1] < crop[3] <= picture.height
            and period[2] + 2 <= crop[2]):
        return baseline
    remaining = deadline - time.monotonic()
    if remaining < 0.25:
        return baseline
    with picture.crop(crop) as strip:
        tsv = ocr.image_to_data(strip, lang=lang, config="--psm 7", timeout=min(2, remaining))
    result = _word_lines(tsv)
    if len(result) != 1 or [word for _, word in result[0]] != [*words[:-1], words[-1] + "."]:
        return baseline
    if not 95 <= float(result[0][-1][0]["conf"]) <= 100:
        return baseline
    for index, ((row, _), original) in enumerate(zip(result[0], bounds, strict=True)):
        observed = _word_edges(row, crop[:2])
        allowance = max(2, (original[3] - original[1]) // 8)
        intended = original
        if index == len(bounds) - 1:
            if observed[2] < period[2] or not (observed[1] <= period[1] < period[3] <= observed[3]):
                return baseline
            intended = (*original[:2], period[2], original[3])
        if any(abs(old - new) > allowance for old, new in zip(intended, observed, strict=True)):
            return baseline
    if time.monotonic() >= deadline:
        return baseline
    return text + "." + baseline[len(text):]


def _prefer_enhanced(baseline, enhanced):
    if not baseline[0].strip() or not enhanced[0].strip() or baseline[0].split() == enhanced[0].split():
        return False
    original = _ocr_lines(*baseline)
    candidate = _ocr_lines(*enhanced)
    if [len(line) for line in original] != [len(line) for line in candidate]:
        return False

    score_gain = 0
    token_count = 0
    for before_line, after_line in zip(original, candidate, strict=True):
        for (before, prior_score), (after, score) in zip(before_line, after_line, strict=True):
            score_gain += score - prior_score
            token_count += 1
            if before == after:
                continue
            if len(before) != len(after) or any(char.isnumeric() for char in before + after):
                return False
            differences = [(old, new) for old, new in zip(before, after, strict=True) if old != new]
            if len(differences) != 1:
                return False
            old, new = differences[0]
            minimum_gain = 15 if old.isalnum() or new.isalnum() else 4
            if score < 85 or score - prior_score < minimum_gain:
                return False
    return score_gain >= 2 * token_count


def _recognize(ocr, picture, *, lang, timeout, allow_terminal_period=False):
    deadline = time.monotonic() + timeout
    candidate = _enhance_scan(picture)
    with candidate if candidate is not None else nullcontext():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("OCR time budget exhausted")
        if candidate is None and ("tur" not in lang.split("+") or max(picture.size) > 2000):
            return ocr.image_to_string(picture, lang=lang, timeout=remaining)
        baseline = ocr.run_and_get_multiple_output(picture, ["txt", "tsv"], lang=lang, timeout=remaining)
        if candidate is None:
            try:
                dotted = _recover_dotted_i(ocr, picture, *baseline, lang=lang, deadline=deadline)
                if dotted != baseline[0] or not allow_terminal_period:
                    return dotted
                return _recover_terminal_period(ocr, picture, *baseline, lang=lang, deadline=deadline)
            except (RuntimeError, OSError, KeyError, ValueError, TypeError, IndexError, AttributeError, csv.Error):
                # A failed or inconclusive retry keeps the baseline.
                return baseline[0]
        remaining = deadline - time.monotonic()
        if not baseline[0].strip() or remaining < 0.25:
            return baseline[0]
        try:
            enhanced = ocr.run_and_get_multiple_output(candidate, ["txt", "tsv"], lang=lang, timeout=remaining)
            if time.monotonic() < deadline and _prefer_enhanced(baseline, enhanced):
                return enhanced[0]
        except (RuntimeError, OSError, KeyError, ValueError, TypeError, IndexError, AttributeError, csv.Error):
            # A failed secondary attempt leaves the original recognition intact.
            pass
        return baseline[0]


def _extract_pdf(path):
    def scoped_import(name, globals=None, locals=None, fromlist=(), level=0):
        module = builtins.__import__(name, globals, locals, fromlist, level)
        if name == "pytesseract" and level == 0:
            return SimpleNamespace(image_to_string=lambda picture, **args: _recognize(module, picture, **args))
        return module

    # The qualified historical parser owns pagination, rasterization and exact
    # passage formatting. Bind the one native OCR import in this child only.
    namespace = {**extract.__globals__, "__builtins__": {**vars(builtins), "__import__": scoped_import}}
    parse = FunctionType(extract.__code__, namespace)
    return add_pdf_coverage_warnings(path, parse(path, ".pdf"))


def main():
    if len(sys.argv) != 3 or sys.argv[2] != ".pdf":
        return 1
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    try:
        print(json.dumps(_extract_pdf(Path(sys.argv[1])), ensure_ascii=False))
    except Exception:
        # The worker exposes its bounded failure response without parser content.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
