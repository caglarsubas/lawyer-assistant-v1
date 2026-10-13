"""Actual whole-release concurrent reads and rights writes in an owned child DB."""
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from sqlalchemy import update
from test_declared_graph_assembly import build
from test_final_release_authorization import accepted, activate, stage_for
from test_snapshot_set_postgres import (
    observe_identity_lock,
    postgres_database,
    postgres_graph_b_snapshot,
    postgres_workspace,
    wait_until_blocked,
)
from test_source_reviews import assess

from app.final_release_authorization import FinalReleaseAuthorization
from app.release_authorization import AuthorizationError
from app.source_review_models import SourceReviewHead

__all__ = ["postgres_database", "postgres_graph_b_snapshot", "postgres_workspace"]


def test_five_authorized_whole_release_readers_protect_all_member_rights(postgres_graph_b_snapshot, tmp_path):
    value = stage_for(build(postgres_graph_b_snapshot, tmp_path), tmp_path)
    accepted(value)
    serving, root, key, _, _, _ = activate(value)
    info = serving.load_active(root, key)
    current = value["assembly"]["current"]
    barrier, resume = Barrier(6), Event()
    targets = [value["assembly"]["a"]["mappings"][-1][3], current["request"].register_source_id]
    def read():
        with FinalReleaseAuthorization(value["settings"]).guard(info, "read") as receipt:
            assert receipt["scope"] == "complete_declared_release"
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
            # Every read also holds the real publication SH descriptor.
            with pytest.raises(ValueError, match="Publication is locked"), serving.publication_lock(root):
                pytest.fail("A transition cannot bypass live shared readers")
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
    assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    with pytest.raises(AuthorizationError), FinalReleaseAuthorization(value["settings"]).guard(info, "read"):
        pytest.fail("Whole-release reads must be withdrawn after any later rights decision")
