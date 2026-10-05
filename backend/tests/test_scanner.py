"""Synthetic ClamAV protocol checks; never connect to a live endpoint."""

from datetime import UTC, datetime, timedelta

import pytest

from app import scanner
from app.scanner import MalwareDetected, ScannerUnavailable, probe_scanner, scan_document


def version(age=0):
    date = datetime.now(UTC) - timedelta(days=age)
    return ("ClamAV 1.4.6/28000/" + date.strftime("%a %b %d %H:%M:%S %Y")).encode() + b"\0"


def responses(monkeypatch, frames):
    seen = []
    queue = iter(frames)

    class Connection:
        def __init__(self):
            response = next(queue)
            self.parts = iter(response if isinstance(response, list) else [response])
            self.sent = []
            seen.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, timeout):
            assert 0 < timeout <= 120

        def sendall(self, content):
            self.sent.append(content)

        def recv(self, limit):
            return next(self.parts, b"")

    monkeypatch.setattr(scanner.socket, "create_connection", lambda *args, **kwargs: Connection())
    return seen


def test_fragmented_verdict_and_framing(monkeypatch):
    seen = responses(monkeypatch, [b"PONG\0", version(), [b"stream:", b" OK", b"\0"]])
    scan_document(b"synthetic", "scanner")
    assert seen[0].sent == [b"zPING\0"]
    assert seen[1].sent == [b"zVERSION\0"]
    assert seen[2].sent == [b"zINSTREAM\0", b"\0\0\0\x09synthetic", b"\0\0\0\0"]


@pytest.mark.parametrize("reply", [b"stream: OK", b"", b"stream: OK\n\0", b"stream: OK\0bad",
                                 b"stream: OK\0\0", b"stream: ERROR\0", b"x" * 1025,
                                 b"INSTREAM size limit exceeded. ERROR\0"])
def test_nonclean_incomplete_and_oversized_replies_fail_closed(monkeypatch, reply):
    responses(monkeypatch, [b"PONG\0", version(), reply])
    with pytest.raises(ScannerUnavailable):
        scan_document(b"synthetic", "scanner")


@pytest.mark.parametrize("reply", [b"stream: Win.Test-1 FOUND\0",
                                 b"stream: Heuristics.Limits.Exceeded FOUND\0",
                                 b"stream: Heuristics.Encrypted.PDF FOUND\0"])
def test_malware_and_incomplete_content_are_rejected(monkeypatch, reply):
    responses(monkeypatch, [b"PONG\0", version(), reply])
    with pytest.raises(MalwareDetected):
        scan_document(b"synthetic", "scanner")


@pytest.mark.parametrize("reply", [version(8), version(-1), b"ClamAV 1.4.6\0",
                                 b"ClamAV 1.4.6/0/Sat Oct  3 12:00:00 2026\0",
                                 b"ClamAV 1.4.6/9/Sat Xxx  3 12:00:00 2026\0"])
def test_bad_signatures_prevent_content_transmission(monkeypatch, reply):
    seen = responses(monkeypatch, [b"PONG\0", reply])
    with pytest.raises(ScannerUnavailable):
        scan_document(b"synthetic", "scanner")
    assert len(seen) == 2


def test_failed_ping_prevents_content_transmission(monkeypatch):
    seen = responses(monkeypatch, [b"wrong\0"])
    with pytest.raises(ScannerUnavailable):
        scan_document(b"synthetic", "scanner")
    assert len(seen) == 1


@pytest.mark.parametrize("host", ["", "example.com", "169.254.169.254", "0.0.0.0", "8.8.8.8",
                                "scanner ", "127.0.0.1\0", "::ffff:127.0.0.1"])
def test_external_or_ambiguous_hosts_are_forbidden(monkeypatch, host):
    responses(monkeypatch, [])
    with pytest.raises(ScannerUnavailable):
        scan_document(b"synthetic", host)


@pytest.mark.parametrize("kwargs", [{"timeout_seconds": 0}, {"timeout_seconds": float("nan")},
                                  {"timeout_seconds": 121}, {"port": 0}, {"port": True},
                                  {"max_signature_age_days": 0}, {"max_signature_age_days": 15},
                                  {"max_bytes": 21 * 1024 * 1024}])
def test_invalid_limits_never_connect(monkeypatch, kwargs):
    responses(monkeypatch, [])
    with pytest.raises(ScannerUnavailable):
        scan_document(b"synthetic", "scanner", **kwargs)


@pytest.mark.parametrize("content", [b"", "synthetic", b"123456"])
def test_size_admission_before_connection(monkeypatch, content):
    responses(monkeypatch, [])
    with pytest.raises(ScannerUnavailable):
        scan_document(content, "scanner", max_bytes=5)


def test_no_raw_network_errors_escape(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("private scanner location /secret")

    monkeypatch.setattr(scanner.socket, "create_connection", fail)
    with pytest.raises(ScannerUnavailable, match="Local malware scanner is unavailable"):
        scan_document(b"synthetic", "scanner")
    assert "secret" not in str(probe_scanner("scanner"))


def test_probe_has_safe_freshness_metadata(monkeypatch):
    responses(monkeypatch, [b"PONG\0", version()])
    result = probe_scanner("scanner")
    assert result["status"] == "ready" and result["issues"] == []
    assert result["version"] == "1.4.6" and result["signature_version"] == 28000
    responses(monkeypatch, [b"PONG\0", version(8)])
    assert probe_scanner("scanner")["status"] == "blocked"


def test_total_deadline_not_reset_by_partial_reads(monkeypatch):
    responses(monkeypatch, [[b"P", b"ONG", b"\0"]])
    ticks = iter([0, 1, 2, 3, 31])
    monkeypatch.setattr(scanner.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ScannerUnavailable, match="time budget"):
        scan_document(b"synthetic", "scanner")
