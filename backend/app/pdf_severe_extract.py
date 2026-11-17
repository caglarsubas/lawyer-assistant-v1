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
from typing import NamedTuple

from PIL import Image, ImageChops, ImageFilter, ImageOps

from .extract import extract
from .pdf_image_coverage import add_pdf_coverage_warnings
from .pdf_scan_extract import _ocr_lines, _percentile, _recognize, _word_edges, _word_lines

PARTIAL_WARNING = "Sayfa {n}: OCR sonucu kısmi olabilir; önemli bilgileri özgün sayfada doğrulayın."
_MAX_RASTER_EDGE = 2_000
_RECOVERY_PROFILES = ((28, 5, 4), (17, 3, 8))
_MIN_RECOVERY_SECONDS = 0.25


class _Word(NamedTuple):
    text: str
    confidence: float
    box: tuple[int, int, int, int]


def _partial_words(tsv, picture, origin=(0, 0)):
    lines = []
    for line in _word_lines(tsv):
        words = []
        for row, token in line:
            box = _word_edges(row, origin)
            left, top, right, bottom = box
            confidence = float(row["conf"])
            if not (0 <= confidence <= 100 and 0 <= left < right <= picture.width
                    and 0 <= top < bottom <= picture.height):
                raise ValueError("OCR word is outside the original raster")
            words.append(_Word(token, confidence, box))
        lines.append(words)
    return lines


def _partial_crop(gray):
    # Bound the alternate reads to visibly dark source ink. Ignore a thin page
    # boundary, which can carry dark scanner-edge lines and rotation triangles.
    margin = max(4, min(gray.size) // 40)
    with gray.crop((margin, margin, gray.width - margin, gray.height - margin)) as interior:
        tones = interior.histogram()
        threshold = min(150, (_percentile(tones, 0.0025) + _percentile(tones, 0.85)) // 2)
        with interior.point([255 if value < threshold else 0 for value in range(256)]) as mask:
            region = mask.getbbox()
    if region is None:
        return None
    left, top, right, bottom = (edge + margin for edge in region)
    padding = max(24, min(gray.size) // 27)
    return (max(0, left - padding), max(0, top - padding),
            min(gray.width, right + padding), min(gray.height, bottom + padding))


def _read_leveled(ocr, gray, region, *, radius, gain, lang, deadline):
    # Remove the broad paper gradient without rotating or rescaling the ink.
    # Native word boxes from both reads can be registered to the same pixels.
    with gray.crop(region) as crop, crop.filter(ImageFilter.GaussianBlur(radius)) as paper:
        with ImageChops.subtract(paper, crop) as detail:
            with detail.point([max(0, 255 - max(0, shade - 7) * gain) for shade in range(256)]) as view:
                remaining = deadline - time.monotonic()
                if remaining < _MIN_RECOVERY_SECONDS:
                    return []
                result = ocr.image_to_data(view, lang=lang, config="--psm 3", timeout=min(2, remaining))
    return _partial_words(result, gray, region[:2])


def _fraction_covered(original, candidate):
    left, top, right, bottom = original
    width = max(0, min(right, candidate[2]) - max(left, candidate[0]))
    height = max(0, min(bottom, candidate[3]) - max(top, candidate[1]))
    return width * height / ((right - left) * (bottom - top))


def _same_ink(first, second):
    return min(_fraction_covered(first, second), _fraction_covered(second, first)) >= 0.72


def _same_existing_word(first, second):
    # Adaptive segmentation may inflate the raw box with the dark gutter.
    # Preserve an exact word when one box almost contains the other and both
    # still share a majority of their area. The alternate pair stays stricter.
    cover = _fraction_covered(first, second), _fraction_covered(second, first)
    return min(cover) >= 0.72 or (min(cover) >= 0.55 and max(cover) >= 0.90)


def _visible_word(gray, word, second):
    # Require exact agreement and substantial raw ink, since contrast leveling
    # can otherwise turn faint paper texture into plausible letters or digits.
    if not (min(word.confidence, second.confidence) >= 94 and any(c.isalnum() for c in word.text)):
        return False
    with gray.crop(word.box) as crop:
        tones = crop.histogram()
    return _percentile(tones, 0.8) - _percentile(tones, 0.04) >= 80


def _elongated_scuff(gray, mark, last):
    left, top, right, bottom = mark.box
    character_height = last.box[3] - last.box[1]
    if not (2 <= left - last.box[2] <= character_height // 2
            and top >= last.box[1] + character_height // 2
            and bottom <= last.box[3] + character_height // 6):
        return False
    with gray.crop(mark.box) as crop:
        dark, light = crop.getextrema()
        if light - dark < 24:
            return False
        for ratio in (0.45, 0.60):
            threshold = round(dark + (light - dark) * ratio)
            with crop.point([255 if shade < threshold else 0 for shade in range(256)]) as ink:
                source = ink.getbbox()
                if source is None:
                    return False
                width, height = source[2] - source[0], source[3] - source[1]
                # A compact period is close to square. Require a thin stroke
                # with substantially greater horizontal than vertical extent.
                if not (width >= 3 * height and height <= character_height // 8):
                    return False
    return True


def _restored_prefix(original, after):
    # Restore only a left-clipped, nonnumeric fragment with a surviving suffix.
    # A shifted or substituted whole word, date or amount stays untouched.
    height = original.box[3] - original.box[1]
    exact_tail = len(original.text) >= 3 and after.text.endswith(original.text)
    tail_preserved = exact_tail or (original.confidence < 80 and after.text[-1:] == original.text[-1:])
    return (tail_preserved and original.text.isalpha() and after.text.isalpha()
            and len(original.text) < len(after.text)
            and original.box[0] - after.box[0] >= height // 4
            and abs(original.box[2] - after.box[2]) <= max(2, height // 8)
            and _fraction_covered(original.box, after.box) >= (0.68 if exact_tail else 0.74))


def _false_digit_prefix(gray, digit, suffix, word):
    # A clipped first word can be split into a spurious digit and a readable
    # suffix. Its claimed number box must contain only a cut-off trace inside
    # the corroborated word's original ink, never a full visible numeral.
    if not (digit.confidence < 80 and suffix.confidence < 80 and len(digit.text) == 1
            and digit.text in "0123456789" and len(suffix.text) >= 3 and word.text.endswith(suffix.text)
            and _restored_prefix(suffix, word) and digit.box[2] <= suffix.box[0]):
        return False
    left, top, _, bottom = digit.box
    height = word.box[3] - word.box[1]
    with gray.crop(digit.box) as tile:
        dark, light = tile.getextrema()
        if light - dark < 64:
            return False
        for ratio in (0.45, 0.60):
            threshold = round(dark + (light - dark) * ratio)
            with tile.point([255 if shade < threshold else 0 for shade in range(256)]) as ink:
                bounds = ink.getbbox()
            if bounds is None:
                return False
            x1, y1, x2, y2 = bounds
            if (x1 != 0 or y2 != tile.height or y2 - y1 > height // 3 or y1 < 2 * (bottom - top) // 3
                    or not (word.box[0] <= left + x1 < left + x2 <= word.box[2]
                            and word.box[1] <= top + y1 < top + y2 <= word.box[3])):
                return False
    return True


def _reconcile_partial(gray, baseline, original, first, second):
    if not first or [[word.text for word in line] for line in first] != [
        [word.text for word in line] for line in second
    ]:
        return baseline
    original_words = [word for line in original for word in line]
    primary = [word for line in first for word in line]
    confirmation = [word for line in second for word in line]
    if not (2 <= len(original_words) <= 300 and 2 <= len(primary) <= 300
            and [word.text for word in original_words] == baseline.split()
            and all(_same_ink(a.box, b.box) for a, b in zip(primary, confirmation, strict=True))):
        return baseline

    retained = []
    for line in original:
        matches = [word[0] for word, reread in zip(first, second, strict=True)
                   if len(line) >= 3 and _false_digit_prefix(gray, line[0], line[1], word[0])
                   and _visible_word(gray, word[0], reread[0])]
        retained.extend(line[1:] if len(matches) == 1 else line)
    original = retained

    old_tail, new_tail = original[-1], primary[-1]
    scuff = (
        len(first[-1]) >= 3 and new_tail.text == "." and old_tail.confidence < 90
        and old_tail.text == primary[-2].text + "." and primary[-2].text.isalpha()
        and _fraction_covered(new_tail.box, old_tail.box) >= 0.8
        and _elongated_scuff(gray, new_tail, primary[-2])
        and _elongated_scuff(gray, confirmation[-1], confirmation[-2])
    )
    if scuff:
        primary.pop()
        confirmation.pop()
        first[-1].pop()

    next_word = 0
    for index, old in enumerate(original):
        for position in range(next_word, len(primary)):
            candidate, reread = primary[position], confirmation[position]
            if candidate.text == old.text and _same_existing_word(old.box, candidate.box):
                break
            if scuff and index == len(original) - 1 and position == len(primary) - 1:
                if _same_ink(old.box, candidate.box):
                    break
            elif _restored_prefix(old, candidate) and _visible_word(gray, candidate, reread):
                break
            if not _visible_word(gray, candidate, reread):
                return baseline
        else:
            return baseline
        next_word = position + 1
    if any(not _visible_word(gray, word, reread) for word, reread in zip(
        primary[next_word:], confirmation[next_word:], strict=True,
    )):
        return baseline
    if [word.text for word in primary] == baseline.split():
        return baseline
    return "\n".join(" ".join(word.text for word in line) for line in first)


def _recover_partial(ocr, picture, baseline, original_tsv, *, lang, deadline):
    if deadline - time.monotonic() < 0.5:
        return baseline
    with picture.convert("L") as gray:
        original = _partial_words(original_tsv, gray)
        if not original:
            return baseline
        region = _partial_crop(gray)
        if region is None or any(_fraction_covered(word.box, region) < 0.95 for line in original for word in line):
            return baseline
        first = _read_leveled(ocr, gray, region, radius=30, gain=1, lang=lang, deadline=deadline)
        if not first:
            return baseline
        second = _read_leveled(ocr, gray, region, radius=18, gain=2, lang=lang, deadline=deadline)
        result = _reconcile_partial(gray, baseline, original, first, second)
    return result if time.monotonic() < deadline else baseline


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
    text = _recognize(ocr, picture, lang=lang, timeout=remaining, allow_terminal_period=degraded,
                      recover_partial=_recover_partial if degraded else None)
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
