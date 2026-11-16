"""Run the existing PDF parser with a conservative, bounded scan enhancement."""

import builtins
import csv
import json
import resource
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from types import FunctionType, SimpleNamespace

from PIL import Image, ImageOps

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
    rows = csv.DictReader(tsv.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in rows:
        # Tesseract can emit level-5 layout rows containing only spaces.
        if row.get("level") != "5" or not (word := row.get("text")) or not word.strip():
            continue
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


def _recognize(ocr, picture, *, lang, timeout):
    deadline = time.monotonic() + timeout
    candidate = _enhance_scan(picture)
    with candidate if candidate is not None else nullcontext():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("OCR time budget exhausted")
        if candidate is None:
            return ocr.image_to_string(picture, lang=lang, timeout=remaining)
        baseline = ocr.run_and_get_multiple_output(picture, ["txt", "tsv"], lang=lang, timeout=remaining)
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
