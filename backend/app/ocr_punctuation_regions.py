"""Original-raster region locator retained from the qualified regional OCR candidate."""

from PIL import Image

from . import pdf_scan_extract as scan
from . import pdf_severe_extract as severe


def overlap(a, b):
    return min(severe._fraction_covered(a, b), severe._fraction_covered(b, a))


def intersect(a, b):
    return max(severe._fraction_covered(a, b), severe._fraction_covered(b, a))


def locate(detail, contrast):
    margin = max(28, min(detail.size) // 34)
    with detail.point([255 if v >= contrast else 0 for v in range(256)]) as mask:
        mask.paste(0, (0, 0, mask.width, margin))
        mask.paste(0, (0, mask.height - margin, mask.width, mask.height))
        mask.paste(0, (0, 0, margin, mask.height))
        mask.paste(0, (mask.width - margin, 0, mask.width, mask.height))
        with mask.resize((1, mask.height), Image.Resampling.BOX) as counts:
            active = list(scan._runs([v >= 1 for v in counts.tobytes()]))
        bands = []
        for top, bottom in active:
            if bands and top - bands[-1][1] < 16:
                bands[-1] = (bands[-1][0], bottom)
            else:
                bands.append((top, bottom))
        cells = []
        for top, bottom in bands:
            if not 18 <= bottom - top <= 140:
                continue
            with mask.crop((0, top, mask.width, bottom)) as band:
                groups = []
                for left, right in scan._runs(band.getprojection()[0]):
                    if groups and left - groups[-1][1] < max(36, (bottom - top) * .85):
                        groups[-1] = (groups[-1][0], right)
                    else:
                        groups.append((left, right))
                for left, right in groups:
                    if right - left >= 62:
                        with band.crop((left, 0, right, band.height)) as rectangle:
                            x1, y1, x2, y2 = rectangle.getbbox()
                        cells.append((left + x1, top + y1, left + x2, top + y2))
        return cells
