"""Reduce cyclic collector scans in the existing isolated CI test workers."""

import gc
import os


def pytest_sessionstart(session):
    if os.environ.get("GITHUB_ACTIONS") != "true" or not hasattr(session.config, "workerinput"):
        return
    original = gc.get_threshold()
    if original == (700, 10, 10):
        # Retain automatic collection in every generation. RDF validation
        # produces many short-lived objects. The complete paired suite
        # qualified this bounded CI-only increase with automatic collection
        # active in every generation; scan less often in this disposable worker.
        # Explicit gc.collect() retains its normal behavior.
        gc.set_threshold(14_000, *original[1:])
        session.config.add_cleanup(lambda: gc.set_threshold(*original))
