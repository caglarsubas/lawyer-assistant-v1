"""Synthetic HTTP/DNS fixtures only: these tests acquire no actual legal sources."""

import hashlib
import importlib.util
import itertools
import json
import socket
import subprocess
import time
from pathlib import Path

import pytest

from app import source_gateway as gateway

SOURCE = "tbmm-6101-enacted"
BODY = b"<html><p>SYNTHETIC TEST CONTENT, NOT A LEGAL SOURCE.</p></html>"


def addresses(*ips):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            for ip in ips]


class FakeSocket:
    def __init__(self, wire=b"", fragment=8192):
        self.wire, self.fragment, self.sent, self.connected = wire, fragment, b"", None
        self.timeouts, self.closed = [], False

    def settimeout(self, seconds):
        self.timeouts.append(seconds)

    def connect(self, address):
        self.connected = address

    def sendall(self, content):
        self.sent += content

    def recv_into(self, target):
        size = min(len(target), self.fragment, len(self.wire))
        target[:size], self.wire = self.wire[:size], self.wire[size:]
        return size

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    def install(*, status=200, headers=None, body=BODY, fragment=8192):
        if headers is None:
            headers = [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))]
        wire = (f"HTTP/1.1 {status} Fixture\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers)
                + "\r\n").encode("latin-1") + body
        raw, tls = FakeSocket(), FakeSocket(wire, fragment)
        observation = {"raw": raw, "tls": tls, "dns": [], "sni": []}

        def resolve(*args, **kwargs):
            observation["dns"].append((args, kwargs))
            return addresses("9.9.9.9", "8.8.8.8")

        class Context:
            def wrap_socket(self, stream, *, server_hostname):
                assert stream is raw
                observation["sni"].append(server_hostname)
                return tls

        monkeypatch.setattr(gateway.socket, "getaddrinfo", resolve)
        monkeypatch.setattr(gateway.socket, "socket", lambda *args: raw)
        monkeypatch.setattr(gateway.ssl, "create_default_context", Context)
        return observation

    return install


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[2] / "scripts/acquire_public_source.py"
    spec = importlib.util.spec_from_file_location("source_acquisition_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_is_closed_and_immutable():
    assert set(gateway.REGISTRY) == {"tbmm-6101-enacted", "tbmm-6098-enacted",
                                     "tbmm-4857-enacted", "tbmm-6103-enacted"}
    assert gateway.REGISTRY[SOURCE].url.endswith("3c4eac23-5d02-49cd-9ef1-4bf8de05aee6.html")
    with pytest.raises(TypeError):
        gateway.REGISTRY["caller"] = gateway.REGISTRY[SOURCE]
    with pytest.raises(AttributeError):
        gateway.REGISTRY[SOURCE].url = "https://caller.invalid"


def test_historical_registry_cannot_acquire_later_members_or_be_mutated():
    old = gateway.REGISTRY_SNAPSHOTS[gateway.LEGACY_REGISTRY_VERSION]
    assert set(old) == {"tbmm-6101-enacted", "tbmm-6098-enacted"}
    for source_id in old:
        assert gateway.registered(source_id, registry_version=gateway.LEGACY_REGISTRY_VERSION) == old[source_id]
        assert gateway.REGISTRY[source_id] == old[source_id]
    for source_id in ("tbmm-4857-enacted", "tbmm-6103-enacted"):
        with pytest.raises(gateway.AcquisitionError, match="Unknown registered source"):
            gateway.registered(source_id, registry_version=gateway.LEGACY_REGISTRY_VERSION)
    with pytest.raises(TypeError):
        old["tbmm-4857-enacted"] = gateway.REGISTRY["tbmm-4857-enacted"]
    with pytest.raises(TypeError):
        gateway.REGISTRY_SNAPSHOTS["caller"] = old


@pytest.mark.parametrize("source_id,domain,path", [
    ("tbmm-6101-enacted", "contracts", "D23/Y3/T1/KanunMetni/3c4eac23-5d02-49cd-9ef1-4bf8de05aee6.html"),
    ("tbmm-6098-enacted", "contracts", "D23/Y2/T1/KanunMetni/a657b33d-109c-473d-9266-5aa48d603ab2.html"),
    ("tbmm-4857-enacted", "employment", "D22/Y1/T1/KanunMetni/359dee72-3cd1-4131-8597-48c58658e326.html"),
    ("tbmm-6103-enacted", "commercial", "D23/Y2/T1/KanunMetni/7f9bad4f-097c-4097-960f-2ef0bb0ed482.html"),
])
def test_domain_and_exact_destination_are_bound_to_current_registry(transport, source_id, domain, path):
    observed = transport()
    raw, manifest = gateway.acquire(source_id, connected_staging=True)
    assert observed["tls"].sent.startswith(f"GET /KKBSPublicFile/{path} HTTP/1.1\r\n".encode())
    assert observed["sni"] == ["cdn.tbmm.gov.tr"]
    assert manifest["domain"] == domain
    assert manifest["registry_version"] == gateway.REGISTRY_VERSION
    assert gateway.validate_acquisition_metadata(raw, manifest) == manifest


@pytest.mark.parametrize("identifier", ["unknown", "TBMM-6101-enacted", SOURCE + "?secret=1",
                                       SOURCE + "\n", gateway.REGISTRY[SOURCE].url, None])
def test_caller_cannot_supply_or_extend_destinations(monkeypatch, identifier):
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *a, **kw: pytest.fail("Unexpected DNS"))
    with pytest.raises(gateway.AcquisitionError, match="Unknown registered source"):
        gateway.acquire(identifier, connected_staging=True)


@pytest.mark.parametrize("opt_in", [False, None, "true", 1])
def test_connected_opt_in_is_required_before_network(monkeypatch, opt_in):
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *a, **kw: pytest.fail("Unexpected DNS"))
    with pytest.raises(gateway.AcquisitionError, match="opt-in"):
        gateway.acquire(SOURCE, connected_staging=opt_in)


def test_exact_registered_get_pins_one_ip_and_tls_hostname(transport):
    result = transport(fragment=7)
    content, metadata = gateway.acquire(SOURCE, connected_staging=True)
    assert content == BODY
    assert len(result["dns"]) == 1
    assert result["raw"].connected == ("9.9.9.9", 443)
    assert result["sni"] == ["cdn.tbmm.gov.tr"]
    wire = result["tls"].sent.decode("ascii")
    assert wire.startswith("GET /KKBSPublicFile/D23/Y3/T1/KanunMetni/"
                           "3c4eac23-5d02-49cd-9ef1-4bf8de05aee6.html HTTP/1.1\r\n")
    assert "Host: cdn.tbmm.gov.tr\r\n" in wire and "Accept-Encoding: identity\r\n" in wire
    assert "?" not in wire and "Authorization:" not in wire and "Cookie:" not in wire
    assert metadata["raw_sha256"] == hashlib.sha256(BODY).hexdigest()
    assert metadata["source_version_id"] == SOURCE + ":sha256:" + metadata["raw_sha256"]
    assert metadata["rights_status"] == "rights_pending"
    assert metadata["review_status"] == "legal_review_pending"
    assert metadata["current_consolidation"] is False
    assert metadata["content_status"] == "untrusted_unscanned"
    assert metadata["extraction_status"] == "not_processed"
    assert gateway.HISTORICAL_LIMITATION in metadata["limitations"]
    assert result["raw"].closed and result["tls"].closed


@pytest.mark.parametrize("ips", [[], ["127.0.0.1"], ["10.1.2.3"], ["169.254.169.254"], ["::1"],
                                ["9.9.9.9", "192.168.0.1"], ["224.0.0.1"], ["0.0.0.0"],
                                ["::ffff:9.9.9.9"], ["2001:db8::1"]])
def test_every_dns_address_must_be_global_before_socket_creation(monkeypatch, ips):
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *a, **kw: addresses(*ips))
    monkeypatch.setattr(gateway.socket, "socket", lambda *a: pytest.fail("Unexpected connection"))
    with pytest.raises(gateway.AcquisitionError, match="DNS"):
        gateway.acquire(SOURCE, connected_staging=True)


def test_dns_wait_is_bounded(monkeypatch):
    def delayed(*args, **kwargs):
        time.sleep(0.03)
        return addresses("9.9.9.9")
    monkeypatch.setattr(gateway.socket, "getaddrinfo", delayed)
    monkeypatch.setattr(gateway, "_remaining", lambda deadline: 0.001)
    with pytest.raises(gateway.AcquisitionError, match="DNS resolution timed out"):
        gateway._resolve("cdn.tbmm.gov.tr", time.monotonic() + 1)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 403, 404, 500])
def test_redirects_and_errors_never_return_response_content(transport, status):
    transport(status=status, headers=[("Content-Type", "text/html"), ("Location", "https://private.invalid")],
              body=b"DO_NOT_REFLECT_SECRET_DIAGNOSTIC")
    with pytest.raises(gateway.AcquisitionError) as captured:
        gateway.acquire(SOURCE, connected_staging=True)
    assert "DO_NOT_REFLECT" not in str(captured.value) and "private.invalid" not in str(captured.value)


@pytest.mark.parametrize("headers", [
    [], [("Content-Type", "text/plain")], [("Content-Type", "application/pdf")],
    [("Content-Type", "text/html"), ("Content-Encoding", "gzip")],
    [("Content-Type", "text/html"), ("Content-Encoding", "br")],
    [("Content-Type", "text/html"), ("Content-Length", "1"), ("Content-Length", "1")],
    [("Content-Type", "text/html"), ("Content-Length", "-1")],
    [("Content-Type", "text/html"), ("Content-Length", str(gateway.MAX_BYTES + 1))],
    [("Content-Type", "text/html"), ("Content-Length", "1"), ("Transfer-Encoding", "chunked")],
    [("Content-Type", "text/html"), ("Transfer-Encoding", "gzip")],
])
def test_media_compression_and_framing_are_fail_closed(transport, headers):
    transport(headers=headers)
    with pytest.raises(gateway.AcquisitionError):
        gateway.acquire(SOURCE, connected_staging=True)


def test_undeclared_oversize_and_declared_truncation_are_rejected(transport):
    transport(headers=[("Content-Type", "text/html")], body=b"x" * (gateway.MAX_BYTES + 1))
    with pytest.raises(gateway.AcquisitionError, match="byte budget"):
        gateway.acquire(SOURCE, connected_staging=True)
    transport(headers=[("Content-Type", "text/html"), ("Content-Length", "100")], body=b"short")
    with pytest.raises(gateway.AcquisitionError, match="incomplete"):
        gateway.acquire(SOURCE, connected_staging=True)


def test_bounded_chunked_html_preserves_bytes_but_incomplete_chunk_is_rejected(transport):
    headers = [("Content-Type", "text/html"), ("Transfer-Encoding", "chunked")]
    transport(headers=headers, body=f"{len(BODY):x}\r\n".encode() + BODY + b"\r\n0\r\n\r\n", fragment=7)
    assert gateway.acquire(SOURCE, connected_staging=True)[0] == BODY
    transport(headers=headers, body=b"9\r\nx")
    with pytest.raises(gateway.AcquisitionError, match="safely acquired"):
        gateway.acquire(SOURCE, connected_staging=True)


def test_deadline_covers_slow_drip_headers(transport, monkeypatch):
    transport(fragment=1)
    ticks = itertools.count()
    monkeypatch.setattr(gateway.time, "monotonic", lambda: next(ticks))
    with pytest.raises(gateway.AcquisitionError, match="deadline"):
        gateway.acquire(SOURCE, connected_staging=True)


def test_tls_failures_are_sanitized(transport, monkeypatch):
    transport()
    class Context:
        def wrap_socket(self, *a, **kw):
            raise OSError("DO_NOT_REFLECT_TLS_DIAGNOSTIC")
    monkeypatch.setattr(gateway.ssl, "create_default_context", Context)
    with pytest.raises(gateway.AcquisitionError, match="safely acquired") as captured:
        gateway.acquire(SOURCE, connected_staging=True)
    assert "DO_NOT_REFLECT" not in str(captured.value)


def test_atomic_package_keeps_raw_bytes_and_pending_metadata(transport, tmp_path):
    transport()
    content, metadata = gateway.acquire(SOURCE, connected_staging=True)
    output = tmp_path / "new-release"
    gateway.write_package(content, metadata, output)
    assert {p.name for p in output.iterdir()} == {"raw.html", "acquisition.json"}
    assert (output / "raw.html").read_bytes() == BODY
    assert json.loads((output / "acquisition.json").read_text()) == metadata
    with pytest.raises(gateway.AcquisitionError, match="new directory"):
        gateway.write_package(b"replacement", {}, output)
    assert (output / "raw.html").read_bytes() == BODY


def test_exclusive_rename_never_overwrites_a_raced_empty_directory(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    (source / "raw.html").write_bytes(BODY)
    destination.mkdir()
    with pytest.raises(gateway.AcquisitionError, match="without replacement"):
        gateway.rename_new(source, destination)
    assert list(destination.iterdir()) == [] and (source / "raw.html").exists()


def test_failed_publication_leaves_no_partial_destination(transport, tmp_path, monkeypatch):
    transport()
    content, metadata = gateway.acquire(SOURCE, connected_staging=True)
    monkeypatch.setattr(gateway, "rename_new", lambda *a: (_ for _ in ()).throw(gateway.AcquisitionError("blocked")))
    with pytest.raises(gateway.AcquisitionError):
        gateway.write_package(content, metadata, tmp_path / "target")
    assert list(tmp_path.iterdir()) == []


def test_cli_container_receives_only_new_staging_directory_and_fixed_inputs(cli, tmp_path):
    command = cli._command(SOURCE, tmp_path, "fixture-worker", "sha256:" + "a" * 64)
    assert command.count("--mount") == 1
    assert command[command.index("--mount") + 1] == f"type=bind,src={tmp_path},dst=/staging"
    assert command[command.index("--network") + 1] == "bridge"
    assert command[command.index("--pull") + 1] == "never"
    assert command[command.index("--entrypoint") + 1] == "/usr/bin/env" and "-i" in command
    assert "--read-only" in command and "ALL" in command and "no-new-privileges:true" in command
    assert "--env-file" not in command and "--privileged" not in command
    assert all(command[index + 1].endswith("=") for index, arg in enumerate(command) if arg == "--env")
    assert command[-3:] == [SOURCE, "/staging/acquired", "--connected-staging"]


def test_cli_publishes_only_after_hash_validation_and_cleanup(cli, transport, tmp_path, monkeypatch):
    transport()
    content, metadata = gateway.acquire(SOURCE, connected_staging=True)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return "sha256:" + "a" * 64
        if command[1] == "run":
            mount = command[command.index("--mount") + 1]
            staging = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
            gateway.write_package(content, metadata, staging / "acquired")
        return ""
    monkeypatch.setattr(cli, "_run", run)
    result = cli.acquire_in_container(SOURCE, tmp_path / "published", connected_staging=True)
    assert result["raw_sha256"] == hashlib.sha256(BODY).hexdigest()
    assert calls[-1][1:3] == ["rm", "--force"]
    assert (tmp_path / "published/raw.html").read_bytes() == BODY


def test_cli_rejects_existing_output_before_docker(cli, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_run", lambda *a, **kw: pytest.fail("Unexpected Docker call"))
    with pytest.raises(gateway.AcquisitionError, match="new directory"):
        cli.acquire_in_container(SOURCE, tmp_path, connected_staging=True)


def test_cli_does_not_publish_tampered_content(cli, transport, tmp_path):
    transport()
    content, metadata = gateway.acquire(SOURCE, connected_staging=True)
    gateway.write_package(content, metadata, tmp_path / "staged")
    (tmp_path / "staged/raw.html").write_bytes(b"tampered")
    with pytest.raises(gateway.AcquisitionError, match="provenance"):
        cli._validate_package(SOURCE, tmp_path / "staged")


@pytest.mark.parametrize("field,value", [
    ("registry_version", gateway.LEGACY_REGISTRY_VERSION), ("domain", "employment"),
    ("title", "Misidentified source"), ("byte_count", True),
    ("current_consolidation", 0), ("started_at", "2999-01-01T00:00:00+00:00"),
    ("extra", "unexpected"),
])
def test_host_rejects_stale_worker_or_mislabeled_provenance(cli, transport, tmp_path, field, value):
    transport()
    raw, manifest = gateway.acquire(SOURCE, connected_staging=True)
    manifest[field] = value
    gateway.write_package(raw, manifest, tmp_path / "staged")
    with pytest.raises(gateway.AcquisitionError, match="provenance"):
        cli._validate_package(SOURCE, tmp_path / "staged")


def test_acquisition_uses_separate_fixed_image_and_stops_old_worker_after_cleanup(cli, transport, tmp_path,
                                                                              monkeypatch):
    transport()
    raw, manifest = gateway.acquire(SOURCE, connected_staging=True)
    manifest["registry_version"] = gateway.LEGACY_REGISTRY_VERSION
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            assert command[-1] == "lawyer-assistant-public-acquisition:0.1.0"
            return "sha256:" + "a" * 64
        if command[1] == "run":
            mount = command[command.index("--mount") + 1]
            staging = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
            gateway.write_package(raw, manifest, staging / "acquired")
        return ""

    monkeypatch.setattr(cli, "_run", run)
    with pytest.raises(gateway.AcquisitionError, match="provenance"):
        cli.acquire_in_container(SOURCE, tmp_path / "target", connected_staging=True)
    assert calls[-1][1:3] == ["rm", "--force"]
    assert list(tmp_path.iterdir()) == []


def test_cli_cleans_up_after_worker_failure_without_publishing(cli, tmp_path, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return "sha256:" + "a" * 64
        if command[1] == "run":
            raise gateway.AcquisitionError("Disposable worker timed out")
        return ""
    monkeypatch.setattr(cli, "_run", run)
    with pytest.raises(gateway.AcquisitionError, match="timed out"):
        cli.acquire_in_container(SOURCE, tmp_path / "target", connected_staging=True)
    assert calls[-1][1:3] == ["rm", "--force"]
    assert list(tmp_path.iterdir()) == []


def test_cleanup_confirms_auto_removed_container_absence(cli, monkeypatch):
    def run(command, **kwargs):
        if command[1] == "rm":
            raise gateway.AcquisitionError("Already absent or Docker failure")
        assert command[1:3] == ["container", "ls"]
        return ""
    monkeypatch.setattr(cli, "_run", run)
    cli._cleanup("fixture-worker")
    monkeypatch.setattr(cli, "_run", lambda *a, **kw: (_ for _ in ()).throw(gateway.AcquisitionError("failed")))
    with pytest.raises(gateway.AcquisitionError):
        cli._cleanup("fixture-worker")


@pytest.mark.parametrize("option", ["--url", "--header", "--proxy", "--image", "--credentials",
                                    "--registry-version", "--domain"])
def test_cli_rejects_custom_egress_inputs(cli, tmp_path, monkeypatch, option):
    monkeypatch.setattr(cli.sys, "argv", ["acquire_public_source.py", SOURCE, str(tmp_path / "new"),
                                       "--connected-staging", option, "untrusted"])
    monkeypatch.setattr(cli, "_run", lambda *a, **kw: pytest.fail("Unexpected Docker call"))
    with pytest.raises(SystemExit) as captured:
        cli.main()
    assert captured.value.code == 2


def test_worker_reports_only_fixed_error_categories(transport, tmp_path, monkeypatch, capsys):
    transport(status=503, body=b"DO_NOT_REFLECT_RESPONSE")
    monkeypatch.setattr(gateway.sys, "argv", ["source_gateway", SOURCE, str(tmp_path / "new"),
                                           "--connected-staging"])
    with pytest.raises(SystemExit):
        gateway.main()
    assert json.loads(capsys.readouterr().err) == {"error": "http_status"}


@pytest.mark.parametrize("stderr,expected", [
    ('{"error":"dns_timeout"}', "Registered source acquisition failed: dns_timeout"),
    ('{"error":"DO_NOT_REFLECT_RESPONSE"}', "Disposable staging process was rejected"),
    ("DO_NOT_REFLECT_RESPONSE", "Disposable staging process was rejected"),
])
def test_cli_accepts_only_allowlisted_diagnostic_codes(cli, monkeypatch, stderr, expected):
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", stderr))
    with pytest.raises(gateway.AcquisitionError) as captured:
        cli._run(["docker", "run"])
    assert str(captured.value) == expected


def test_cleanup_waits_for_in_progress_auto_removal(cli, monkeypatch):
    listings = iter(["container-still-removing", ""])
    def run(command, **kwargs):
        if command[1] == "rm":
            raise gateway.AcquisitionError("Removal in progress")
        return next(listings)
    monkeypatch.setattr(cli, "_run", run)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    cli._cleanup("fixture-worker")
