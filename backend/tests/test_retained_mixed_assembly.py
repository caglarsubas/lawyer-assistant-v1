"""Invented retained corpus, original ledgers and external TEST-ONLY signatures."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Graph
from sqlalchemy import event
from test_declared_graph_assembly import assembly as assembly_fixture
from test_declared_graph_assembly import decision_component
from test_final_release_authorization import accepted, activate, form_candidate, stage_for
from test_mixed_graph_snapshot import add_second_context
from test_public_sources import source as source_fixture
from test_release_authorization import signed
from test_release_set_authorization import build_authorized_set
from test_source_reviews import assess

from app import final_release_authorization as final
from app.config import ROOT
from app.declared_graph_assembly import Declaration, VerifiedServingContext, current_assembly
from app.graph_release import LA, RuntimeGraphRelease
from app.mixed_graph_snapshot import MixedGraphRequest
from app.release_authorization import AuthorizationError
from app.release_preparation import canonical
from app.release_snapshot import readonly_store
from app.source_corpus import EvidenceLookup, SourceCorpusService

assembly = assembly_fixture


def added_component(assembly, root):
    request = MixedGraphRequest(schema_version="legal-mixed-graph-selection-v1", structure=assembly["a_request"],
                                jurisprudence=[assembly["current"]["request"]])
    fixture, items = add_second_context((assembly["current"], [], request), root)
    second = {**assembly["current"], "request": fixture[2].jurisprudence[-1]}
    component_root = root / "added-component"
    component_root.mkdir()
    component, _ = decision_component(second, component_root, Path(assembly["settings"].graph_trusted_review_key),
        assembly["component_review_key"], (assembly["settings"].data_dir / "publication-epoch").read_text().strip(),
        grant_key=assembly["component_grant_key"], grant_public=Path(assembly["settings"].graph_b_component_trusted_key))
    return component, items


def added_structure(assembly, root):
    root.mkdir()
    _, inputs, metadata, locators = source_fixture.__wrapped__(root)
    current = assembly["current"]
    app, owner = current["evidence"][0][0][:2]
    value = build_authorized_set((app, owner, None), (current["sources"], inputs, metadata, locators), root,
        keys=(assembly["component_review_key"], Path(assembly["settings"].graph_trusted_review_key)),
        epoch=(assembly["settings"].data_dir / "publication-epoch").read_text().strip(), identity_prefix="retained-additional-a")
    return {"release_id": value["info"]["release_id"], "prepared": str(value["info"]["bundle_path"].parent),
            "grant": str(value["root"] / value["info"]["release_id"])}, value["mappings"]


def successor(previous, pointer, root, components=None, structure=None):
    root.mkdir()
    assembly = {**previous["assembly"]}
    declaration = Declaration.model_validate({**assembly["declaration"].model_dump(), "expected_base": pointer,
        "jurisprudence": components or assembly["declaration"].model_dump()["jurisprudence"],
        "structure": structure or assembly["declaration"].structure.model_dump()})
    assembly.update(declaration=declaration, selection=root / "PRIVATE-selection.json")
    assembly["selection"].write_bytes(canonical(declaration.model_dump()))
    command, settings = assembly["command"], assembly["settings"]
    packet = root / "assembly"
    command.prepare(settings, selection=assembly["selection"], reviewer="TEST-ONLY FINAL REVIEW " + root.name,
        reviewed_at=datetime.now(timezone.utc).isoformat(), output=packet)
    # The new independent public attestation is an actual signature over NEW
    # assembled bytes. No production keys/signatures or prior permission reuse.
    with readonly_store(settings) as reader:
        files, _ = command.io.read_packet(packet, reader, schema_version=command.PACKET_SCHEMA)
        attestation = root / "TEST-ONLY-external-final-review.json"
        signed(attestation, command.io.parse_json(files["public-review-body.json"]), assembly["key"], command.io)
        reviewed = root / "reviewed"
        command.io.atomic_packet(reviewed, command.io.sealed_files({**files, "review-attestation.json": attestation.read_bytes()},
            reader, schema_version=command.PACKET_SCHEMA))
    value = {**previous, "assembly": assembly, "packet": reviewed, "candidate": root / "candidate",
             "permission_expires_at": previous["body"]["expires_at"]}
    form_candidate(value, value["candidate"])
    with readonly_store(settings) as reader:
        permission, _ = command.io.read_packet(value["candidate"] / "permission", reader)
        request = reader.decode(SimpleNamespace(payload=permission["request.fernet"].decode()))
    value["body"] = final.approval_body(request)
    value["authorization"] = root / "TEST-ONLY-external-whole-permission.json"
    signed(value["authorization"], value["body"], value["key"], command.io)
    return value


def test_two_successors_preserve_full_mixed_inventory_current_grants_and_rollback(assembly, tmp_path):
    first = stage_for(assembly, tmp_path)
    accepted(first)
    serving, root, key, first_info, guard, first_pointer = activate(first)
    component, later_items = added_component(assembly, tmp_path)
    structure, added_sources = added_structure(assembly, tmp_path / "new-structure")
    second = successor(first, first_pointer, tmp_path / "second", [component], structure)
    assert set(first["body"]["component_release_ids"]) < set(second["body"]["component_release_ids"])
    second_info = serving.validate_prepared(second["candidate"] / "prepared", key)
    # The old WHOLE permission cannot authorize a freshly assembled child.
    with pytest.raises(AuthorizationError), guard(second_info, "install"):
        pytest.fail("New whole permission is mandatory")
    accepted(second)
    serving.install(root, second["candidate"] / "prepared", key, authorization_guard=guard)
    second_pointer = serving.activate(root, second_info["release_id"], key, expected_current=first_info["release_id"],
        expected_sequence=1, authorization_guard=guard)
    third = successor(second, second_pointer, tmp_path / "third", [component])
    accepted(third)
    third_info = serving.validate_prepared(third["candidate"] / "prepared", key)
    serving.install(root, third["candidate"] / "prepared", key, authorization_guard=guard)
    third_pointer = serving.activate(root, third_info["release_id"], key, expected_current=second_info["release_id"],
        expected_sequence=2, authorization_guard=guard)
    assert third_pointer["sequence"] == 3
    for family in ("structure", "jurisprudence"):
        graphs = [Graph().parse(value["candidate"] / "prepared/bundle/inputs" / (family + ".ttl"), format="turtle")
                  for value in (first, second, third)]
        assert set(graphs[0]) < set(graphs[1]) <= set(graphs[2])
    active = serving.load_active(root, key)
    # All original sources are read once in ONE transaction; no writes or
    # nested original-source sessions survive the retained-chain traversal.
    with readonly_store(assembly["settings"]) as reader:
        connections, statements = set(), []
        def capture(connection, cursor, statement, parameters, context, executemany):
            connections.add(id(connection))
            statements.append(statement)
        event.listen(reader.engine, "before_cursor_execute", capture)
        auth, _ = final._packet_tools().read_packet(assembly["settings"].data_dir / "release-authorizations" / third_info["release_id"], reader)
        binding = reader.decode(SimpleNamespace(payload=auth["binding.fernet"].decode()))
        with serving.publication_lock(root, shared=True) as descriptor, current_assembly(assembly["settings"], reader, assembly["current"]["sources"],
                third["assembly"]["declaration"], ROOT / "ontology",
                serving_context=VerifiedServingContext(third_info["release_id"], binding["original_pointer_sha256"],
                    canonical(third_pointer), canonical(third_pointer), descriptor)):
            pass
        assert len(connections) == 1
        assert statements and all(statement.lstrip().upper().startswith(("SELECT", "SHOW")) for statement in statements)
    with guard(active, "read"):
        pass
    rolled = serving.rollback(root, key, expected_current=third_info["release_id"],
        expected_sequence=3, authorization_guard=guard)
    assert rolled["sequence"] == 4
    # Source retrieval spans the exact whole retained release even when a
    # decision has no eligible dated/legally-reviewed authority relationship.
    # Construct AFTER rollback so the following denial proves source withdrawal,
    # independently of pointer drift.
    runtime = RuntimeGraphRelease(root, key, authorization_guard=guard)
    assert runtime.info is not None
    from rdflib import RDF
    passage = next(runtime._resources.subjects(RDF.type, LA.EvidencePassage))
    corpus = SourceCorpusService(runtime).search("TEST ONLY", passage_id=str(passage), as_of="1921-01-01")
    assert corpus["snapshot"]["release_id"] == second_info["release_id"]
    assert corpus["coverage"]["eligible_passages"] > 0 and len(corpus["hits"]) == 1
    assert corpus["hits"][0]["authority_id"] is None
    item = corpus["hits"][0]
    lookup = EvidenceLookup(passage_id=item["passage_id"], source_version_id=item["source_version_id"],
        expected_release_id=second_info["release_id"], expected_serving_sha256=corpus["snapshot"]["serving_sha256"])
    assert SourceCorpusService(runtime).get_evidence(lookup)["hit"]["text"] == item["text"]
    # A source omitted from the new declaration is still mandatory, including
    # the shared register. Withdrawal denies both descendant and prior release.
    item = assembly["current"]["evidence"][0][0]
    assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    with pytest.raises(AuthorizationError), guard(serving.load_active(root, key), "read"):
        pytest.fail("Retained original source cannot be dropped")
    assert SourceCorpusService(runtime).search("TEST ONLY")["coverage"]["status"] == "unavailable"
    assert SourceCorpusService(runtime).get_evidence(lookup)["status"] == "unavailable"
    assert serving.read_pointer(root) == rolled
    assert later_items and added_sources


