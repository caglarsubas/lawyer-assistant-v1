"""Portable TEST-ONLY release seed; every test owns independently verified files."""
import json
import os
from collections import defaultdict

import pytest

_ci_times = defaultdict(lambda: {"setup": 0.0, "call": 0.0, "teardown": 0.0, "completed": 0})
_ci_completed = 0


def pytest_runtest_logreport(report):
    """Passive master-only timing: no fixture, verdict or runtime changes."""
    global _ci_completed
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("PYTEST_XDIST_WORKER"):
        return
    row = _ci_times[report.nodeid.split("::", 1)[0]]
    row[report.when] += report.duration
    if report.when == "teardown":
        row["completed"] += 1
        _ci_completed += 1
        if _ci_completed % 100 == 0:
            _print_ci_times()


def _print_ci_times():
    rows = sorted(_ci_times.items(), key=lambda item: sum(item[1][phase] for phase in ("setup", "call", "teardown")), reverse=True)[:8]
    print("\nCI_TIMINGS " + json.dumps({"completed": _ci_completed,
        "slow_files": [{"file": name, **{key: round(value, 2) for key, value in values.items()}}
                       for name, values in rows]}, sort_keys=True), flush=True)


def pytest_terminal_summary(terminalreporter):
    if os.environ.get("GITHUB_ACTIONS") == "true" and not os.environ.get("PYTEST_XDIST_WORKER"):
        _print_ci_times()


def discard_test_seed_logins(store):
    from sqlalchemy import delete

    from app.db import LoginSession
    with store.session() as session:
        session.execute(delete(LoginSession))
        session.commit()


@pytest.fixture(scope="session")
def synthetic_active_release_template(tmp_path_factory):
    # Per pytest worker, outside application storage. The seed contains an empty
    # invented release and a TEST-ONLY public key, no customer or real law data.
    # Rebuilding/installing/activating the same seed for every negative reader
    # case exercises setup work already tested by the dedicated serving suite.
    from test_runtime_graph_release import build_synthetic_active_release
    return build_synthetic_active_release(tmp_path_factory.mktemp("test-only-release-seed"))


@pytest.fixture(scope="session")
def synthetic_serving_seeds(tmp_path_factory):
    from test_serving_releases import build_serving_seeds
    return build_serving_seeds(tmp_path_factory.mktemp("test-only-serving-seeds"))


@pytest.fixture(scope="session")
def synthetic_authorized_set_seed(tmp_path_factory):
    """Reviewed synthetic source-set fixture setup once per isolated pytest worker."""
    from test_public_sources import source
    from test_release_set_authorization import build_authorized_set
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-authorized-set-seed")
    lifetime = fresh_workspace(root)
    fixture_workspace = next(lifetime)
    try:
        seed = build_authorized_set(fixture_workspace, source.__wrapped__(root), root)
    finally:
        # Close all application connections before copying its test-only database.
        lifetime.close()
    return root, seed


@pytest.fixture(scope="session")
def synthetic_authorized_seed(tmp_path_factory):
    from test_provision_mappings import mapping
    from test_public_sources import source
    from test_release_authorization import build_authorized
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-authorized-seed")
    lifetime = fresh_workspace(root)
    fixture_workspace = next(lifetime)
    try:
        seed = build_authorized(mapping.__wrapped__(fixture_workspace, source.__wrapped__(root)), root)
    finally:
        lifetime.close()
    return root, seed


@pytest.fixture(scope="session")
def synthetic_equivalence_seed(tmp_path_factory):
    from test_decision_equivalence import prepare
    from test_jurisprudence_candidates import incoming
    from test_public_sources import source
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-equivalence-seed")
    lifetime = fresh_workspace(root)
    fixture = next(lifetime)
    try:
        value = prepare(fixture[0], fixture[1], *incoming.__wrapped__(source.__wrapped__(root)))
    finally:
        discard_test_seed_logins(fixture[0].state.store)
        lifetime.close()
        fixture[0].state.store.engine.dispose()
    for client in value[1:]:
        client.close()
    return root, value


@pytest.fixture(scope="session")
def synthetic_signed_graph_b_seed(tmp_path_factory):
    from test_graph_b_snapshot import prepare
    from test_jurisprudence_candidates import incoming
    from test_public_sources import source
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-signed-graph-b-seed")
    lifetime = fresh_workspace(root)
    fixture = next(lifetime)
    try:
        value = prepare(fixture, incoming.__wrapped__(source.__wrapped__(root)), root)
    finally:
        discard_test_seed_logins(fixture[0].state.store)
        lifetime.close()
        fixture[0].state.store.engine.dispose()
    for client in (*value["evidence"][1:], value["signed"][2]):
        client.close()
    return root, value


@pytest.fixture(scope="session")
def synthetic_empty_source_workspace(tmp_path_factory):
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-empty-source-workspace")
    lifetime = fresh_workspace(root)
    fixture = next(lifetime)
    discard_test_seed_logins(fixture[0].state.store)
    lifetime.close()
    fixture[0].state.store.engine.dispose()
    return root


@pytest.fixture(scope="session")
def synthetic_component_grant_seed(tmp_path_factory):
    """TEST ONLY setup bytes, never reused current verification or sessions."""
    from test_graph_b_component_grants import accept, setup
    from test_graph_b_publication import prepare as prepare_packet
    from test_graph_b_snapshot import prepare
    from test_jurisprudence_candidates import incoming
    from test_public_sources import source
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-component-grant-seed")
    lifetime = fresh_workspace(root)
    workspace = next(lifetime)
    current = prepare(workspace, incoming.__wrapped__(source.__wrapped__(root)), root)
    try:
        packet = prepare_packet(current, root)
        value = setup(current, packet, root)
        grant = accept(value, root)
    finally:
        discard_test_seed_logins(workspace[0].state.store)
        lifetime.close()
        workspace[0].state.store.engine.dispose()
        for client in (*current["evidence"][1:], current["signed"][2]):
            client.close()
    return root, value, grant


@pytest.fixture(scope="session")
def synthetic_declared_assembly_seed(tmp_path_factory):
    from test_declared_graph_assembly import build
    from test_graph_b_snapshot import prepare
    from test_jurisprudence_candidates import incoming
    from test_public_sources import source
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-declared-assembly-seed")
    lifetime = fresh_workspace(root)
    workspace = next(lifetime)
    current = prepare(workspace, incoming.__wrapped__(source.__wrapped__(root)), root)
    try:
        value = build(current, root)
    finally:
        discard_test_seed_logins(workspace[0].state.store)
        lifetime.close()
        workspace[0].state.store.engine.dispose()
        for client in (*current["evidence"][1:], current["signed"][2]):
            client.close()
    return root, value


@pytest.fixture(scope="session")
def synthetic_analysis_workbench_seed(tmp_path_factory):
    """Invented document/fact bytes before any analysis or review is performed."""
    from test_analysis_workbench import fresh_workbench
    root = tmp_path_factory.mktemp("TEST-ONLY-analysis-baseline")
    lifetime = fresh_workbench(root)
    value = next(lifetime)
    discard_test_seed_logins(value[0].state.store)
    lifetime.close()
    value[0].state.store.engine.dispose()
    return root, value


@pytest.fixture(scope="session")
def synthetic_unsigned_graph_b_seed(tmp_path_factory):
    """Complete invented equivalence, no signed Graph B review or verdict."""
    from test_decision_equivalence import prepare as prepare_equivalence
    from test_graph_b_review import prepare
    from test_jurisprudence_candidates import incoming
    from test_public_sources import source
    from test_workspace import fresh_workspace
    root = tmp_path_factory.mktemp('TEST-ONLY-unsigned-graph-b-context')
    lifetime = fresh_workspace(root)
    workspace = next(lifetime)
    evidence = prepare_equivalence(workspace[0], workspace[1], *incoming.__wrapped__(source.__wrapped__(root)))
    try:
        signed_inputs = prepare(evidence, root)
    finally:
        discard_test_seed_logins(workspace[0].state.store)
        lifetime.close()
        workspace[0].state.store.engine.dispose()
    for client in (*evidence[1:], signed_inputs[2]):
        client.close()
    return root, evidence, signed_inputs


@pytest.fixture
def unsigned_graph_b_context(tmp_path, synthetic_unsigned_graph_b_seed):
    from graph_b_test_seeds import cloned_unsigned_graph_b
    with cloned_unsigned_graph_b(synthetic_unsigned_graph_b_seed, tmp_path) as value:
        yield value
