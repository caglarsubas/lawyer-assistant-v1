"""Trusted source-set publication review using isolated TEST-ONLY approvals."""

import copy
import importlib.util
import json
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest
from test_release_authorization import signed
from test_release_set_authorization import authorized_set as authorized_set_fixture
from test_release_set_authorization import change_second, guard_set
from test_release_set_authorization import source as source_fixture
from test_release_set_authorization import workspace as workspace_fixture
from test_release_snapshot import counts, operator_id

from app import config
from app.graph_release import _load_serving

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("set_publication_cli_tests", ROOT / "scripts/review_set_publication.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)
workspace = workspace_fixture
source = source_fixture
authorized_set = authorized_set_fixture


def packet(fixture):
    return fixture["auth_path"].parent / "packet"


def candidate_options(fixture, output):
    return dict(operator_id=operator_id(fixture["app"]), public_reviewer=fixture["info"]["review"]["reviewer"],
                reviewed_at=fixture["info"]["review"]["reviewed_at"], output=output)


def request_options(fixture, output):
    body = fixture["body"]
    return dict(packet=packet(fixture), operator_id=operator_id(fixture["app"]),
                trusted_review_key=fixture["public_key"], reviewer=body["reviewer"], approved_at=body["approved_at"],
                expires_at=body["expires_at"], source_permissions=copy.deepcopy(body["source_permissions"]), output=output)


def accept_options(fixture, envelope=None):
    return dict(packet=packet(fixture), operator_id=operator_id(fixture["app"]),
                trusted_review_key=fixture["public_key"], authorization=envelope or fixture["auth_path"])


def fresh_destination(fixture):
    """Move only this test's prior private approval aside; retain the policy epoch."""
    moved = fixture["root"].with_name("TEST-ONLY-input-approvals")
    fixture["root"].rename(moved)
    fixture["root"].mkdir(mode=0o700)
    fixture["auth_path"] = moved / fixture["info"]["release_id"] / "authorization.json"
    return fixture


def assert_failure(capsys):
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"error": "source_set_publication_review_failed", "publication_performed": False}


def test_real_candidate_request_external_acceptance_and_guarded_install(authorized_set, tmp_path):
    fixture = fresh_destination(authorized_set)
    settings = fixture["app"].state.settings
    before = counts(fixture["app"])
    prepared = fixture["info"]["bundle_path"].parent
    preview = tmp_path / "private-signing-inputs"
    result = cli.candidate(settings, packet(fixture), **candidate_options(fixture, preview))
    assert result == {"candidate_created": True, "signed": False, "publication_eligible": False}
    for family in ("structure", "jurisprudence"):
        assert (preview / "inputs" / f"{family}.ttl").read_bytes() == (
            fixture["info"]["bundle_path"] / "inputs" / f"{family}.ttl").read_bytes()
    assert not any(b"PRIVATE TEST-ONLY" in path.read_bytes() for path in preview.rglob("*") if path.is_file())
    output = tmp_path / "private-authorization-request"
    result = cli.request(settings, prepared, **request_options(fixture, output))
    assert result == {"authorization_requested": True, "signed": False, "publication_eligible": False}
    body = json.loads((output / "authorization-body.json").read_bytes())
    assert body["source_permissions"] == fixture["body"]["source_permissions"]
    assert len(body["source_binding"]["sources"]) == 2
    assert "signature" not in body
    envelope = tmp_path / "EXTERNALLY-SIGNED-TEST-ONLY.json"
    signed(envelope, body, fixture["key"], fixture["tools"])
    result = cli.accept(settings, prepared, **accept_options(fixture, envelope))
    assert result == {"authorization_accepted": True, "release_id": fixture["info"]["release_id"],
                      "publication_performed": False}
    destination = fixture["root"] / result["release_id"]
    assert all(stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
               for path in (destination, *destination.rglob("*")))
    assert counts(fixture["app"]) == before
    assert not list(fixture["root"].glob(".source-set-authorization-*"))
    serving = _load_serving()
    volume = tmp_path / "public-volume"
    def authorize(info, action):
        return guard_set(fixture, info=info, action=action)
    serving.install(volume, prepared, fixture["public_key"], authorization_guard=authorize)
    serving.activate(volume, result["release_id"], fixture["public_key"], expected_current=None,
                     authorization_guard=authorize)
    assert not any(b"PRIVATE TEST-ONLY" in path.read_bytes() for path in volume.rglob("*") if path.is_file())
    change_second(fixture, "rights")
    with pytest.raises(ValueError):
        serving.install(volume, prepared, fixture["public_key"], authorization_guard=authorize)


def test_same_release_acceptance_never_replaces_existing_private_approval(authorized_set):
    fixture = authorized_set
    before = {str(path.relative_to(fixture["root"])): path.read_bytes()
              for path in fixture["root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError):
        cli.accept(fixture["app"].state.settings, fixture["info"]["bundle_path"].parent, **accept_options(fixture))
    after = {str(path.relative_to(fixture["root"])): path.read_bytes()
             for path in fixture["root"].rglob("*") if path.is_file()}
    assert after == before
    assert not list(fixture["root"].glob(".source-set-authorization-*"))


@pytest.mark.parametrize("kind", ["bad_signature", "second_source_stale", "cross_source_audience_proof"])
def test_failed_acceptance_leaves_no_authorization_or_stage(authorized_set, tmp_path, kind):
    fixture = fresh_destination(authorized_set)
    body = copy.deepcopy(fixture["body"])
    if kind == "cross_source_audience_proof":
        body["source_permissions"][1]["evidence_sha256"] = body["source_permissions"][0]["evidence_sha256"]
    envelope = tmp_path / "external-approval.json"
    signed(envelope, body, fixture["key"], fixture["tools"])
    if kind == "bad_signature":
        value = json.loads(envelope.read_bytes())
        value["signature"] = "AAAA"
        envelope.write_bytes(cli.io.canonical(value))
    elif kind == "second_source_stale":
        change_second(fixture, "rights")
    with pytest.raises(ValueError):
        cli.accept(fixture["app"].state.settings, fixture["info"]["bundle_path"].parent,
                   **accept_options(fixture, envelope))
    assert list(fixture["root"].iterdir()) == []


@pytest.mark.parametrize("operation", ["candidate", "request"])
def test_final_source_revalidation_failure_removes_only_new_output(authorized_set, tmp_path, monkeypatch, operation):
    fixture = authorized_set
    output = tmp_path / "discard-on-review-change"
    original = cli.current_packet

    @contextmanager
    def changed(*args, **kwargs):
        with original(*args, **kwargs) as current:
            yield current
            assert output.exists()
            change_second(fixture, "rights")

    monkeypatch.setattr(cli, "current_packet", changed)
    with pytest.raises(ValueError):
        if operation == "candidate":
            cli.candidate(fixture["app"].state.settings, packet(fixture), **candidate_options(fixture, output))
        else:
            cli.request(fixture["app"].state.settings, fixture["info"]["bundle_path"].parent,
                        **request_options(fixture, output))
    assert not output.exists()


def test_bad_per_source_permission_is_rejected_before_request_output(authorized_set, tmp_path):
    fixture = authorized_set
    output = tmp_path / "must-not-exist"
    options = request_options(fixture, output)
    options["source_permissions"][1]["evidence_sha256"] = options["source_permissions"][0]["evidence_sha256"]
    with pytest.raises(ValueError):
        cli.request(fixture["app"].state.settings, fixture["info"]["bundle_path"].parent, **options)
    assert not output.exists()


def test_accept_removes_owned_durable_output_when_post_write_integrity_fails(authorized_set, monkeypatch):
    fixture = fresh_destination(authorized_set)
    destination = fixture["root"] / fixture["info"]["release_id"]
    original = cli.io.atomic_packet

    def changed(output, files, **kwargs):
        result = original(output, files, **kwargs)
        if Path(output) == destination:
            path = destination / "authorization.json"
            path.write_bytes(path.read_bytes() + b"PRIVATE POST-WRITE CHANGE")
        return result

    monkeypatch.setattr(cli.io, "atomic_packet", changed)
    with pytest.raises(ValueError):
        cli.accept(fixture["app"].state.settings, fixture["info"]["bundle_path"].parent, **accept_options(fixture))
    assert list(fixture["root"].iterdir()) == []


def test_request_cli_strictly_reads_permission_file_and_emits_only_safe_receipt(authorized_set, tmp_path, monkeypatch, capsys):
    fixture = authorized_set
    permissions = tmp_path / "private-source-permissions.json"
    permissions.write_bytes(cli.io.canonical(fixture["body"]["source_permissions"]))
    output = tmp_path / "cli-request"
    options = request_options(fixture, output)
    options["source_permissions"] = permissions
    argv = ["request", str(fixture["info"]["bundle_path"].parent), *[part for name, value in options.items()
            for part in ("--" + name.replace("_", "-"), str(value))]]
    monkeypatch.setattr(config, "load_settings", lambda: fixture["app"].state.settings)
    assert cli.main(argv) == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert json.loads(captured.out) == {"authorization_requested": True, "publication_eligible": False, "signed": False}
    permissions.write_text('[{"source_id":"PRIVATE-A","source_id":"PRIVATE-B"}]')
    loaded = []
    monkeypatch.setattr(config, "load_settings", lambda: loaded.append(True))
    assert cli.main(argv) == 2
    assert not loaded
    assert_failure(capsys)


@pytest.mark.parametrize("args", [[], ["PRIVATE-ARGUMENT"], ["candidate", "private-packet"],
                                  ["request", "private-release"], ["accept", "private-release"]])
def test_bad_arguments_cannot_expose_private_inputs(args, capsys):
    assert cli.main(args) == 2
    assert_failure(capsys)
