"""Bounded transport to the isolated parser; never forwards matter or provider metadata."""

import ipaddress
import json
import time
from urllib.parse import urlsplit

import httpx

from .extract import SUPPORTED_SUFFIXES

ALLOWED_SUFFIXES = SUPPORTED_SUFFIXES
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 9 * 1024 * 1024
MAX_TEXT_CHARACTERS = 2_000_000
REQUEST_BUDGET_SECONDS = 80
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
))


class ExtractionError(Exception):
    """The parser did not produce a safely consumable result."""


def validate_origin(base_url):
    try:
        uri = urlsplit(base_url)
        if (uri.scheme not in ("http", "https") or not uri.hostname or uri.username or uri.password
                or uri.path not in ("", "/") or uri.query or uri.fragment or uri.port == 0
                or base_url != base_url.strip() or "\\" in base_url
                or any(ord(char) < 32 or ord(char) == 127 for char in base_url)):
            raise ValueError("Invalid extraction origin")
        if uri.hostname != "extractor":
            address = ipaddress.ip_address(uri.hostname)
            if (not (address.is_loopback or any(address in network for network in PRIVATE_NETWORKS))
                    or address.is_link_local or address.is_unspecified or address.is_multicast
                    or (address.is_reserved and not address.is_loopback)
                    or getattr(address, "ipv4_mapped", None) is not None or "%" in uri.hostname):
                raise ValueError("Nonprivate extraction origin")
    except (ValueError, TypeError) as error:
        raise ExtractionError("Extraction requires the isolated extractor service or a vetted private IP") from error


def validate_document(content, suffix):
    if suffix not in ALLOWED_SUFFIXES:
        raise ExtractionError("Extraction format is not admitted")
    if not isinstance(content, bytes) or not 1 <= len(content) <= MAX_DOCUMENT_BYTES:
        raise ExtractionError("Document size is outside the extraction limit")


def _text(value, maximum):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= maximum
            and not any((ord(char) < 32 and char not in "\t\n\r")
                        or 0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF)
                        for char in value))


def validate_result(result):
    """Only parsed text and locators cross back; no executable/identity/path fields."""
    if not isinstance(result, dict) or set(result) != {"passages", "warnings", "page_count", "passage_count"}:
        raise ExtractionError("Unsupported extraction result shape")
    passages, warnings = result["passages"], result["warnings"]
    if not isinstance(passages, list) or len(passages) > 20000:
        raise ExtractionError("Extraction passage limit exceeded")
    if type(result["passage_count"]) is not int or result["passage_count"] != len(passages):
        raise ExtractionError("Extraction passage count mismatch")
    page_count = result["page_count"]
    if page_count is not None and (type(page_count) is not int or not 1 <= page_count <= 500):
        raise ExtractionError("Extraction page limit exceeded")
    if not isinstance(warnings, list) or len(warnings) > 1000 or any(not _text(w, 1000) for w in warnings):
        raise ExtractionError("Invalid extraction warnings")
    if sum(len(w) for w in warnings) > 100000:
        raise ExtractionError("Extraction warnings limit exceeded")
    total = 0
    for passage in passages:
        if (not isinstance(passage, dict) or set(passage) != {"locator", "text"}
                or not _text(passage["locator"], 400) or not _text(passage["text"], MAX_TEXT_CHARACTERS)):
            raise ExtractionError("Invalid extracted passage")
        total += len(passage["text"])
        if total > MAX_TEXT_CHARACTERS:
            raise ExtractionError("Extracted text limit exceeded")
    return result


class ExtractionClient:
    def __init__(self, base_url, token):
        validate_origin(base_url)
        if not isinstance(token, str) or len(token) < 32:
            raise ExtractionError("A separate extraction token of at least 32 characters is required")
        self.base_url, self.token = base_url.rstrip("/"), token

    def probe(self):
        """Authenticate the worker without uploading any document or invoking a parser."""
        failure = {"status": "unavailable", "issues": [{"code": "extractor_unavailable",
                   "message": "Yalıtılmış belge işleme hizmeti doğrulanamadı."}]}
        deadline = time.monotonic() + 4
        try:
            with httpx.Client(timeout=httpx.Timeout(3, connect=2), follow_redirects=False,
                              trust_env=False) as client:
                with client.stream("GET", self.base_url + "/ready", headers={
                    "Authorization": "Bearer " + self.token, "Accept-Encoding": "identity",
                }) as response:
                    if (response.status_code != 200
                            or response.headers.get("content-encoding", "identity").lower() != "identity"):
                        return failure
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() > deadline or len(raw) + len(chunk) > 4096:
                            return failure
                        raw.extend(chunk)
            payload = json.loads(raw)
            if (time.monotonic() > deadline or payload != {
                "status": "ready", "protocol": "isolated-extraction-v1",
                "max_document_bytes": MAX_DOCUMENT_BYTES,
            }):
                return failure
            return {"status": "ready", "issues": [], "authenticated": True}
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            return failure

    def execute(self, content, suffix):
        validate_document(content, suffix)
        deadline = time.monotonic() + REQUEST_BUDGET_SECONDS
        try:
            with httpx.Client(timeout=httpx.Timeout(65, connect=3, write=10, pool=3),
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", self.base_url + "/extract", content=content, headers={
                    "Authorization": "Bearer " + self.token, "Content-Type": "application/octet-stream",
                    "X-Document-Suffix": suffix, "Accept-Encoding": "identity",
                }) as response:
                    if response.status_code != 200:
                        raise ExtractionError("Extraction worker did not accept the document")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ExtractionError("Compressed extraction responses are prohibited")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise ExtractionError("Extraction response exceeded its total time budget")
                        if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ExtractionError("Extraction response size exceeded")
                        raw.extend(chunk)
            if time.monotonic() >= deadline:
                raise ExtractionError("Extraction response exceeded its total time budget")
            return validate_result(json.loads(raw))
        except (httpx.HTTPError, ValueError, TypeError, RecursionError) as error:
            raise ExtractionError("Extraction response could not be safely consumed") from error
