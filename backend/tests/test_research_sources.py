"""Invented evidence, current guard simulations and private saved products."""

import copy
from types import SimpleNamespace

import pytest
from test_source_corpus import passage, release

from app.graph import GraphBackendError
from app.research import _product_graph_pin, effective_product, guard_product_graph
from app.research_sources import validate_retained
from app.source_corpus import SourceCorpusService


def product():
    reader = release()
    passage(reader, "source", "TEST ONLY source quote; no actual law")
    result = SourceCorpusService(reader).search("source")
    pin = {"status": "verified", "release_id": reader.info["release_id"],
           "serving_sha256": reader.info["serving_sha256"], "activation_sequence": 2}
    return reader, {"status": "needs_review", "snapshots": {"graph_release_pin": pin},
        "evidence": [{"text": "AUTHORIZED PRIVATE EVIDENCE"}], "source_candidates": result,
        "authority_candidates": {"hits": []}, "graph_paths": []}


def test_source_only_and_zero_hit_captures_require_exact_current_release_pin():
    reader, data = product()
    graph = SimpleNamespace(release=reader)
    with guard_product_graph(data, graph):
        pass
    for empty in (False, True):
        invalid = copy.deepcopy(data)
        if empty:
            invalid["source_candidates"]["hits"] = []
            invalid["source_candidates"]["coverage"]["returned_hits"] = 0
        invalid["snapshots"].clear()
        with pytest.raises(GraphBackendError):
            _product_graph_pin(invalid)
        invalid["snapshots"] = copy.deepcopy(data["snapshots"])
        invalid["source_candidates"]["snapshot"]["release_id"] = "d" * 64
        with pytest.raises(GraphBackendError):
            _product_graph_pin(invalid)
    assert _product_graph_pin({"snapshots": {}, "evidence": []}) is None


@pytest.mark.parametrize("field,value", [("text", "PUBLIC FORGERY"), ("source_sha256", "0" * 64),
    ("source_version_id", "urn:test:similar"), ("start_offset", False), ("authority_id", "urn:test:invented"),
    ("finality", "final"), ("matter_applicability", "confirmed"), ("quote_sha256", "0" * 64)])
def test_saved_source_fields_are_reprojected_and_cannot_invent_authority(field, value):
    reader, data = product()
    data["source_candidates"]["hits"][0][field] = value
    with pytest.raises(ValueError):
        validate_retained(reader, data["source_candidates"], reader.info)
    original = copy.deepcopy(data)
    view = effective_product(data, SimpleNamespace(release=reader))
    assert view["status"] == "stale" and view["public_results_withheld"] is True
    assert not view["source_candidates"]["hits"] and not view["authority_candidates"]["hits"]
    assert view["graph_paths"] == [] and view["evidence"] == data["evidence"]
    assert data == original


def test_saved_source_snapshot_and_duplicates_are_not_reused():
    reader, data = product()
    for field, value in (("serving_sha256", "f" * 64), ("ontology_sha256", "f" * 64),
                         ("activation_sequence", 3), ("activation_sequence", True)):
        invalid = copy.deepcopy(data["source_candidates"])
        invalid["snapshot"][field] = value
        with pytest.raises(ValueError):
            validate_retained(reader, invalid, reader.info)
    invalid = copy.deepcopy(data["source_candidates"])
    invalid["hits"] *= 2
    with pytest.raises(ValueError):
        validate_retained(reader, invalid, reader.info)


def test_permission_exit_failure_withholds_public_quotes_without_rewriting_private_work():
    from contextlib import contextmanager
    reader, data = product()
    data["authority_candidates"]["snapshot"] = {"release_id": reader.info["release_id"]}
    data["authority_candidates"]["hits"] = [{"text": "OLD AUTHORITY QUOTE"}]
    data["graph_paths"] = [{"mode": "fuseki", "snapshot": {"release_id": reader.info["release_id"]},
                            "edges": [{"text": "OLD GRAPH QUOTE"}]}]
    @contextmanager
    def failed():
        yield reader.info
        raise ValueError("PRIVATE-SOURCE-RIGHTS-ID")
    reader.current_guard = failed
    before = copy.deepcopy(data)
    result = effective_product(data, SimpleNamespace(release=reader))
    assert not result["source_candidates"]["hits"] and not result["authority_candidates"]["hits"]
    assert result["graph_paths"] == [] and result["evidence"] == data["evidence"]
    assert data == before
