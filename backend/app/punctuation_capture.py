"""Bounded source-page OCR sidecar; saved document text is owned by its caller."""

import base64
import hashlib
import json
import resource
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from . import ocr_punctuation_amount as amount
from . import ocr_punctuation_regions as regions

PRODUCER_RECIPE = "native-pdf-punctuation-v1"
_SOURCE_FILES = ("punctuation_capture.py", "ocr_punctuation_amount.py", "ocr_punctuation_regions.py",
                 "pdf_severe_extract.py", "pdf_scan_extract.py", "extract.py", "pdf_image_coverage.py")
PRODUCER_SHA256 = hashlib.sha256(PRODUCER_RECIPE.encode() + b"\0" + b"\n".join(
    name.encode() + b":" + hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest().encode()
    for name in _SOURCE_FILES
)).hexdigest()
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_PNG_BYTES = 4_000_000


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def capture_document(content, page):
    if (not isinstance(content, bytes) or not content.startswith(b"%PDF-")
            or not 0 < len(content) <= MAX_DOCUMENT_BYTES or type(page) is not int or not 1 <= page <= 500):
        raise ValueError("Source capture input is unavailable")
    reader = PdfReader(BytesIO(content), strict=True)
    if reader.is_encrypted or not 1 <= page <= len(reader.pages) <= 500:
        raise ValueError("Source page is unavailable")
    with tempfile.TemporaryDirectory(prefix="la-punctuation-page-") as directory:
        source = Path(directory) / "source.pdf"
        source.write_bytes(content)
        source.chmod(0o600)
        rendered = subprocess.run(
            ["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-scale-to", "2000", "-png", str(source)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=6,
        ).stdout
        if len(rendered) > MAX_PNG_BYTES:
            raise ValueError("Raster exceeds its source capture bound")
        with Image.open(BytesIO(rendered)) as image:
            if image.width * image.height > 4_000_000:
                raise ValueError("Raster dimensions exceed their bound")
            gray = image.convert("L")
    with gray:
        deadline = time.monotonic() + 6
        frame = (0, 0, gray.width, gray.height)
        # Every nomination is re-read from this original raster. Quote text and
        # previously extracted passage offsets never supply a location.
        raw = amount.read_rows(gray, frame, mode=3, profile=None, deadline=deadline)
        nominated = raw
        if not any(amount.field([word.text for word in line]) for line in raw):
            nominated = amount.read_rows(gray, frame, mode=3, profile=(18, 7, 2), deadline=deadline)
        baseline = "\n".join(" ".join(word.text for word in line) for line in nominated)
        events = []
        amount.observe_disputed_amounts(gray, nominated, baseline, regions, deadline, on_punctuation=events.append)
        if len(events) > 8:
            raise ValueError("Source observation limit exceeded")
        png_output = BytesIO()
        gray.save(png_output, format="PNG")
        png = png_output.getvalue()
        if len(png) > MAX_PNG_BYTES:
            raise ValueError("Raster exceeds its output bound")
    result = {"source_sha256": _digest(content), "page": page, "page_count": len(reader.pages),
              "producer_sha256": PRODUCER_SHA256, "producer_recipe": PRODUCER_RECIPE,
              "png": png, "events": events}
    identity = {key: value for key, value in result.items() if key != "png"}
    identity["raster_sha256"] = _digest(png)
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    result["run_sha256"] = _digest(canonical.encode())
    return result


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (9 * 1024 * 1024, 9 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    source, page = Path(sys.argv[1]), int(sys.argv[2])
    with source.open("rb") as stream:
        content = stream.read(MAX_DOCUMENT_BYTES + 1)
    result = capture_document(content, page)
    result["png"] = base64.b64encode(result["png"]).decode("ascii")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"error":"Source page capture failed"}')
        sys.exit(1)
