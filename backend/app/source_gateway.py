"""Closed public-source registry for disposable connected staging, never an API route."""

import argparse
import ctypes
import hashlib
import http.client
import io
import ipaddress
import json
import os
import queue
import socket
import ssl
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

MAX_BYTES = 1024 * 1024
MAX_WIRE_BYTES = MAX_BYTES + 64 * 1024
TOTAL_SECONDS = 20
IDLE_SECONDS = 5
LEGACY_REGISTRY_VERSION = "tbmm-enacted-2026-10-04-v1"
REGISTRY_VERSION = "tbmm-enacted-2026-10-11-v2"
HISTORICAL_LIMITATION = (
    "TBMM enacted text excludes subsequent amendments; this is not a current consolidated text."
)
ERROR_CATEGORIES = MappingProxyType({
    "Public DNS resolution timed out": "dns_timeout",
    "Public DNS resolution failed": "dns_failed",
    "Public DNS resolution contains an inadmissible address": "dns_denied",
    "Acquisition deadline exceeded": "deadline",
    "Registered source could not be safely acquired": "transport_or_http",
    "Output could not be published without replacement": "exclusive_publication",
    "Exclusive publication is unsupported on this platform": "publication_unsupported",
    "Output must be a new directory under an existing parent": "invalid_output",
    "Redirects and non-success responses are not admitted": "http_status",
    "Only registered HTML representations are admitted": "media_type",
    "Compressed representations are not admitted": "compression",
    "Ambiguous response headers": "headers",
    "Invalid response headers": "headers",
    "Ambiguous response framing": "framing",
    "Invalid or oversized response length": "content_length",
    "Empty or incomplete source representation": "incomplete_content",
    "Source exceeds the content byte budget": "content_budget",
    "Response exceeds the wire byte budget": "wire_budget",
})
WORKER_ERROR_CODES = frozenset(ERROR_CATEGORIES.values()) | {"admission_control", "filesystem"}


class AcquisitionError(ValueError):
    """Messages are fixed diagnostics, never source bodies, paths or response headers."""


@dataclass(frozen=True)
class RegisteredSource:
    title: str
    url: str
    domain: str


_LEGACY_REGISTRY = MappingProxyType({
    "tbmm-6101-enacted": RegisteredSource(
        "6101 sayılı Türk Borçlar Kanununun Yürürlüğü ve Uygulama Şekli Hakkında Kanun — kabul edilen metin",
        "https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y3/T1/KanunMetni/"
        "3c4eac23-5d02-49cd-9ef1-4bf8de05aee6.html",
        "contracts",
    ),
    "tbmm-6098-enacted": RegisteredSource(
        "6098 sayılı Türk Borçlar Kanunu — kabul edilen metin",
        "https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y2/T1/KanunMetni/"
        "a657b33d-109c-473d-9266-5aa48d603ab2.html",
        "contracts",
    ),
})

REGISTRY = MappingProxyType({
    **_LEGACY_REGISTRY,
    "tbmm-4857-enacted": RegisteredSource(
        "4857 sayılı İş Kanunu — kabul edilen metin",
        "https://cdn.tbmm.gov.tr/KKBSPublicFile/D22/Y1/T1/KanunMetni/"
        "359dee72-3cd1-4131-8597-48c58658e326.html",
        "employment",
    ),
    "tbmm-6103-enacted": RegisteredSource(
        "6103 sayılı Türk Ticaret Kanununun Yürürlüğü ve Uygulama Şekli Hakkında Kanun — kabul edilen metin",
        "https://cdn.tbmm.gov.tr/KKBSPublicFile/D23/Y2/T1/KanunMetni/"
        "7f9bad4f-097c-4097-960f-2ef0bb0ed482.html",
        "commercial",
    ),
})
# Retain exact historical membership and metadata; new acquisitions always use
# REGISTRY. Only offline preparation may resolve a declared earlier snapshot.
REGISTRY_SNAPSHOTS = MappingProxyType({
    LEGACY_REGISTRY_VERSION: _LEGACY_REGISTRY,
    REGISTRY_VERSION: REGISTRY,
})


def registered(source_id, *, registry_version=REGISTRY_VERSION):
    if type(registry_version) is not str or registry_version not in REGISTRY_SNAPSHOTS:
        raise AcquisitionError("Unknown registry version")
    snapshot = REGISTRY_SNAPSHOTS[registry_version]
    if type(source_id) is not str or source_id not in snapshot:
        raise AcquisitionError("Unknown registered source")
    return snapshot[source_id]


def validate_acquisition_metadata(content, manifest, *, required_registry_version=None):
    """Bind all provenance to its immutable snapshot, without authenticating it."""
    if not isinstance(manifest, dict) or not 0 < len(content) <= MAX_BYTES:
        raise AcquisitionError("Invalid registered acquisition")
    version, source_id = manifest.get("registry_version"), manifest.get("registry_id")
    source = registered(source_id, registry_version=version)
    if required_registry_version is not None and version != required_registry_version:
        raise AcquisitionError("Registry version does not match the acquisition worker")
    digest = hashlib.sha256(content).hexdigest()
    expected = {
        "schema_version": "registered-source-acquisition-v1", "registry_version": version,
        "registry_id": source_id, "title": source.title, "source_url": source.url,
        "source_version_id": f"{source_id}:sha256:{digest}", "domain": source.domain,
        "raw_sha256": digest, "byte_count": len(content), "raw_media_type": "text/html",
        "rights_status": "rights_pending", "review_status": "legal_review_pending",
        "publication_status": "quarantined", "content_status": "untrusted_unscanned",
        "extraction_status": "not_processed", "representation": "enacted_text", "current_consolidation": False,
        "limitations": [HISTORICAL_LIMITATION,
            "Public availability does not establish permitted use, source identity review or legal applicability.",
            "This acquisition is unscanned and unparsed; admission and legal review are separate steps."],
    }
    if (set(manifest) != set(expected) | {"started_at", "acquired_at"}
            or any(json.dumps(manifest[key], sort_keys=True) != json.dumps(value, sort_keys=True)
                   for key, value in expected.items())):
        raise AcquisitionError("Invalid registered acquisition")
    try:
        dates = [datetime.fromisoformat(manifest[key]) for key in ("started_at", "acquired_at")]
        if (any(date.tzinfo is None or date.utcoffset() is None for date in dates)
                or not dates[0] <= dates[1] <= datetime.now(timezone.utc)):
            raise ValueError
    except (ValueError, TypeError):
        raise AcquisitionError("Invalid acquisition dates") from None
    return manifest


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AcquisitionError("Acquisition deadline exceeded")
    return min(IDLE_SECONDS, remaining)


def _resolve(hostname, deadline):
    result = queue.Queue(maxsize=1)

    def resolve():
        try:
            result.put(socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM))
        except OSError:
            result.put(None)

    # getaddrinfo has no Python timeout. A daemon resolver cannot hold up this
    # one-shot worker after the bounded wait; it never receives private input.
    threading.Thread(target=resolve, daemon=True).start()
    try:
        addresses = result.get(timeout=_remaining(deadline))
    except queue.Empty:
        raise AcquisitionError("Public DNS resolution timed out") from None
    if not addresses:
        raise AcquisitionError("Public DNS resolution failed")
    for family, socktype, _protocol, _name, address in addresses:
        ip = ipaddress.ip_address(address[0])
        if (family not in (socket.AF_INET, socket.AF_INET6) or socktype != socket.SOCK_STREAM
                or address[1] != 443 or not ip.is_global or ip.is_multicast or ip.is_reserved
                or ip.is_loopback or ip.is_link_local or ip.is_unspecified
                or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None)):
            raise AcquisitionError("Public DNS resolution contains an inadmissible address")
    _remaining(deadline)
    return addresses[0]


class _DeadlineReader(io.RawIOBase):
    def __init__(self, stream, deadline):
        self.stream, self.deadline, self.received = stream, deadline, 0

    def readable(self):
        return True

    def readinto(self, buffer):
        # Apply the absolute deadline to every low-level read, including headers
        # and chunk framing; slow-drip headers cannot reset the total budget.
        self.stream.settimeout(_remaining(self.deadline))
        count = self.stream.recv_into(buffer)
        self.received += count
        if self.received > MAX_WIRE_BYTES:
            raise AcquisitionError("Response exceeds the wire byte budget")
        return count


class _ResponseSocket:
    def __init__(self, stream, deadline):
        self.stream, self.deadline = stream, deadline

    def makefile(self, mode):
        if mode != "rb":
            raise AcquisitionError("Unsupported response stream")
        return io.BufferedReader(_DeadlineReader(self.stream, self.deadline), buffer_size=8192)


def _header(response, name):
    values = response.headers.get_all(name, [])
    if len(values) > 1:
        raise AcquisitionError("Ambiguous response headers")
    value = values[0].strip() if values else None
    if value is not None and any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise AcquisitionError("Invalid response headers")
    return value


def _body(stream, deadline):
    with http.client.HTTPResponse(_ResponseSocket(stream, deadline)) as response:
        response.begin()
        if response.status != 200:
            raise AcquisitionError("Redirects and non-success responses are not admitted")
        media = _header(response, "Content-Type")
        if not media or media.split(";", 1)[0].strip().lower() != "text/html":
            raise AcquisitionError("Only registered HTML representations are admitted")
        encoding = _header(response, "Content-Encoding")
        if encoding is not None and encoding.lower() != "identity":
            raise AcquisitionError("Compressed representations are not admitted")
        length = _header(response, "Content-Length")
        transfer = _header(response, "Transfer-Encoding")
        if transfer is not None and (transfer.lower() != "chunked" or length is not None):
            raise AcquisitionError("Ambiguous response framing")
        if length is not None and (not length.isascii() or not length.isdigit() or int(length) > MAX_BYTES):
            raise AcquisitionError("Invalid or oversized response length")
        content = bytearray()
        while True:
            _remaining(deadline)
            chunk = response.read1(min(8192, MAX_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise AcquisitionError("Source exceeds the content byte budget")
        if not content or (length is not None and len(content) != int(length)):
            raise AcquisitionError("Empty or incomplete source representation")
        _remaining(deadline)
        return bytes(content)


def acquire(source_id, *, connected_staging=False):
    source = registered(source_id)
    if connected_staging is not True:
        raise AcquisitionError("Explicit connected staging opt-in is required")
    started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + TOTAL_SECONDS
    url = urlsplit(source.url)
    # Registry paths are code-reviewed literals, never supplied by the caller.
    try:
        family, _socktype, _protocol, _name, address = _resolve(url.hostname, deadline)
        with socket.socket(family, socket.SOCK_STREAM) as raw:
            raw.settimeout(_remaining(deadline))
            raw.connect(address)
            raw.settimeout(_remaining(deadline))
            with ssl.create_default_context().wrap_socket(raw, server_hostname=url.hostname) as stream:
                stream.settimeout(_remaining(deadline))
                wire = (f"GET {url.path} HTTP/1.1\r\nHost: {url.hostname}\r\n"
                        "User-Agent: LawyerAssistant-RegisteredStaging/0.1\r\n"
                        "Accept: text/html\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n")
                stream.sendall(wire.encode("ascii"))
                content = _body(stream, deadline)
    except AcquisitionError:
        raise
    except (OSError, ValueError, http.client.HTTPException, OverflowError):
        raise AcquisitionError("Registered source could not be safely acquired") from None
    digest = hashlib.sha256(content).hexdigest()
    return content, {
        "schema_version": "registered-source-acquisition-v1", "registry_version": REGISTRY_VERSION,
        "registry_id": source_id, "title": source.title, "source_url": source.url,
        "source_version_id": f"{source_id}:sha256:{digest}", "domain": source.domain,
        "started_at": started, "acquired_at": datetime.now(timezone.utc).isoformat(),
        "raw_sha256": digest, "byte_count": len(content), "raw_media_type": "text/html",
        "rights_status": "rights_pending", "review_status": "legal_review_pending",
        "publication_status": "quarantined", "content_status": "untrusted_unscanned",
        "extraction_status": "not_processed", "representation": "enacted_text",
        "current_consolidation": False, "limitations": [HISTORICAL_LIMITATION,
            "Public availability does not establish permitted use, source identity review or legal applicability.",
            "This acquisition is unscanned and unparsed; admission and legal review are separate steps."],
    }


def rename_new(source, destination):
    """Atomic exclusive directory publication; fail rather than replace a raced target."""
    library = ctypes.CDLL(None, use_errno=True)
    source, destination = os.fsencode(source), os.fsencode(destination)
    if sys.platform == "linux" and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, source, -100, destination, 1)  # AT_FDCWD, RENAME_NOREPLACE
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source, destination, 4)  # RENAME_EXCL
    else:
        raise AcquisitionError("Exclusive publication is unsupported on this platform")
    if result:
        raise AcquisitionError("Output could not be published without replacement")


def write_package(content, metadata, destination):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise AcquisitionError("Output must be a new directory under an existing parent")
    with tempfile.TemporaryDirectory(prefix=".public-acquisition-", dir=destination.parent) as temporary:
        staged = Path(temporary)
        (staged / "raw.html").write_bytes(content)
        (staged / "acquisition.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        for path in staged.iterdir():
            path.chmod(0o600)
        rename_new(staged, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("source_id", choices=tuple(REGISTRY))
    parser.add_argument("output", type=Path)
    parser.add_argument("--connected-staging", action="store_true", required=True)
    args = parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
            raise AcquisitionError("Output must be a new directory under an existing parent")
        content, metadata = acquire(args.source_id, connected_staging=args.connected_staging)
        write_package(content, metadata, args.output)
    except AcquisitionError as error:
        parser.exit(1, json.dumps({"error": ERROR_CATEGORIES.get(str(error), "admission_control")}) + "\n")
    except OSError:
        parser.exit(1, json.dumps({"error": "filesystem"}) + "\n")


if __name__ == "__main__":
    main()
