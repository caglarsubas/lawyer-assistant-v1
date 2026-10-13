"""Actual complete-assembly readers and rights writers in a disposable database."""
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from sqlalchemy import update
from test_declared_graph_assembly import build
from test_snapshot_set_postgres import (
    observe_identity_lock,
    postgres_database,
    postgres_graph_b_snapshot,
    postgres_workspace,
    wait_until_blocked,
)
from test_source_reviews import assess

from app.config import ROOT
from app.declared_graph_assembly import current_assembly
from app.release_snapshot import SnapshotError, readonly_store
from app.source_review_models import SourceReviewHead

__all__ = ["postgres_database", "postgres_graph_b_snapshot", "postgres_workspace"]


def test_five_complete_assembly_readers_keep_both_families_current(postgres_graph_b_snapshot, tmp_path):
    value = build(postgres_graph_b_snapshot, tmp_path)
    current, settings = value["current"], value["settings"]
    barrier, resume = Barrier(6), Event()
    targets = [value["a"]["mappings"][-1][3], current["request"].register_source_id]
    with readonly_store(settings) as store:
        def read():
            with current_assembly(settings, store, current["sources"], value["declaration"], ROOT / "ontology") as (files, inventory, _):
                assert len(inventory["components"]) == 2 and files["inputs/structure.ttl"] and files["inputs/jurisprudence.ttl"]
                barrier.wait(timeout=30)
                assert resume.wait(timeout=10)
        def write(source):
            with current["app"].state.store.session() as session:
                session.execute(update(SourceReviewHead).where(SourceReviewHead.source_id == source)
                                .values(revision=SourceReviewHead.revision))
                session.commit()
        with ThreadPoolExecutor(7) as pool:
            readers = [pool.submit(read) for _ in range(5)]
            writers = []
            try:
                barrier.wait(timeout=30)
                with observe_identity_lock(current["app"].state.store.engine, statement_fragment="UPDATE source_review_heads") as observed:
                    writers = [pool.submit(write, source) for source in targets]
                    deadline = time.monotonic() + 4
                    while len(observed[1]) < 2 and time.monotonic() < deadline:
                        time.sleep(.01)
                    assert len(observed[1]) == 2
                    assert all(wait_until_blocked(current["app"].state.store.engine, pid) for pid in observed[1])
                    assert not any(future.done() for future in writers)
            finally:
                resume.set()
            for future in [*readers, *writers]:
                future.result(timeout=30)
        item = current["evidence"][0][-1]
        with ThreadPoolExecutor(1) as pool:
            with current_assembly(settings, store, current["sources"], value["declaration"], ROOT / "ontology"), \
                    observe_identity_lock(current["app"].state.store.engine) as observed:
                writer = pool.submit(assess, item[1], item[4] + "/review", 6, "rights", decision="rejected")
                assert observed[0].wait(timeout=5)
                assert wait_until_blocked(current["app"].state.store.engine, observed[1][-1])
                assert not writer.done()
            assert writer.result(timeout=10).status_code == 200
        with pytest.raises(SnapshotError), current_assembly(settings, store, current["sources"], value["declaration"], ROOT / "ontology"):
            pytest.fail("The complete dependent graph is withheld after either-family revocation")
