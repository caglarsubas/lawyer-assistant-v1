"""Complete invented corpus and EXTERNAL TEST-ONLY signatures; no real law review."""
import importlib.util
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from graph_b_test_seeds import cloned_signed_snapshot
from rdflib import RDF, Graph, Literal
from test_graph_b_publication import prepare as prepare_b
from test_graph_b_publication import request_args
from test_graph_b_snapshot import current as current_fixture
from test_graph_b_snapshot import opened
from test_public_sources import source as source_fixture
from test_release_authorization import signed
from test_release_set_authorization import build_authorized_set
from test_source_reviews import assess

from app import graph_b_component_grants as grants
from app import graph_b_publication as b_public
from app.config import ROOT
from app.declared_graph_assembly import Declaration, current_assembly
from app.graph_b_review import configured_key_path
from app.graph_release import LA, _load_serving
from app.public_graph_union import ASM, compile_union
from app.release_authorization import _packet_tools
from app.release_preparation import canonical, digest
from app.release_snapshot import readonly_store

current = current_fixture


def command_module():
    spec = importlib.util.spec_from_file_location("declared_assembly_command_test", ROOT / "scripts/assemble_legal_graphs.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def key_pair(root, name):
    key = Ed25519PrivateKey.generate()  # TEST ONLY, never deployment key custody.
    path = root / ("TEST-ONLY-" + name + ".pem")
    path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return key, path


def decision_component(current, root, public_review_key, public_signing_key, epoch, *, grant_key=None, grant_public=None):
    io, serving = _packet_tools(), _load_serving()
    settings = current["app"].state.settings
    command, packet, _ = prepare_b(current, root)
    with readonly_store(settings) as store, opened(current, store) as snapshot:
        files, packet_hash = io.read_packet(packet, store, schema_version=b_public.PACKET_SCHEMA)
        private = b_public.private_evidence(store, files)
        b_root = root / "decision-public"
        b_root.mkdir()
        for name in private["public_input_paths"]:
            path = b_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(files[name])
        # Graph B uses the same COMPONENT public-review trust as the A component.
        attestation = b_root / "TEST-ONLY-public-review.json"
        signed(attestation, io.parse_json(files["public-review-body.json"]), public_signing_key, io)
        serving._release.create_bundle(ROOT / "ontology",
            {family: b_root / "inputs" / (family + ".ttl") for family in ("structure", "jurisprudence")},
            b_root / "evidence", b_root / "bundle", attestation, public_review_key)
        prepared = b_root / "prepared"
        info = serving.prepare(b_root / "bundle", public_review_key, prepared)
        _, args = request_args(current, snapshot, files, private)
        args.update(packet_sha256=packet_hash, epoch=epoch)
        key, public = (grant_key, grant_public) if grant_key else key_pair(root, "component-grant")
        settings.graph_b_component_trusted_key = str(public)
        request = b_public.permission_request(files, private, snapshot, info, **args)
        body = grants.grant_body(request, configured_key_path(public)[2])
        envelope = root / "TEST-ONLY-component-grant.json"
        signed(envelope, body, key, io)
        grant = root / "retained-component"
        io.atomic_packet(grant, io.sealed_files(grants.retained_files(store, files, envelope.read_bytes()),
                                                store, schema_version=b_public.PACKET_SCHEMA))
    return {"release_id": info["release_id"], "prepared": str(prepared), "grant": str(grant)}, key


def build(current, root):
    serving = _load_serving()
    a_root = root / "structure-fixture"
    a_root.mkdir()
    _, inputs, metadata, locators = source_fixture.__wrapped__(a_root)
    app, owner = current["evidence"][0][0][:2]
    a = build_authorized_set((app, owner, None), (current["sources"], inputs, metadata, locators), a_root)
    settings = app.state.settings
    settings.graph_trusted_review_key = str(a["public_key"])
    b, component_key = decision_component(current, root, a["public_key"], a["key"], a["epoch"])
    final_key, final_public = key_pair(root, "independent-final-review")
    settings.graph_final_review_trusted_key = str(final_public)
    published = root / "published"
    serving.initialize(published)
    settings.graph_release_dir = str(published)
    declaration = Declaration.model_validate({"schema_version": "legal-declared-graph-selection-v1",
        "operator_id": current["operator_id"], "expected_base": None,
        "structure": {"release_id": a["info"]["release_id"], "prepared": str(a["info"]["bundle_path"].parent),
                      "grant": str(a["root"] / a["info"]["release_id"])},
        "jurisprudence": [b]})
    selection = root / "PRIVATE-selection.json"
    selection.write_bytes(canonical(declaration.model_dump()))
    return {"current": current, "a": a, "declaration": declaration, "settings": settings,
            "key": final_key, "component_grant_key": component_key, "public": final_public, "root": root, "selection": selection, "command": command_module()}


def prepared(value, destination):
    result = value["command"].prepare(value["settings"], selection=value["selection"],
        reviewer="TEST-ONLY INDEPENDENT FINAL REVIEWER", reviewed_at=datetime.now(timezone.utc).isoformat(), output=destination)
    assert result["signature_created"] is False and result["final_attestation_required"] is True
    return destination


def accepted(value, packet, output):
    with readonly_store(value["settings"]) as store:
        files, _ = value["command"].io.read_packet(packet, store, schema_version=value["command"].PACKET_SCHEMA)
    attestation = output.parent / (output.name + "-TEST-ONLY-external-review.json")
    signed(attestation, value["command"].io.parse_json(files["public-review-body.json"]), value["key"], value["command"].io)
    result = value["command"].accept(value["settings"], packet=packet, attestation=attestation, output=output)
    assert result["independent_final_attestation_accepted"] and result["publication_performed"] is False
    return output, attestation


@contextmanager
def clone(seed, destination):
    root, original = seed
    with cloned_signed_snapshot((root, original["current"]), destination) as current:
        settings = current["app"].state.settings
        for field in ("graph_trusted_review_key", "graph_b_component_trusted_key", "graph_final_review_trusted_key", "graph_release_dir"):
            setattr(settings, field, str(destination / Path(getattr(original["settings"], field)).relative_to(root)))
        def moved(component):
            return {**component, **{name: str(destination / Path(component[name]).relative_to(root)) for name in ("prepared", "grant")}}
        data = original["declaration"].model_dump()
        declaration = Declaration.model_validate({**data, "structure": moved(data["structure"]),
            "jurisprudence": [moved(item) for item in data["jurisprudence"]]})
        selection = destination / "PRIVATE-current-selection.json"
        selection.write_bytes(canonical(declaration.model_dump()))
        value = {"current": current, "settings": settings, "declaration": declaration, "selection": selection,
                 "key": original["key"], "public": destination / original["public"].relative_to(root),
                 "root": destination, "command": command_module(), "component_review_key": original["a"]["key"],
                 "a_request": original["a"]["request"], "component_grant_key": original["component_grant_key"]}
        # Copy setup bytes only. The actual preparation/validation/guard subject
        # reconstructs every current permission per case; do not run the entire
        # subject a second time before every negative input. Positive retained-
        # base/multiple-context and fresh-builder cases qualify this setup.
        yield value


@pytest.fixture
def assembly(synthetic_declared_assembly_seed, tmp_path):
    with clone(synthetic_declared_assembly_seed, tmp_path / "independent-assembly") as value:
        yield value


def test_fresh_complete_graphs_and_external_final_signature(current, tmp_path):
    value = build(current, tmp_path)
    packet = prepared(value, tmp_path / "assembled")
    output, _ = accepted(value, packet, tmp_path / "final-reviewed")
    assert value["command"].validate(value["settings"], output, reviewed=True)["independent_final_attestation_verified"]
    with readonly_store(value["settings"]) as store:
        files, _ = value["command"].io.read_packet(output, store, schema_version=value["command"].PACKET_SCHEMA)
    graphs = {family: Graph().parse(data=files["inputs/" + family + ".ttl"], format="turtle")
              for family in ("structure", "jurisprudence")}
    assert len(set(graphs["structure"].subjects(RDF.type, LA.Assertion))) == 4
    assert len(set(graphs["jurisprudence"].subjects(RDF.type, LA.Assertion))) == 6
    inventory = value["command"].io.parse_json(files["assembly-inputs.json"])
    assert len(inventory["components"]) == 2 and inventory["coverage_scope"] == "declared_components_only"
    assert (None, ASM.inventoryJson, Literal(canonical(inventory).decode())) in graphs["structure"]
    for item in [value["declaration"].structure, *value["declaration"].jurisprudence]:
        for family, graph in graphs.items():
            original = Graph().parse(Path(item.prepared) / "bundle/inputs" / (family + ".ttl"), format="turtle")
            assert set(original).issubset(graph)
    flat = b"\n".join(path.read_bytes() for path in output.rglob("*") if path.is_file())
    for private in (current["operator_id"].encode(), current["audience"], b"source_permissions", b"credential_data", b"dependencies_sha256"):
        assert private not in flat
    assert not (Path(value["settings"].graph_release_dir) / "active.json").exists()
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.rglob("*") if path.is_file())
    with pytest.raises(ValueError):
        accepted(value, packet, output)
    assert output.exists()


@pytest.mark.parametrize("change", ["missing-b", "duplicate-b", "missing-a", "extra", "wrong-base"])
def test_complete_closed_declaration_never_drops_a_member(assembly, tmp_path, change):
    data = assembly["declaration"].model_dump()
    if change == "missing-b":
        data["jurisprudence"] = []
    elif change == "duplicate-b":
        data["jurisprudence"] *= 2
    elif change == "missing-a":
        del data["structure"]
    elif change == "extra":
        data["override"] = True
    else:
        data["expected_base"] = {"format_version": 1, "release_id": "a" * 64, "serving_sha256": "b" * 64,
                                 "previous_release_id": None, "sequence": 1}
    assembly["selection"].write_bytes(canonical(data))
    with pytest.raises(ValueError):
        prepared(assembly, tmp_path / "withheld")
    assert not (tmp_path / "withheld").exists()


@pytest.mark.parametrize("change", ["a-rights", "b-rights", "epoch", "final-key", "same-key", "component-bytes", "grant"])
def test_any_current_member_or_trust_change_withholds_the_whole_assembly(assembly, tmp_path, change):
    packet = prepared(assembly, tmp_path / "assembled")
    current = assembly["current"]
    if change == "a-rights":
        source_id = assembly["declaration"].structure.release_id
        with readonly_store(assembly["settings"]) as store:
            files, _ = _packet_tools().read_packet(Path(assembly["declaration"].structure.grant) / "packet", store,
                                                  schema_version="legal-review-source-set-packet-v1")
            source_id = _packet_tools().parse_json(files["binding.json"])["sources"][-1]["source_id"]
        owner = current["evidence"][0][0][1]
        assert assess(owner, f"/api/v1/public-sources/{source_id}/review", 6, "rights", decision="rejected").status_code == 200
    elif change == "b-rights":
        item = current["evidence"][0][-1]
        assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    elif change == "epoch":
        (assembly["settings"].data_dir / "publication-epoch").write_text(str(uuid4()) + "\n")
    elif change == "final-key":
        assembly["public"].write_bytes(b"changed key")
    elif change == "same-key":
        assembly["settings"].graph_final_review_trusted_key = assembly["settings"].graph_trusted_review_key
    elif change == "component-bytes":
        path = Path(assembly["declaration"].jurisprudence[0].prepared) / "bundle/inputs/jurisprudence.ttl"
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b"# substituted\n")
    else:
        path = Path(assembly["declaration"].jurisprudence[0].grant) / "grant.fernet"
        path.write_bytes(b"changed grant")
    with pytest.raises(Exception):
        assembly["command"].validate(assembly["settings"], packet)
    assert packet.exists()


def test_retained_base_inventory_is_preserved_and_omission_is_denied(assembly, tmp_path):
    serving = _load_serving()
    root = Path(assembly["settings"].graph_release_dir)
    item = assembly["declaration"].structure
    shutil.copytree(item.prepared, root / "releases" / item.release_id)
    info = serving.validate_prepared(Path(item.prepared), Path(assembly["settings"].graph_trusted_review_key))
    pointer = {"format_version": 1, "release_id": item.release_id, "serving_sha256": info["serving_sha256"],
               "previous_release_id": None, "sequence": 1}
    (root / "active.json").write_bytes(canonical(pointer))  # TEST ONLY retained-base fixture.
    with pytest.raises(ValueError):
        prepared(assembly, tmp_path / "omitted-base")
    data = {**assembly["declaration"].model_dump(), "expected_base": pointer}
    assembly["selection"].write_bytes(canonical(data))
    packet = prepared(assembly, tmp_path / "retained-base")
    with readonly_store(assembly["settings"]) as store:
        files, _ = assembly["command"].io.read_packet(packet, store, schema_version=assembly["command"].PACKET_SCHEMA)
    base = assembly["command"].io.parse_json(files["assembly-inputs.json"])["retained_base"]
    assert base["pointer"] == pointer
    assert set(base["files"]) == serving._files(root / "releases" / item.release_id)
    accepted(assembly, packet, tmp_path / "base-reviewed")


@pytest.mark.parametrize("change", ["component-signature", "wrong-final-key", "different-hashes", "extra", "duplicate", "unsigned"])
def test_component_attestation_and_forged_final_approval_cannot_be_reused(assembly, tmp_path, change):
    packet = prepared(assembly, tmp_path / "assembled")
    with readonly_store(assembly["settings"]) as store:
        files, _ = assembly["command"].io.read_packet(packet, store, schema_version=assembly["command"].PACKET_SCHEMA)
    body = assembly["command"].io.parse_json(files["public-review-body.json"])
    path = tmp_path / "TEST-ONLY-final-attestation.json"
    key = assembly["key"]
    if change == "different-hashes":
        body["input_graphs_sha256"]["jurisprudence"] = "f" * 64
    elif change == "extra":
        body["override"] = True
    elif change == "wrong-final-key":
        key = Ed25519PrivateKey.generate()
    signed(path, body, key, assembly["command"].io)
    if change == "component-signature":
        path.write_bytes((Path(assembly["declaration"].jurisprudence[0].prepared) / "bundle/review-attestation.json").read_bytes())
    elif change == "duplicate":
        path.write_bytes(b'{"algorithm":"Ed25519","algorithm":"none"}')
    elif change == "unsigned":
        path.write_bytes(canonical({"algorithm": "none", "body": body, "signature": ""}))
    with pytest.raises(ValueError):
        assembly["command"].accept(assembly["settings"], packet=packet, attestation=path, output=tmp_path / "withheld")
    assert not (tmp_path / "withheld").exists()


@pytest.mark.parametrize("change", ["epoch", "pointer", "key", "interruption"])
def test_late_change_or_interruption_discards_only_new_output(assembly, tmp_path, monkeypatch, change):
    original = assembly["command"].io.atomic_packet
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if change == "epoch":
            (assembly["settings"].data_dir / "publication-epoch").write_text(str(uuid4()) + "\n")
        elif change == "key":
            assembly["public"].write_bytes(b"changed key")
        elif change == "pointer":
            (Path(assembly["settings"].graph_release_dir) / "active.json").write_bytes(b"{}")
        else:
            # A late signal during dependency validation still cleans the artifact
            # using its owned inode; atomic_packet's own rename signal has its
            # separate existing regression suite.
            monkeypatch.setattr(assembly["command"].io, "read_packet", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
        return result
    monkeypatch.setattr(assembly["command"].io, "atomic_packet", changed)
    with pytest.raises((Exception, KeyboardInterrupt)):
        prepared(assembly, tmp_path / "withheld")
    assert not (tmp_path / "withheld").exists()


def test_final_reviewer_independence_and_safe_cli(assembly, tmp_path, monkeypatch, capsys):
    from app import config
    with pytest.raises(ValueError):
        assembly["command"].prepare(assembly["settings"], selection=assembly["selection"],
            reviewer="TEST-ONLY PUBLIC SET REVIEW", reviewed_at=datetime.now(timezone.utc).isoformat(), output=tmp_path / "withheld")
    monkeypatch.setattr(config, "load_settings", lambda: assembly["settings"])
    assert assembly["command"].main(["validate", "/missing-private-packet"]) == 2
    output = capsys.readouterr()
    assert assembly["current"]["operator_id"] not in output.err and "publication_performed" in output.err


def test_union_rejects_conflicting_identity_and_budget(assembly, tmp_path, monkeypatch):
    members = {item.release_id: item.prepared for item in (assembly["declaration"].structure, *assembly["declaration"].jurisprudence)}
    from app import public_graph_union
    monkeypatch.setattr(public_graph_union, "MAX_BYTES", 1)
    with pytest.raises(ValueError):
        compile_union(members, base=None, trusted_key=Path(assembly["settings"].graph_trusted_review_key), ontology_root=ROOT / "ontology")


def test_individually_signed_components_with_conflicting_subjects_cannot_be_unioned(assembly, tmp_path):
    from rdflib import RDFS, URIRef
    serving, io, members = _load_serving(), _packet_tools(), {}
    for index, component in enumerate([assembly["declaration"].structure, assembly["declaration"].jurisprudence[0]]):
        root = tmp_path / ("TEST-ONLY-conflict-" + str(index))
        root.mkdir()
        shutil.copytree(Path(component.prepared) / "bundle/evidence", root / "evidence")
        graphs = {}
        for family in ("structure", "jurisprudence"):
            graph = Graph().parse(Path(component.prepared) / "bundle/inputs" / (family + ".ttl"), format="turtle")
            if family == "structure":
                graph.add((URIRef("urn:tr-law:TEST-ONLY-conflicting-public-identity"), RDFS.label, Literal(str(index))))
            graphs[family] = root / (family + ".ttl")
            graph.serialize(graphs[family], format="turtle")
        body = {"reviewer": "TEST-ONLY CONFLICT REVIEW", "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "decision": "approve", "scope": "national_ontology_and_assertions",
                "ontology_sha256": serving._release.ontology_digest(ROOT / "ontology"),
                "input_graphs_sha256": {family: digest(path.read_bytes()) for family, path in graphs.items()}}
        signed(root / "TEST-ONLY-review.json", body, assembly["key"], io)
        serving._release.create_bundle(ROOT / "ontology", graphs, root / "evidence", root / "bundle",
                                       root / "TEST-ONLY-review.json", assembly["public"])
        info = serving.prepare(root / "bundle", assembly["public"], root / "prepared")
        members[info["release_id"]] = root / "prepared"
    with pytest.raises(ValueError, match="Shared identity definitions conflict"):
        compile_union(members, base=None, trusted_key=assembly["public"], ontology_root=ROOT / "ontology")


def test_two_complete_decision_contexts_share_register_and_cannot_drop_later_grant(assembly, tmp_path):
    from test_mixed_graph_snapshot import add_second_context

    from app.mixed_graph_snapshot import MixedGraphRequest
    request = MixedGraphRequest(schema_version="legal-mixed-graph-selection-v1", structure=assembly["a_request"],
                                jurisprudence=[assembly["current"]["request"]])
    fixture, later_items = add_second_context((assembly["current"], [], request), tmp_path)
    second = {**assembly["current"], "request": fixture[2].jurisprudence[-1]}
    second_root = tmp_path / "second-public-component"
    second_root.mkdir()
    component, _ = decision_component(second, second_root, Path(assembly["settings"].graph_trusted_review_key),
        assembly["component_review_key"], (assembly["settings"].data_dir / "publication-epoch").read_text().strip(),
        grant_key=assembly["component_grant_key"], grant_public=Path(assembly["settings"].graph_b_component_trusted_key))
    data = {**assembly["declaration"].model_dump(), "jurisprudence": [component, *assembly["declaration"].model_dump()["jurisprudence"]]}
    assembly["selection"].write_bytes(canonical(data))
    packet = prepared(assembly, tmp_path / "complete-two-contexts")
    with readonly_store(assembly["settings"]) as store:
        files, _ = assembly["command"].io.read_packet(packet, store, schema_version=assembly["command"].PACKET_SCHEMA)
    graph = Graph().parse(data=files["inputs/jurisprudence.ttl"], format="turtle")
    assert len(set(graph.subjects(RDF.type, LA.Assertion))) == 12
    accepted(assembly, packet, tmp_path / "two-contexts-reviewed")
    item = later_items[-1]
    assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    with pytest.raises(ValueError):
        assembly["command"].validate(assembly["settings"], packet)


def test_caller_cannot_mutate_assembled_output_or_retained_dependency(assembly):
    for change in ("output", "binding"):
        with readonly_store(assembly["settings"]) as store, pytest.raises(ValueError):
            with current_assembly(assembly["settings"], store, assembly["current"]["sources"],
                    assembly["declaration"], ROOT / "ontology") as (files, _, loaded):
                if change == "output":
                    files["inputs/jurisprudence.ttl"] = b""
                else:
                    loaded["structure"]["authorization"] = b"substituted permission"


def test_expiry_during_original_source_exit_withholds_new_output(assembly, tmp_path, monkeypatch):
    from datetime import timedelta

    from app import declared_graph_assembly, release_set_authorization
    original = declared_graph_assembly.locked_mixed_snapshot
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=2)
    @contextmanager
    def expired(*args, **kwargs):
        with original(*args, **kwargs) as snapshot:
            yield snapshot
        monkeypatch.setattr(release_set_authorization, "datetime", Later)
    monkeypatch.setattr(declared_graph_assembly, "locked_mixed_snapshot", expired)
    with pytest.raises(ValueError):
        prepared(assembly, tmp_path / "withheld")
    assert not (tmp_path / "withheld").exists()


@pytest.mark.parametrize("relative", ["bundle/inputs/jurisprudence.ttl", "jurisprudence.nq", "bundle/manifest.json"])
def test_operation_local_public_validation_never_skips_changed_bytes(assembly, relative):
    with readonly_store(assembly["settings"]) as store, pytest.raises(ValueError):
        with current_assembly(assembly["settings"], store, assembly["current"]["sources"],
                assembly["declaration"], ROOT / "ontology"):
            target = Path(assembly["declaration"].jurisprudence[0].prepared) / relative
            target.chmod(0o600)
            target.write_bytes(target.read_bytes() + b"\n# substituted after verified capture\n")
