"""Fail-closed, bounded INSTREAM transport to the isolated local malware scanner."""

import ipaddress
import re
import socket
import struct
import time
from datetime import UTC, datetime, timedelta

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024
ISSUE_MESSAGES = {
    "Invalid local scanner configuration": "Yerel zararlı yazılım tarayıcısı yapılandırılmalı.",
    "Scanner signatures are stale": "Tarayıcı imzaları eski; onaylı güncel imza paketini içe aktarın.",
    "Scanner signature date is in the future": "Tarayıcı imza tarihi doğrulanamadı; sistem saatini denetleyin.",
    "Scanner has no verifiable signature date": "Tarayıcı imza tarihi doğrulanamadı.",
    "Scanner has no verifiable signature version": "Tarayıcı imza sürümü doğrulanamadı.",
}
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
))


class ScannerUnavailable(Exception):
    """Mandatory scanning could not be completed; messages contain no endpoint details."""


class MalwareDetected(Exception):
    """Scanner rejected content, including encrypted or incompletely scanned content."""


def _validate(host, port, timeout_seconds, max_signature_age_days):
    try:
        if not isinstance(host, str) or host != host.strip():
            raise ValueError
        if host != "scanner":
            address = ipaddress.ip_address(host)
            if (not (address.is_loopback or any(address in network for network in PRIVATE_NETWORKS))
                    or address.is_link_local or address.is_unspecified or address.is_multicast
                    or getattr(address, "ipv4_mapped", None) is not None or "%" in host):
                raise ValueError
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not 0 < timeout_seconds <= 120):
            raise ValueError
        if type(max_signature_age_days) is not int or not 1 <= max_signature_age_days <= 14:
            raise ValueError
    except (ValueError, TypeError):
        raise ScannerUnavailable("Invalid local scanner configuration") from None


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ScannerUnavailable("Scanner exceeded its time budget")
    return remaining


def _send(connection, content, deadline):
    connection.settimeout(_remaining(deadline))
    connection.sendall(content)


def _read(connection, deadline):
    result = bytearray()
    while b"\0" not in result:
        connection.settimeout(_remaining(deadline))
        part = connection.recv(MAX_RESPONSE_BYTES + 1 - len(result))
        if not part:
            raise ScannerUnavailable("Scanner returned an incomplete response")
        result.extend(part)
        if len(result) > MAX_RESPONSE_BYTES:
            raise ScannerUnavailable("Scanner response exceeded its limit")
    _remaining(deadline)
    if result[-1:] != b"\0" or b"\0" in result[:-1]:
        raise ScannerUnavailable("Scanner returned an invalid response")
    return bytes(result[:-1])


def _command(host, port, command, deadline):
    with socket.create_connection((host, port), timeout=_remaining(deadline)) as connection:
        _send(connection, b"z" + command + b"\0", deadline)
        return _read(connection, deadline)


def _version(response, max_signature_age_days):
    # The scanner container fixes LC_ALL=C and TZ=UTC; do not guess other time zones.
    match = re.fullmatch(rb"ClamAV ([0-9]+\.[0-9]+\.[0-9]+)/([0-9]+)/([A-Za-z]{3} [A-Za-z]{3} [ 0-9][0-9] [0-9:]{8} [0-9]{4})", response)
    if not match or int(match[2]) <= 0:
        raise ScannerUnavailable("Scanner has no verifiable signature version")
    try:
        date = datetime.strptime(match[3].decode("ascii"), "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
    except ValueError:
        raise ScannerUnavailable("Scanner has no verifiable signature date") from None
    age = datetime.now(UTC) - date
    if age < timedelta(minutes=-5):
        raise ScannerUnavailable("Scanner signature date is in the future")
    if age > timedelta(days=max_signature_age_days):
        raise ScannerUnavailable("Scanner signatures are stale")
    return {"version": match[1].decode("ascii"), "signature_date": date.isoformat(),
            "signature_version": int(match[2])}


def _ready(host, port, deadline, max_signature_age_days):
    if _command(host, port, b"PING", deadline) != b"PONG":
        raise ScannerUnavailable("Scanner did not pass its health check")
    return _version(_command(host, port, b"VERSION", deadline), max_signature_age_days)


def probe_scanner(host, *, port=3310, timeout_seconds=3, max_signature_age_days=7):
    """Report only sanitized readiness data; never return a hostname or raw daemon response."""
    try:
        _validate(host, port, timeout_seconds, max_signature_age_days)
        details = _ready(host, port, time.monotonic() + timeout_seconds, max_signature_age_days)
        return {"status": "ready", "issues": [], **details}
    except ScannerUnavailable as error:
        return {"status": "blocked", "issues": [{
            "code": "scanner_not_ready", "message": ISSUE_MESSAGES.get(
                str(error), "Yerel tarayıcı güvenlik denetimini tamamlayamadı; yöneticinize başvurun."),
        }]}
    except OSError:
        return {"status": "unavailable", "issues": [{
            "code": "scanner_unavailable", "message": "Yerel zararlı yazılım tarayıcısına ulaşılamıyor.",
        }]}


def scan_document(content, host, *, port=3310, timeout_seconds=30,
                  max_bytes=MAX_DOCUMENT_BYTES, max_signature_age_days=7):
    """Admit only a complete clean verdict, with freshness checked before transmitting content."""
    _validate(host, port, timeout_seconds, max_signature_age_days)
    if (type(max_bytes) is not int or not 1 <= max_bytes <= MAX_DOCUMENT_BYTES
            or not isinstance(content, bytes) or not 1 <= len(content) <= max_bytes):
        raise ScannerUnavailable("Document exceeds the scanning admission limit")
    deadline = time.monotonic() + timeout_seconds
    try:
        _ready(host, port, deadline, max_signature_age_days)
        with socket.create_connection((host, port), timeout=_remaining(deadline)) as connection:
            _send(connection, b"zINSTREAM\0", deadline)
            for start in range(0, len(content), 65536):
                chunk = content[start:start + 65536]
                _send(connection, struct.pack("!I", len(chunk)) + chunk, deadline)
            _send(connection, struct.pack("!I", 0), deadline)
            verdict = _read(connection, deadline)
        if verdict == b"stream: OK":
            return
        if re.fullmatch(rb"stream: [A-Za-z0-9_.()-]+ FOUND", verdict):
            raise MalwareDetected("Document did not pass its security check")
        raise ScannerUnavailable("Scanner did not return a complete clean verdict")
    except OSError:
        raise ScannerUnavailable("Local malware scanner is unavailable") from None
