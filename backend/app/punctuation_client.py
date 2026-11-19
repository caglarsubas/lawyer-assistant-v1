"""Bounded authenticated transport for source-page punctuation observations."""

import base64
import binascii
import hashlib
import json
import time

import httpx

from .extraction_client import MAX_RESPONSE_BYTES, ExtractionClient, ExtractionError, validate_document
from .punctuation_assessment import valid_assessment
from .punctuation_capture import MAX_PNG_BYTES, PRODUCER_RECIPE, PRODUCER_SHA256


def capture_run_sha256(capture):
    identity = {key: value for key, value in capture.items() if key not in {"png", "run_sha256"}}
    identity["raster_sha256"] = hashlib.sha256(capture["png"]).hexdigest()
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_capture_wire(payload, source_sha256, page):
    fields = {"source_sha256", "page", "page_count", "producer_sha256", "producer_recipe", "png",
              "run_sha256", "events", "assessment"}
    if (not isinstance(payload, dict) or set(payload) != fields
            or payload["source_sha256"] != source_sha256
            or type(payload["page"]) is not int or payload["page"] != page
            or type(payload["page_count"]) is not int or not page <= payload["page_count"] <= 500
            or payload["producer_sha256"] != PRODUCER_SHA256 or payload["producer_recipe"] != PRODUCER_RECIPE
            or not isinstance(payload["png"], str) or len(payload["png"]) > 4 * ((MAX_PNG_BYTES + 2) // 3)
            or not isinstance(payload["events"], list) or len(payload["events"]) > 8
            or not valid_assessment(payload["assessment"], payload["events"])):
        raise ExtractionError("Punctuation capture binding is unavailable")
    try:
        capture = {**payload, "png": base64.b64decode(payload["png"], validate=True)}
        if (not 0 < len(capture["png"]) <= MAX_PNG_BYTES
                or not capture["png"].startswith(b"\x89PNG\r\n\x1a\n")
                or capture_run_sha256(capture) != capture["run_sha256"]):
            raise ValueError("Capture digest mismatch")
        return capture
    except (ValueError, TypeError, binascii.Error, RecursionError) as exc:
        raise ExtractionError("Punctuation capture could not be safely consumed") from exc


class PunctuationClient(ExtractionClient):
    def execute_capture(self, content, page):
        validate_document(content, ".pdf")
        if not content.startswith(b"%PDF-") or type(page) is not int or not 1 <= page <= 500:
            raise ExtractionError("Punctuation source page is unavailable")
        deadline = time.monotonic() + 30
        try:
            with httpx.Client(timeout=httpx.Timeout(23, connect=3, write=5, pool=3),
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", self.base_url + f"/punctuation-capture/{page}", content=content,
                                   headers={"Authorization": "Bearer " + self.token,
                                            "Content-Type": "application/octet-stream",
                                            "Accept-Encoding": "identity"}) as response:
                    if (response.status_code != 200
                            or response.headers.get("content-encoding", "identity").lower() != "identity"):
                        raise ExtractionError("Punctuation worker did not accept the source")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline or len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ExtractionError("Punctuation response budget exceeded")
                        raw.extend(chunk)
            if time.monotonic() >= deadline:
                raise ExtractionError("Punctuation response budget exceeded")
            return validate_capture_wire(json.loads(raw), hashlib.sha256(content).hexdigest(), page)
        except (httpx.HTTPError, ValueError, TypeError, RecursionError) as exc:
            raise ExtractionError("Punctuation response could not be safely consumed") from exc
