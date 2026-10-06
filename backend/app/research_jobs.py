"""One bounded local research coordinator; persistence owns the job outcome.

No private payloads enter this queue, only record IDs. Running calls stop at
checkpoints; a cancel request never pretends that an in-flight call has exited.
"""

import fcntl
import logging
import os
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Condition, Lock, Thread

from sqlalchemy import select, text
from sqlalchemy.orm.exc import StaleDataError

from .auth import require_matter
from .db import Record, User, now, uid

ACTIVE = frozenset({"queued", "running", "cancelling"})
LEASE_KEY = 709706249715316078
logger = logging.getLogger(__name__)


class QueueUnavailable(Exception):
    def __init__(self, *, closed=False):
        self.closed = closed
        super().__init__("Research admission closed" if closed else "Research capacity reached")


class JobStopped(Exception):
    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(outcome)


def submission(budget_seconds):
    started = datetime.now(timezone.utc)
    return {"status": "queued", "phase": "queued", "budget_seconds": budget_seconds,
            "deadline_at": (started + timedelta(seconds=budget_seconds)).isoformat()}


def ensure_active(state):
    if state.get("status") in {"cancelled", "cancelling"}:
        reason = state.get("stop_reason", "user_requested")
        raise JobStopped("interrupted" if reason == "service_shutdown" else "cancelled")
    if state.get("status") not in {"queued", "running"}:
        raise JobStopped(state.get("status", "failed"))
    if state.get("deadline_at"):
        deadline = datetime.fromisoformat(state["deadline_at"])
        if deadline.tzinfo is None:
            raise ValueError("Research deadline requires a timezone")
        if datetime.now(timezone.utc) >= deadline:
            raise JobStopped("timed_out")


def checkpoint(app, run_id, phase):
    app.state.research_owner()
    store = app.state.store
    with store.session() as session:
        record = session.get(Record, run_id, with_for_update=True)
        if not record or record.kind != "research":
            raise JobStopped("interrupted")
        state = store.decode(record)
        ensure_active(state)
        user = session.get(User, record.owner_id)
        if not user or not user.active:
            raise ValueError("Research access revoked")
        matter = require_matter(session, record.matter_id, user)
        if store.decode(matter).get("status") == "archived":
            raise JobStopped("cancelled")
        state["phase"] = phase
        store.update(record, state)
        session.commit()


def request_stop(store, run_id, reason="user_requested", *, authorize=None):
    """Idempotent intent; callers must authorize before using this internal helper."""
    for attempt in range(3):
        try:
            with store.session() as session:
                if authorize is not None:
                    authorize(session)
                record = session.get(Record, run_id, with_for_update=True, populate_existing=True)
                if authorize is not None:
                    authorize(session)
                if not record or record.kind != "research":
                    return None
                state = store.decode(record)
                if state["status"] in {"queued", "running"}:
                    state.update(status="cancelling", stop_reason=reason, cancel_requested_at=now())
                    store.update(record, state)
                    session.commit()
                return store.view(record)
        except StaleDataError:
            if attempt == 2:
                raise


def finish_run(store, run_id, outcome="failed", error_code=None):
    """Called only after execution exits, or after a queued job was removed."""
    for attempt in range(3):
        try:
            with store.session() as session:
                record = session.get(Record, run_id, with_for_update=True)
                if not record or record.kind != "research":
                    return
                state = store.decode(record)
                if state["status"] not in ACTIVE:
                    return
                if state["status"] == "cancelling":
                    outcome = "interrupted" if state.get("stop_reason") == "service_shutdown" else "cancelled"
                state.update(status=outcome, finished_at=now(), phase="finished")
                if outcome == "timed_out":
                    state.update(error="Araştırmanın süre bütçesi doldu; sonuç yayımlanmadı.",
                                 error_code="research_budget_exhausted")
                elif outcome == "interrupted":
                    state.update(error="Araştırma hizmet durduğu için kesildi; yeniden başlatın.",
                                 error_code="research_interrupted")
                elif outcome == "failed":
                    state.update(error="Çıktı doğrulanamadı; sonuç yayımlanmadı.",
                                 error_code=error_code or "research_worker_failed")
                store.update(record, state)
                session.commit()
                return
        except StaleDataError:
            if attempt == 2:
                raise


def recover_runs(store):
    with store.session() as session:
        for record in session.scalars(select(Record).where(Record.kind == "research")):
            state = store.decode(record)
            if state["status"] in ACTIVE:
                state.update(status="interrupted", phase="finished", finished_at=now(),
                             error="Araştırma sunucu yeniden başlatılırken kesildi; yeniden başlatın.",
                             error_code="research_interrupted")
                store.update(record, state)
        session.commit()


@contextmanager
def coordinator_lease(store):
    """Prevent a second API coordinator from doubling capacity or recovering live jobs."""
    if store.engine.dialect.name == "postgresql":
        with store.engine.connect() as connection:
            if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LEASE_KEY}):
                raise RuntimeError("Another research coordinator owns this database; use one API worker")
            connection.commit()
            pid = connection.scalar(text("SELECT pg_backend_pid()"))
            connection.commit()
            mutex, lost = Lock(), False

            def verify():
                nonlocal lost
                with mutex:
                    if lost:
                        raise RuntimeError("Research coordinator lease lost; restart required")
                    try:
                        owned = connection.scalar(text(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                            "AND pid = pg_backend_pid() AND pid = :pid AND classid = :upper "
                            "AND objid = :lower AND objsubid = 1 AND granted)"),
                            {"pid": pid, "upper": LEASE_KEY >> 32, "lower": LEASE_KEY & 0xffffffff})
                        connection.commit()
                        if not owned:
                            raise RuntimeError("Research coordinator lease lost")
                    except Exception:
                        lost = True
                        connection.invalidate()
                        raise RuntimeError("Research coordinator lease lost; restart required") from None

            try:
                yield verify
            finally:
                # Never return a session-level lock to the connection pool.
                if not lost:
                    try:
                        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LEASE_KEY})
                        connection.commit()
                    except Exception:
                        connection.invalidate()
    else:
        lock_path = Path(store.engine.url.database).absolute().with_suffix(".research.lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another research coordinator owns this database; use one API worker") from None
            yield lambda: None
        finally:
            os.close(fd)


class ResearchJobs:
    """A removable bounded queue, not an executor queue of cancelled tombstones."""

    def __init__(self, work, stop, finish, *, workers=5, capacity=10, verify_owner=lambda: None):
        if not 1 <= workers <= capacity <= 10:
            raise ValueError("Invalid research capacity")
        self._work, self._stop, self._finish = work, stop, finish
        self._verify_owner = verify_owner
        self._capacity, self._condition = capacity, Condition()
        self._jobs, self._queue, self._closed = {}, deque(), False
        self._threads = [Thread(target=self._worker, name=f"research-{index}") for index in range(workers)]
        for thread in self._threads:
            thread.start()

    @contextmanager
    def reserve(self):
        try:
            self._verify_owner()
        except Exception:
            with self._condition:
                self._closed = True
                self._condition.notify_all()
            raise QueueUnavailable(closed=True) from None
        ident = uid()
        with self._condition:
            if self._closed or len(self._jobs) >= self._capacity:
                raise QueueUnavailable(closed=self._closed)
            self._jobs[ident] = "reserved"
        try:
            yield ident
        finally:
            with self._condition:
                if self._jobs.get(ident) == "reserved":
                    del self._jobs[ident]

    def submit(self, ident):
        with self._condition:
            if self._closed or self._jobs.get(ident) != "reserved":
                raise QueueUnavailable(closed=True)
            self._jobs[ident] = "queued"
            self._queue.append(ident)
            self._condition.notify()

    def cancel(self, ident):
        # Intent must be persisted before this call. A reserved job will inspect
        # that intent when it starts; no worker may acknowledge a running call.
        with self._condition:
            if self._jobs.get(ident) != "queued":
                return
            self._queue.remove(ident)
            self._jobs[ident] = "finishing"
        self._complete(ident)

    def _complete(self, ident):
        try:
            self._finish(ident)
        except Exception:
            # Unknown durable outcome stops admission; never silently keep
            # accepting jobs with stale running records after database failure.
            with self._condition:
                self._closed = True
                self._condition.notify_all()
            logger.error("Research outcome persistence failed; admission disabled")
        finally:
            with self._condition:
                self._jobs.pop(ident, None)
                self._condition.notify_all()

    def _worker(self):
        while True:
            with self._condition:
                while not self._queue and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                ident = self._queue.popleft()
                self._jobs[ident] = "running"
            try:
                self._work(ident)
            except Exception:
                logger.error("Research worker exited without a confirmed outcome")
            finally:
                self._complete(ident)

    def close(self):
        with self._condition:
            self._closed = True
            pending = list(self._jobs)
            self._condition.notify_all()
        failure = None
        try:
            for ident in pending:
                try:
                    self._stop(ident)
                    self.cancel(ident)
                except Exception as exc:
                    failure = exc
                    logger.error("Research shutdown intent could not be persisted")
        finally:
            for thread in self._threads:
                thread.join()
        if failure is not None:
            raise RuntimeError("Research shutdown incomplete; restart recovery required") from None
