"""Runtime observations only use the local daemon and export allowlisted data."""

import hashlib
import json
import subprocess
import sys
from unittest.mock import Mock

import pytest

from scripts import observe_uat_runtime as runtime


def test_observation_redacts_command_failures_and_never_grants_acceptance(monkeypatch):
    def command(argv, **kwargs):
        if argv[0] == "git":
            return b"a" * 40
        raise subprocess.CalledProcessError(1, argv, output="private-secret", stderr="private-secret")

    monkeypatch.setattr(runtime, "command", command)
    monkeypatch.setattr(runtime, "docker_environment", lambda: {"DOCKER_HOST": "unix:///private-socket"})
    monkeypatch.setattr(runtime, "local_route", lambda port, path: 200 if path in ("/", "/api/v1/health") else 401)
    result = runtime.observe(compare_code=True)
    assert "private-secret" not in json.dumps(result) and "private-socket" not in json.dumps(result)
    assert result["authenticated_workflows"] == "not_observed"
    assert result["legal_acceptance"] == "not_granted"
    assert result["posture"]["status"] == result["backend_source"]["status"] == "unavailable"
    assert all(row["result"] == "pass" for row in result["routes"])


@pytest.mark.parametrize("project,port", [("bad\nproject", 8081), ("project;cmd", 8081), ("x", True), ("x", 80), ("x", 65536)])
def test_invalid_target_never_launches_a_command(monkeypatch, project, port):
    command = Mock()
    monkeypatch.setattr(runtime, "command", command)
    with pytest.raises(ValueError):
        runtime.observe(project, port)
    command.assert_not_called()


def test_loopback_get_has_no_auth_and_does_not_follow_redirects(monkeypatch):
    connection = Mock()
    connection.getresponse.return_value.status = 302
    factory = Mock(return_value=connection)
    monkeypatch.setattr(runtime.http.client, "HTTPConnection", factory)
    assert runtime.local_route(8081, "/api/v1/health") == 302
    factory.assert_called_once_with("127.0.0.1", 8081, timeout=3)
    connection.request.assert_called_once_with("GET", "/api/v1/health")
    connection.getresponse.return_value.read.assert_not_called()
    connection.close.assert_called_once()


def test_scanner_raw_error_text_is_never_forwarded(monkeypatch):
    replies = iter([b"a" * 12, json.dumps({"status": "blocked", "issues": [
        {"code": "scanner_not_ready", "message": "private-secret"}]}).encode()])
    monkeypatch.setattr(runtime, "command", lambda *a, **k: next(replies))
    assert runtime.scanner_readiness("lawyer-assistant-v1", {}) == {"status": "blocked", "issue_codes": ["scanner_not_ready"]}


def test_output_budget_is_enforced_on_the_stream():
    with pytest.raises(ValueError, match="budget"):
        runtime.command([sys.executable, "-c", "import os; os.write(1, b'x' * 4096)"], limit=64)
    assert runtime.command([sys.executable, "-c", "import os; os.write(2, b'secret'); print('ok')"]) == b"ok\n"


def test_remote_docker_context_never_inspects_or_executes(monkeypatch):
    command = Mock(side_effect=[b"a" * 40, b"ssh://remote-owner@remote.invalid"])
    monkeypatch.setattr(runtime, "command", command)
    monkeypatch.setattr(runtime, "local_route", lambda *args: None)
    monkeypatch.setenv("DOCKER_CONTEXT", "elsewhere")
    monkeypatch.setenv("DOCKER_HOST", "unix:///must-not-override-context")
    observed = runtime.observe(compare_code=True)
    assert not observed["local_docker_socket"] and observed["scanner"]["status"] == "unavailable"
    assert observed["backend_source"]["status"] == "unavailable"
    assert command.call_count == 2
    assert command.call_args.args[0][-2:] == ["--", "elsewhere"]
    assert "remote.invalid" not in json.dumps(observed)


def test_local_docker_context_is_pinned_to_a_unix_socket(monkeypatch, tmp_path):
    # macOS has a short sockaddr_un limit, even for pytest's temporary paths.
    monkeypatch.setattr(runtime.Path, "is_socket", lambda path: path == tmp_path / "d.sock")
    endpoint = "unix://" + str(tmp_path / "d.sock")
    context = Mock(return_value=endpoint.encode())
    monkeypatch.setattr(runtime, "command", context)
    env = runtime.docker_environment({"DOCKER_CONTEXT": "desktop-linux", "DOCKER_HOST": "tcp://remote.invalid"})
    assert env == {"DOCKER_HOST": endpoint}
    assert context.call_args.kwargs["env"] == {}
    assert runtime.docker_environment({"DOCKER_HOST": endpoint}) == env
    assert runtime.docker_environment({"DOCKER_HOST": "tcp://remote.invalid"}) is None
    assert context.call_count == 1


def test_code_comparison_uses_commit_blobs_and_never_local_worktree_bytes(monkeypatch):
    commit, path = "a" * 40, "backend/app/example.py"
    pinned = b"checked-in code\n"
    expected = hashlib.sha256(pinned).hexdigest()

    def command(argv, **kwargs):
        if argv[0] == "git" and argv[3] == "ls-tree":
            assert argv[6] == commit
            return path.encode() + b"\n"
        if argv[0] == "git" and argv[3] == "cat-file":
            assert kwargs["stdin"] == f"{commit}:{path}\n".encode()
            return b"b" * 40 + f" blob {len(pinned)}\n".encode() + pinned + b"\n"
        if argv[:2] == ["docker", "ps"]:
            return b"c" * 12
        assert argv[:3] == ["docker", "exec", "-i"]
        assert json.loads(kwargs["stdin"]) == [path]
        return json.dumps({path: expected}).encode()

    monkeypatch.setattr(runtime, "command", command)
    assert runtime.code_identity("lawyer-assistant-v1", commit, {"DOCKER_HOST": "unix:///test"}) == {
        "status": "matches", "compared_files": 1, "matching_files": 1, "different_or_absent_files": [],
        "scope": "backend Python source blobs in the reported commit",
    }


def test_invalid_posture_fields_cannot_leak_raw_child_output(monkeypatch):
    monkeypatch.setattr(runtime, "command", lambda *a, **k: b'{"schema":"runtime-posture-v1","services":[{"secret":"synthetic"}]}')
    with pytest.raises(ValueError, match="Invalid runtime posture"):
        runtime.deployment_posture("lawyer-assistant-v1", {})
