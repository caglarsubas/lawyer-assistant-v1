"""Current whole and retained release withdrawal; independent TEST-ONLY inputs."""
from pathlib import Path
from uuid import uuid4

import pytest
from test_final_release_authorization import accepted, activate
from test_final_release_authorization import staged as staged_fixture
from test_retained_mixed_assembly import assembly as assembly_fixture
from test_retained_mixed_assembly import stage_for
from test_source_reviews import assess

from app import final_release_authorization as final
from app import retained_graph_assembly as retained
from app.config import ROOT
from app.declared_graph_assembly import Declaration, current_assembly
from app.graph_release import RuntimeGraphRelease
from app.mixed_graph_snapshot import RetainedGraphRequest
from app.release_authorization import AuthorizationError
from app.release_preparation import canonical
from app.release_snapshot import readonly_store

assembly = assembly_fixture
staged = staged_fixture


def test_aggregate_plan_rejects_conflicting_pins_and_duplicate_contexts(assembly):
    data = {"schema_version": "legal-retained-mixed-selection-v1",
        "structures": [assembly["a_request"].model_dump()], "jurisprudence": [assembly["current"]["request"].model_dump()]}
    conflicting = assembly["a_request"].model_dump()
    conflicting["sources"][0]["expected_source_review_revision"] += 1
    for changes in ({"structures": [*data["structures"], conflicting]},
                    {"jurisprudence": [*data["jurisprudence"], *data["jurisprudence"]]},
                    {"structures": []}, {"extra": True}):
        with pytest.raises(ValueError):
            RetainedGraphRequest.model_validate({**data, **changes})


@pytest.mark.parametrize("change", ["a-rights", "b-rights", "epoch", "fifth-key", "packet", "pointer"])
def test_active_whole_release_withdrawn_after_any_dependency_changes(staged, change):
    value = staged
    accepted(value)
    serving, root, key, info, guard, pointer = activate(value)
    runtime = RuntimeGraphRelease(root, key, guard) if change == "pointer" else None
    if change == "a-rights":
        from app.release_set_authorization import _selection
        io = final._packet_tools()
        grant = Path(value["assembly"]["declaration"].structure.grant)
        source_binding = io.parse_json(io.read_file(grant / "authorization.json", 64 * 1024))["body"]["source_binding"]
        source_id = _selection(source_binding, io).sources[-1].source_id
        # Same original rights service; a later revision withdraws all use.
        app, client = value["assembly"]["current"]["evidence"][0][0][:2]
        assert assess(client, f"/api/v1/public-sources/{source_id}/review", 6, "rights", decision="rejected").status_code == 200
    elif change == "b-rights":
        item = value["assembly"]["current"]["evidence"][0][-1]
        assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    elif change == "epoch":
        (value["settings"].data_dir / "publication-epoch").write_text(str(uuid4()) + "\n")
    elif change == "fifth-key":
        value["public"].write_bytes(value["assembly"]["public"].read_bytes())
    elif change == "packet":
        (value["packet"] / "inputs/structure.ttl").write_bytes(b"changed")
    else:
        (root / "active.json").chmod(0o600)
        (root / "active.json").write_bytes(canonical({**pointer, "sequence": 2}))
    runtime = runtime or RuntimeGraphRelease(root, key, guard)
    assert runtime.status()["status"] == "unavailable"
    with pytest.raises(AuthorizationError):
        if change == "pointer":
            with guard(runtime.info, "read"):
                pytest.fail("Prior pinned pointer is stale")
        else:
            serving.install(root, value["candidate"] / "prepared", key, authorization_guard=guard)


def test_complete_retained_bytes_keys_grants_and_budgets_fail_closed(assembly, tmp_path, monkeypatch):
    first = stage_for(assembly, tmp_path)
    accepted(first)
    serving, root, _, _, _, pointer = activate(first)
    child = Declaration.model_validate({**assembly["declaration"].model_dump(), "expected_base": pointer})
    targets = [first["packet"] / "dependencies.fernet", first["candidate"] / "permission/request.fernet",
        assembly["settings"].data_dir / "release-authorizations" / pointer["release_id"] / "grant.fernet",
        root / "releases" / pointer["release_id"] / "jurisprudence.nq",
        Path(assembly["declaration"].jurisprudence[0].grant) / "grant.fernet",
        Path(assembly["settings"].graph_b_review_trusted_key), first["public"],
        assembly["settings"].data_dir / "publication-epoch"]
    for target in targets:
        raw = target.read_bytes()
        target.chmod(0o600)
        target.write_bytes(assembly["public"].read_bytes() if target == first["public"] else raw + b"substituted")
        try:
            with readonly_store(assembly["settings"]) as reader, pytest.raises(Exception):
                with current_assembly(assembly["settings"], reader, assembly["current"]["sources"], child, ROOT / "ontology"):
                    pytest.fail("Changed retained dependency was accepted")
        finally:
            target.write_bytes(raw)
    # Failed EXIT still withholds newly staged output. Earlier bytes and the
    # active pointer are preserved; the caller cannot inherit an entry verdict.
    selection = tmp_path / "retained-selection.json"
    selection.write_bytes(canonical(child.model_dump()))
    output = tmp_path / "interrupted-retained-output"
    original = assembly["command"].io.atomic_packet
    parent_packet = first["packet"] / "dependencies.fernet"
    parent_raw = parent_packet.read_bytes()
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        parent_packet.write_bytes(parent_raw + b"substituted after staging")
        return result
    with monkeypatch.context() as patch:
        patch.setattr(assembly["command"].io, "atomic_packet", changed)
        try:
            from datetime import datetime, timezone
            with pytest.raises(ValueError):
                assembly["command"].prepare(assembly["settings"], selection=selection,
                    reviewer="TEST-ONLY FRESH FINAL REVIEW", reviewed_at=datetime.now(timezone.utc).isoformat(), output=output)
        finally:
            parent_packet.write_bytes(parent_raw)
    assert not output.exists()
    for limit in ("MAX_DEPTH", "MAX_COMPONENTS", "MAX_FILES", "MAX_BYTES"):
        with monkeypatch.context() as patch:
            patch.setattr(retained, limit, 0)
            with readonly_store(assembly["settings"]) as reader, pytest.raises(ValueError):
                with current_assembly(assembly["settings"], reader, assembly["current"]["sources"], child, ROOT / "ontology"):
                    pytest.fail("Oversized complete inventory was accepted")
    # A successful final reconstruction proves denials came from each changed
    # dependency, not a broken positive fixture or a cached denial verdict.
    with readonly_store(assembly["settings"]) as reader:
        with current_assembly(assembly["settings"], reader, assembly["current"]["sources"], child, ROOT / "ontology") as (_, inventory, _):
            assert inventory["retained_base"]["pointer"] == pointer
    assert serving.read_pointer(root) == pointer
