"""Portable TEST-ONLY release seed; every test owns independently verified files."""
import pytest


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
    from test_workspace import workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-authorized-set-seed")
    lifetime = workspace.__wrapped__(root)
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
    from test_workspace import workspace
    root = tmp_path_factory.mktemp("TEST-ONLY-authorized-seed")
    lifetime = workspace.__wrapped__(root)
    fixture_workspace = next(lifetime)
    try:
        seed = build_authorized(mapping.__wrapped__(fixture_workspace, source.__wrapped__(root)), root)
    finally:
        lifetime.close()
    return root, seed
