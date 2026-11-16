"""Recover eligible blank OCR results from corroborating raster views."""

import builtins
import csv
import json
import resource
import subprocess
import sys
import time
from pathlib import Path
from types import FunctionType, SimpleNamespace

from PIL import Image, ImageChops, ImageFilter, ImageOps

from .extract import extract
from .pdf_image_coverage import add_pdf_coverage_warnings
from .pdf_scan_extract import _ocr_lines, _percentile, _recognize

PARTIAL_WARNING = "Sayfa {n}: OCR sonucu kısmi olabilir; önemli bilgileri özgün sayfada doğrulayın."
_MAX_RASTER_EDGE = 2_000
_RECOVERY_PROFILES = ((28, 5, 4), (17, 3, 8))
_MIN_RECOVERY_SECONDS = 0.25


def _is_degraded_scan(picture):
    if min(picture.size) < 64 or max(picture.size) > _MAX_RASTER_EDGE:
        return False
    with picture.convert("L") as gray:
        tones = gray.histogram()
        paper = _percentile(tones, 0.85)
        ink = _percentile(tones, 0.0025)
        if paper >= 210 and 6 <= paper - ink <= 43:
            return True
        gray.thumbnail((448, 448), Image.Resampling.BILINEAR)
        with gray.filter(ImageFilter.GaussianBlur(8)) as background:
            tones = background.histogram()
        return paper >= 180 and _percentile(tones, 0.85) - _percentile(tones, 0.15) >= 18


def _level_and_deskew(picture, radius, noise_floor, gain):
    # Extract fine contrast from the local paper estimate. Work on derivatives;
    # neither the source PDF nor the rendering used by the original read changes.
    with picture.convert("L") as gray, gray.filter(ImageFilter.GaussianBlur(radius)) as background:
        with ImageChops.subtract(background, gray) as detail:
            leveled = detail.point([max(0, 255 - max(0, value - noise_floor) * gain) for value in range(256)])
    with leveled, ImageOps.invert(leveled) as preview:
        preview.thumbnail((460, 460), Image.Resampling.BILINEAR)
        with preview.point([255 if value > 30 else 0 for value in range(256)]) as mask:
            scores = []
            for angle in range(-9, 10):
                with mask.rotate(angle, resample=Image.Resampling.NEAREST, expand=True) as rotated:
                    with rotated.resize((1, rotated.height), Image.Resampling.BOX) as rows:
                        scores.append((sum(value * value for value in rows.tobytes()), -abs(angle), angle))
        return leveled.rotate(max(scores)[2], resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)


def _confident_lines(text, tsv):
    lines = _ocr_lines(text, tsv)
    words = [word for line in lines for word in line]
    if len(words) < 2 or not any(len(word) >= 3 and any(c.isalpha() for c in word) for word, _ in words):
        return None
    if any(score < (85 if any(c.isnumeric() for c in word) else 60) for word, score in words):
        return None
    if sum(score for _, score in words) < 85 * len(words):
        return None
    return [[word for word, _ in line] for line in lines]


def _recover_blank(ocr, picture, *, lang, deadline):
    def observe(profile):
        if deadline - time.monotonic() < _MIN_RECOVERY_SECONDS:
            return "", None
        with _level_and_deskew(picture, *profile) as view:
            remaining = deadline - time.monotonic()
            if remaining < _MIN_RECOVERY_SECONDS:
                return "", None
            text, tsv = ocr.run_and_get_multiple_output(view, ["txt", "tsv"], lang=lang, timeout=remaining)
        if time.monotonic() >= deadline:
            return "", None
        return text, _confident_lines(text, tsv)

    try:
        primary, first = observe(_RECOVERY_PROFILES[0])
        if first is not None:
            _, second = observe(_RECOVERY_PROFILES[1])
            if first == second and time.monotonic() < deadline:
                return primary
    except (RuntimeError, OSError, KeyError, ValueError, TypeError, IndexError, AttributeError, csv.Error):
        # An invalid or timed-out alternate is insufficient to recover text.
        pass
    return ""


def _read_scan(ocr, picture, *, lang, timeout):
    deadline = time.monotonic() + timeout
    degraded = _is_degraded_scan(picture)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("OCR time budget exhausted")
    text = _recognize(ocr, picture, lang=lang, timeout=remaining, allow_terminal_period=degraded)
    if degraded and not text.strip():
        text = _recover_blank(ocr, picture, lang=lang, deadline=deadline)
    return text, degraded


def _extract_pdf(path):
    page = None
    partial = set()

    def rasterize(command, **kwargs):
        nonlocal page
        page = None
        result = subprocess.run(command, **kwargs)
        if len(command) >= 5 and command[:2] == ["pdftoppm", "-f"] and command[3:5] == ["-l", command[2]]:
            page = int(command[2])
        return result

    def recognize(ocr, picture, **args):
        text, degraded = _read_scan(ocr, picture, **args)
        if degraded and page is not None and text.strip():
            partial.add(page)
        return text

    def scoped_import(name, globals=None, locals=None, fromlist=(), level=0):
        module = builtins.__import__(name, globals, locals, fromlist, level)
        if name == "pytesseract" and level == 0:
            return SimpleNamespace(image_to_string=lambda picture, **args: recognize(module, picture, **args))
        return module

    namespace = {
        **extract.__globals__,
        "subprocess": SimpleNamespace(run=rasterize, SubprocessError=subprocess.SubprocessError),
        "__builtins__": {**vars(builtins), "__import__": scoped_import},
    }
    result = FunctionType(extract.__code__, namespace)(path, ".pdf")
    passages = {p["locator"] for p in result["passages"]}
    result["warnings"].extend(PARTIAL_WARNING.format(n=n) for n in sorted(partial) if f"Sayfa {n}" in passages)
    return add_pdf_coverage_warnings(path, result)


def main():
    if len(sys.argv) != 3 or sys.argv[2] != ".pdf":
        return 1
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    try:
        print(json.dumps(_extract_pdf(Path(sys.argv[1])), ensure_ascii=False))
    except Exception:
        # Expose only the isolated worker's controlled extraction failure.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
