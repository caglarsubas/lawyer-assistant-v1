"""Recover eligible blank OCR results from corroborating raster views."""

import builtins
import csv
import json
import resource
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from types import FunctionType, SimpleNamespace
from typing import NamedTuple

from PIL import Image, ImageChops, ImageFilter, ImageOps

from .extract import extract
from .pdf_image_coverage import add_pdf_coverage_warnings
from .pdf_scan_extract import _ocr_lines, _percentile, _recognize, _runs, _word_edges, _word_lines

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


def _visible_word(gray, word, second, *, minimum=94):
    # Require exact agreement and substantial raw ink, since contrast leveling
    # can otherwise turn faint paper texture into plausible letters or digits.
    if not (min(word.confidence, second.confidence) >= minimum and any(c.isalnum() for c in word.text)):
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
        first = [*first[:-1], first[-1][:-1]]

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


def _line_bounds(words):
    return (min(word.box[0] for word in words), min(word.box[1] for word in words),
            max(word.box[2] for word in words), max(word.box[3] for word in words))


def _source_read(ocr, gray, bounds, *, mode, lang, deadline):
    left, top, right, bottom = bounds
    if mode in (8, 13):
        # Isolated word segmentation must not pull in neighboring glyphs.
        x_pad = max(8, min(16, (right - left) // 3))
        y_pad = max(12, min(24, (bottom - top) // 4))
    else:
        x_pad = y_pad = max(12, min(38, (bottom - top) // 3))
    region = (max(0, left - x_pad), max(0, top - y_pad),
              min(gray.width, right + x_pad), min(gray.height, bottom + y_pad))
    remaining = deadline - time.monotonic()
    if remaining < _MIN_RECOVERY_SECONDS:
        return []
    with gray.crop(region) as strip:
        tsv = ocr.image_to_data(strip, lang=lang, config=f"--psm {mode}", timeout=min(1.5, remaining))
    rows = _partial_words(tsv, gray, region[:2])
    return rows[0] if len(rows) == 1 and time.monotonic() < deadline else []


def _flatten_marks(text):
    return tuple("".join(c for c in unicodedata.normalize("NFD", char.casefold())
                        if not unicodedata.combining(c)) for char in text)


def _verify_short_diacritics(ocr, gray, word, target, *, lang, deadline):
    # Independent word and raw-line segmentation must see the same glyphs on
    # the original crop. Require detached ink as well as the reported marks.
    if not (2 <= len(word.text) <= 4 and word.text.isalpha() and target.text.isalpha()
            and _flatten_marks(word.text) == _flatten_marks(target.text)):
        return None
    marks = sum(bool(unicodedata.combining(char)) for char in unicodedata.normalize("NFD", target.text))
    if not marks:
        return None
    for mode in (8, 13):
        observed = _source_read(ocr, gray, word.box, mode=mode, lang=lang, deadline=deadline)
        if (len(observed) != 1 or observed[0].text != target.text or observed[0].confidence < 94
                or not _same_ink(observed[0].box, word.box)):
            return None
    with gray.crop(target.box) as glyphs:
        dark, light = glyphs.getextrema()
        if light - dark < 80:
            return None
        threshold = (dark + light) // 2
        with glyphs.point([255 if shade < threshold else 0 for shade in range(256)]) as mask:
            _, rows = mask.getprojection()
            if len(list(_runs(rows))) < 1 + marks:
                return None
    return target.text


def _registered_lines(first, second):
    pairs = []
    next_line = 0
    for i, line in enumerate(first):
        for j in range(next_line, len(second)):
            other = second[j]
            if [word.text for word in line] == [word.text for word in other] and all(
                _same_ink(word.box, reread.box) for word, reread in zip(line, other, strict=True)
            ):
                pairs.append((i, j, line, other))
                next_line = j + 1
                break
    if not pairs:
        return []
    # Layout can emit a second, inconsistent row from only the top strokes of
    # a word. It supplies no additional ink region or independent reading.
    for side, capture in enumerate((first, second)):
        used = {pair[side] for pair in pairs}
        for index, line in enumerate(capture):
            if index in used:
                continue
            for fragment in line:
                if not any(fragment.box[3] - fragment.box[1] <= (word.box[3] - word.box[1]) / 3
                           and _fraction_covered(fragment.box, word.box) >= 0.75
                           for pair in pairs for word in pair[2 + side]):
                    return []
    return [(line, reread) for _, _, line, reread in pairs]


def _same_line(first, second):
    _, top, _, bottom = first
    _, newer_top, _, newer_bottom = second
    overlap = min(bottom, newer_bottom) - max(top, newer_top)
    return overlap >= 0.72 * min(bottom - top, newer_bottom - newer_top)


def _source_aligned_fragment(previous, candidate):
    if any(char.isnumeric() for char in previous.text):
        return False
    if _restored_prefix(previous, candidate):
        return True
    # A surviving short prefix can clip on either edge of the source word.
    # The original crop confirms continuation into visibly present ink.
    if previous.text.isalpha() and candidate.text.startswith(previous.text) and previous.text != candidate.text:
        left, top, right, bottom = previous.box
        x1, y1, x2, y2 = candidate.box
        return (x2 > right and abs(x1 - left) <= max(4, (y2 - y1) // 6)
                and (min(bottom, y2) - max(top, y1) >= 0.64 * (bottom - top)
                     or (bottom - top <= 3 and y1 - bottom in range(0, 4))))
    return (previous.confidence < 90 and previous.text.isalpha() and candidate.text.isalpha()
            and len(previous.text) == len(candidate.text)
            and sum(a != b for a, b in zip(previous.text, candidate.text, strict=True)) == 1
            and _same_existing_word(previous.box, candidate.box))


def _line_matches_source(ocr, gray, line, *, lang, deadline):
    source = _source_read(ocr, gray, _line_bounds(line), mode=7, lang=lang, deadline=deadline)
    if len(source) != len(line) or any(
        _flatten_marks(old.text) != _flatten_marks(new.text) or not _same_existing_word(old.box, new.box)
        for old, new in zip(line, source, strict=True)
    ):
        return []
    return source


def _reconcile_source_lines(ocr, gray, baseline, original, first, second, *, lang, deadline):
    if [word.text for line in original for word in line] != baseline.split():
        return baseline
    pairs = _registered_lines(first, second)
    if not pairs or len(pairs) > 18:
        return baseline
    regions = [_line_bounds(line) for line, _ in pairs]
    predecessors = [[] for _ in pairs]
    current = 0
    for line in original:
        positions = [index for index in range(current, len(regions)) if _same_line(_line_bounds(line), regions[index])]
        if len(positions) != 1:
            return baseline
        current = positions[0]
        predecessors[current].extend(line)

    result = []
    for (line, reread), earlier in zip(pairs, predecessors, strict=True):
        registered = {word for word in line if any(
            word.text == prior.text and _same_existing_word(prior.box, word.box) for prior in earlier
        )}
        needs_source = (any(word not in registered and not _visible_word(gray, word, other)
                            for word, other in zip(line, reread, strict=True))
                        or any(not any(prior.text == word.text and _same_existing_word(prior.box, word.box)
                                       or _restored_prefix(prior, word) for word in line) for prior in earlier))
        source = _line_matches_source(ocr, gray, line, lang=lang, deadline=deadline) if needs_source else []
        if needs_source and not source:
            return baseline

        index = 0
        tokens = []
        for position, (word, other) in enumerate(zip(line, reread, strict=True)):
            prior = earlier[index] if index < len(earlier) else None
            unchanged = prior and prior.text == word.text and _same_existing_word(prior.box, word.box)
            prefix = prior and _restored_prefix(prior, word)
            # A marginal score can support a word only with an identical
            # registered raw-line reading and strong combined evidence.
            corroborated = bool(source and source[position].text == word.text and source[position].confidence >= 85
                                and word.confidence + other.confidence + source[position].confidence >= 270)
            if not unchanged and not (_visible_word(gray, word, other) or (
                corroborated and _visible_word(gray, word, other, minimum=85)
            )):
                return baseline
            extended = (prior and corroborated and _source_aligned_fragment(prior, word))
            if unchanged or prefix or extended:
                index += 1
                if extended and word.text.startswith(prior.text):
                    while index < len(earlier) and earlier[index].confidence < 50 and not any(
                        char.isnumeric() for char in earlier[index].text
                    ) and _fraction_covered(earlier[index].box, word.box) >= 0.8:
                        index += 1
            token = word.text
            if unchanged and source and source[position].text != token:
                token = _verify_short_diacritics(ocr, gray, word, source[position], lang=lang, deadline=deadline)
                if token is None:
                    return baseline
            tokens.append(token)
        if index != len(earlier):
            return baseline
        result.append(" ".join(tokens))
    text = "\n".join(result)
    return text if text.split() != baseline.split() else baseline


def _remove_blank_recovery_scuff(ocr, picture, baseline, *, lang, deadline):
    text = baseline.rstrip()
    if not text.endswith(" .") or len(text.splitlines()[-1].split()) < 3:
        return baseline
    with picture.convert("L") as gray:
        bounds = _partial_crop(gray)
        if bounds is None:
            return baseline
        left, top, right, _ = bounds
        with gray.crop(bounds) as cropped:
            tones = cropped.histogram()
            threshold = min(158, (_percentile(tones, 0.003) + _percentile(tones, 0.85)) // 2)
            with cropped.point([255 if shade < threshold else 0 for shade in range(256)]) as mask:
                _, rows = mask.getprojection()
                bands = list(_runs(rows))
        if not bands:
            return baseline
        start, stop = bands[-1]
        for earlier_start, earlier_stop in reversed(bands[:-1]):
            if start - earlier_stop > 26 or stop - earlier_start > 170:
                break
            start = earlier_start
        line = _source_read(ocr, gray, (left, top + start, right, top + stop), mode=7, lang=lang, deadline=deadline)
        if [word.text for word in line] == text.splitlines()[-1].split() and _elongated_scuff(gray, line[-1], line[-2]):
            return text[:-2] + baseline[len(text):]
    return baseline


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
        if result == baseline:
            result = _reconcile_source_lines(ocr, gray, baseline, original, first, second, lang=lang, deadline=deadline)
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
                try:
                    return _remove_blank_recovery_scuff(ocr, picture, primary, lang=lang, deadline=deadline)
                except (RuntimeError, OSError, KeyError, ValueError, TypeError, IndexError, AttributeError, csv.Error):
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
