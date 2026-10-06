#!/usr/bin/env python3
"""Build an unselected, sealed lexical index from the currently authorized graph.

Run with the trusted publisher's private review configuration. Never generates
keys, changes approvals, selects an index, deletes data or invokes a provider.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.graph_release import RuntimeGraphRelease, _load_serving  # noqa: E402
from app.public_sources import PublicSourceStore  # noqa: E402
from app.release_authorization import ReleaseAuthorization  # noqa: E402
from app.release_snapshot import readonly_store  # noqa: E402
from app.search_index import IndexBuildError, build_index  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-release", required=True)
    args = parser.parse_args()
    try:
        settings = load_settings()
        if not settings.graph_release_dir or not settings.graph_trusted_review_key or not settings.opensearch_url:
            raise ValueError("Graph, independent trust and private search configuration are required")
        root, key = Path(settings.graph_release_dir), Path(settings.graph_trusted_review_key)
        with _load_serving().publication_lock(root, shared=True), readonly_store(settings) as store:
            authorization = ReleaseAuthorization(store, PublicSourceStore(settings.public_source_dir),
                settings.data_dir / "release-authorizations", key, ROOT / "ontology", settings.data_dir / "publication-epoch")
            release = RuntimeGraphRelease(root, key, authorization_guard=authorization.guard)
            result = build_index(release, settings.opensearch_url, args.expected_release)
        print(json.dumps(result, sort_keys=True))
        return 0
    except IndexBuildError as error:
        print(json.dumps({"status": "failed", "index": error.index, "stage": error.stage,
                          "selected_for_search": False,
                          "message": "An index may have been created or sealed. Reconcile its state; do not select or retry blindly."}), file=sys.stderr)
    except Exception:
        print(json.dumps({"status": "failed", "message": "Current graph, trust, configuration or private authorization unavailable."}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
