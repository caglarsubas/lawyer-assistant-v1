"""Portable public preview, explicit compatible host, invented identities only."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import build_operator_preview as builder  # noqa: E402
import operator_preview_binding as binding  # noqa: E402
import operator_preview_manifest as manifest  # noqa: E402
from test_disposition_journal_reconciliation import protected  # noqa: E402
from test_operator_checksum_handoff import SOURCE, payload, prepared  # noqa: E402
from test_operator_checksum_handoff import f as f  # noqa: E402


def request(f, app, path="/api/v1/firm-admin/disposition-receipt-stage/preview", data=None):
    async def run():
        rows = [(k.decode(), v.decode()) for k, v in f.scope("reviewer")["headers"]]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://operator.invalid") as client:
            return await client.post(path, headers=rows + [("content-type", "application/json")],
                                     content=json.dumps({} if data is None else data))
    return asyncio.run(run())


def export(tmp_path):
    root = tmp_path / "public-preview"
    return root, builder.build(root)["manifest_sha256"]


def selected(f):
    adapter, target = prepared(f)
    p = adapter.service.reconciler.disposition.planner
    return binding.HostBinding(adapter=adapter, source_id=SOURCE, handoff_sha256=target.sha256,
        binding_sha256=target.binding_sha256, profile_id=p.authority.profile_id,
        preparer_id=p.preparer, reviewer_id=p.reviewer, origin=p.authority.app.state.settings.origins[0]), target


def load(root, pin, host_binding):
    return binding.bind_preview(root, pin, host_root=ROOT, binding=host_binding, require_readonly=False)


def test_export_is_deterministic_closed_and_contains_only_exact_public_preview_bytes(tmp_path):
    a, pin = export(tmp_path)
    b = tmp_path / "other"
    assert builder.build(b)["manifest_sha256"] == pin
    assert {p.name for p in a.iterdir()} == manifest.ASSETS | {manifest.MANIFEST}
    for name in manifest.ASSETS:
        assert (a / name).read_bytes() == (ROOT / "scripts" / name).read_bytes()
    with pytest.raises(FileExistsError):
        builder.build(a)
    value, _ = manifest.inspect_package(a, pin, require_readonly=False)
    assert set(value["host_sha256"]) == manifest.host_paths(ROOT)
    assert not any(".env" in n or "fixtures/" in n or "/tests/" in n for n in value["host_sha256"])


@pytest.mark.parametrize("fault", ["wrong_pin", "changed_code", "changed_html", "extra_file", "symlink",
                                  "hardlink", "permissions", "duplicate_json", "unknown_field", "not_readonly"])
def test_unapproved_or_mutable_exports_rejected_before_code_execution(tmp_path, fault):
    root, pin = export(tmp_path)
    path = root / "operator_inspection_preview.py"
    readonly = False
    if fault == "wrong_pin":
        pin = "0" * 64
    elif fault == "changed_code":
        path.write_text('raise AssertionError("must never execute")\n')
    elif fault == "changed_html":
        (root / "operator_inspection_preview.html").write_text("changed")
    elif fault == "extra_file":
        (root / ".env").write_text("invented-only")
    elif fault == "symlink":
        path.unlink()
        path.symlink_to(ROOT / "scripts/operator_inspection_preview.py")
    elif fault == "hardlink":
        os.link(path, tmp_path / "second-link")
    elif fault == "permissions":
        path.chmod(0o666)
    elif fault in {"duplicate_json", "unknown_field"}:
        p = root / manifest.MANIFEST
        raw = p.read_bytes().replace(b'{', b'{"schema":"duplicate",', 1) if fault == "duplicate_json" else (
            json.dumps({**json.loads(p.read_bytes()), "untrusted": True}).encode())
        p.write_bytes(raw)
        pin = manifest.digest(raw)  # Even an approved pin does not widen the schema.
    elif fault == "not_readonly":
        readonly = True
    with pytest.raises(ValueError):
        manifest.inspect_package(root, pin, require_readonly=readonly)


def test_relocated_separate_process_uses_only_explicit_compatible_host_and_retains_histories(tmp_path):
    root, pin = export(tmp_path)
    host = tmp_path / "host"
    # Copy public code only, including test fixtures for the disposable host setup.
    for name in manifest.host_paths(ROOT):
        p = host / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, p)
    for directory in ("scripts", "backend/tests"):
        for p in (ROOT / directory).glob("*.py"):
            target = host / directory / p.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
    code = '''
import json,sys,pathlib
v=json.load(sys.stdin);host=pathlib.Path(v["host"])
sys.path[:0]=[str(host/"backend"),str(host/"scripts"),str(host/"backend/tests"),str(host)]
import operator_preview_binding as b
from test_operator_preview_package import selected,protected,request
from test_copy_recovery_disposition import f
case=pathlib.Path(v["case"]);case.mkdir(mode=0o700)
fixture=f.__wrapped__(case);value=next(fixture)
try:
    selected_binding,target=selected(value);before=protected(value)
    app=b.bind_preview(v["root"],v["pin"],host_root=host,binding=selected_binding,require_readonly=False)
    assert request(value,app).status_code==200
    assert protected(value)==before
    print(json.dumps({"relocated_host":True,"read_only_histories":True,"production_activation":False}))
finally:
    try:next(fixture)
    except StopIteration:pass
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], input=json.dumps({"host": str(host),
        "root": str(root), "pin": pin, "case": str(tmp_path / "case")}), text=True,
        capture_output=True, timeout=30, cwd=tmp_path, env={"PATH": os.environ.get("PATH", "")})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["relocated_host"] is True


def test_bound_preview_and_independent_entry_retain_exact_versions_without_history_writes(f, tmp_path):
    root, pin = export(tmp_path)
    spec, target = selected(f)
    before = protected(f)
    app = load(root, pin, spec)
    response = request(f, app)
    assert response.status_code == 200 and target.receipt_sha256 not in response.text
    assert request(f, app, "/api/v1/firm-admin/disposition-receipt-stage/reobserve", data=payload(target)).status_code == 200
    f.revoke("reviewer")
    assert request(f, app).status_code == 403
    assert protected(f) == before


@pytest.mark.parametrize("field,value", [("source_id", "0" * 32), ("handoff_sha256", "0" * 64),
    ("binding_sha256", "0" * 64), ("profile_id", "0" * 32), ("preparer_id", "0" * 32),
    ("reviewer_id", "0" * 32), ("origin", "http://foreign.invalid")])
def test_exact_trusted_host_fields_cannot_be_substituted(f, tmp_path, field, value):
    root, pin = export(tmp_path)
    spec, _ = selected(f)
    before = protected(f)
    with pytest.raises(ValueError):
        load(root, pin, replace(spec, **{field: value}))
    assert protected(f) == before


def test_host_code_and_loaded_namespace_must_match_before_binding(f, tmp_path):
    root, pin = export(tmp_path)
    spec, _ = selected(f)
    value, _ = manifest.inspect_package(root, pin, require_readonly=False)
    with patch.dict(sys.modules, {"operator_checksum_handoff": object()}), pytest.raises(ValueError):
        load(root, pin, spec)
    wrong = {**value, "host_sha256": {**value["host_sha256"], "scripts/operator_review_auth.py": "0" * 64}}
    with pytest.raises(ValueError):
        manifest.inspect_host(ROOT, wrong, require_readonly=False)
    with patch.dict(sys.modules, {"app.firm_rbac": None}), pytest.raises(ValueError):
        manifest.inspect_host(ROOT, value, require_readonly=False)


def test_untyped_binding_is_rejected_without_opening_any_stage():
    with patch.object(binding, "inspect_package", side_effect=AssertionError("no stage read")), pytest.raises(ValueError):
        binding.bind_preview("untrusted", "0" * 64, host_root=ROOT, binding={})


def test_verification_work_budget_is_enforced_before_execution(tmp_path):
    root, pin = export(tmp_path)
    with patch.object(manifest.time, "monotonic", side_effect=[0, 21]), pytest.raises(ValueError):
        manifest.inspect_package(root, pin, require_readonly=False)


def test_page_changed_between_inspection_and_execution_withholds_callable(f, tmp_path):
    root, pin = export(tmp_path)
    spec, _ = selected(f)
    before = protected(f)
    original = binding.HostBinding.validate
    def changed(self):
        result = original(self)
        (root / "operator_inspection_preview.html").write_text("changed-after-inspection")
        return result
    with patch.object(binding.HostBinding, "validate", changed), pytest.raises(ValueError):
        load(root, pin, spec)
    assert protected(f) == before


def test_expiry_during_final_binding_withholds_the_callable(f, tmp_path):
    root, pin = export(tmp_path)
    spec, target = selected(f)
    before = protected(f)
    original = binding.HostBinding.validate
    calls = 0
    def late(self):
        nonlocal calls
        calls += 1
        result = original(self)
        if calls == 2:
            f.now = target.created_at + 301
        return result
    with patch.object(binding.HostBinding, "validate", late), pytest.raises(ValueError):
        load(root, pin, spec)
    assert protected(f) == before


def test_host_scheme_authority_and_proxy_headers_rejected_before_body_or_private_reads(f, tmp_path):
    root, pin = export(tmp_path)
    spec, _ = selected(f)
    app = load(root, pin, spec)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=spec.origin) as client:
            for headers, url in [({"host": "foreign.invalid"}, spec.origin),
                    ([("host", "operator.invalid"), ("host", "operator.invalid")], spec.origin),
                    ({"forwarded": "host=operator.invalid"}, spec.origin),
                    ({"x-forwarded-host": "operator.invalid"}, spec.origin),
                    ({"host": "operator.invalid"}, "https://operator.invalid")]:
                response = await client.post(url + "/api/v1/firm-admin/disposition-receipt-stage/preview", headers=headers)
                assert response.status_code == 403 and response.json() == {"state": "denied"}
                assert response.headers["cache-control"] == "no-store"
    with patch.object(app.preview.adapter.service.reconciler.disposition.planner.authority,
                      "resolve", side_effect=AssertionError("no auth or body read")):
        asyncio.run(run())
