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
