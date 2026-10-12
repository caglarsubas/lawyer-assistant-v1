"""Real mixed-family row locks against isolated TEST-ONLY child databases."""
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from sqlalchemy import update
from test_mixed_graph_snapshot import add_second_context, opened, prepare
from test_snapshot_set_postgres import (
    observe_identity_lock,
    postgres_database,
    postgres_graph_b_snapshot,
    postgres_workspace,
    wait_until_blocked,
)
from test_source_reviews import assess

from app.release_snapshot import SnapshotError, readonly_store
from app.source_review_models import SourceReviewHead

__all__ = ['postgres_database', 'postgres_graph_b_snapshot', 'postgres_workspace']


def test_mixed_five_shared_readers_block_both_families_and_next_use_rejects(postgres_graph_b_snapshot, tmp_path):
    fixture, later_items = add_second_context(prepare(postgres_graph_b_snapshot, tmp_path), tmp_path)
    current, sources, _ = fixture
    app, entered, resume = current['app'], Barrier(6), Event()
    targets = [sources[0][3], later_items[0][3]]

    with readonly_store(app.state.settings) as reader:
        def read(index):
            request = fixture[2].model_copy(update={"jurisprudence": list(reversed(fixture[2].jurisprudence))}) if index % 2 else fixture[2]
            with opened((current, sources, request), reader, shared=True) as snapshot:
                assert snapshot['summary']['source_count'] == 7 and snapshot['summary']['context_count'] == 2
                entered.wait(timeout=10)
                assert resume.wait(timeout=10)

        def write(source):
            with app.state.store.session() as session:
                session.execute(update(SourceReviewHead).where(SourceReviewHead.source_id == source)
                                .values(revision=SourceReviewHead.revision))
                session.commit()

        with ThreadPoolExecutor(7) as pool:
            readers = [pool.submit(read, index) for index in range(5)]
            writers = []
            try:
                entered.wait(timeout=10)
                with observe_identity_lock(app.state.store.engine, statement_fragment='UPDATE source_review_heads') as observed:
                    writers = [pool.submit(write, source) for source in targets]
                    assert observed[0].wait(timeout=5)
                    # Observe the real database waits, not a timed sleep verdict.
                    for future in writers:
                        assert not future.done()
                    deadline = time.monotonic() + 4
                    while len(observed[1]) < 2 and time.monotonic() < deadline:
                        time.sleep(.01)
                    assert len(observed[1]) == 2
                    assert all(wait_until_blocked(app.state.store.engine, pid) for pid in observed[1])
            finally:
                resume.set()
            for future in [*readers, *writers]:
                future.result(timeout=15)
        item = later_items[0]
        with ThreadPoolExecutor(1) as pool:
            with opened(fixture, reader, shared=True), observe_identity_lock(app.state.store.engine) as observed:
                writer = pool.submit(assess, item[1], item[4]+'/review', 6, 'rights', decision='rejected')
                assert observed[0].wait(timeout=5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not writer.done()
            assert writer.result(timeout=10).status_code == 200
        with pytest.raises(SnapshotError), opened(fixture, reader, shared=True):
            pytest.fail('Revoking any member withholds the complete mixed snapshot')
