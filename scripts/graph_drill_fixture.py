"""TEST ONLY: invented RDF and ephemeral trust inside the disposable graph drill.

No application settings, legal source, provider or private authorization ledger is
loaded. The explicit synthetic guard qualifies filesystem/runtime mechanics only.
Never use these keys, bundles or this guard for a real publication.
"""

import base64
import importlib.util
import json
import os
import shutil
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from urllib.request import Request, urlopen

MARKER = "lawyer-graph-drill-v1"
ROOT = Path(__file__).resolve().parents[1]
VOLUME = Path("/fuseki")
WORK = Path("/drill")
NODES = 128
REVIEWER = "TEST ONLY - invented graph; no legal or rights review"


def require_drill():
    if os.environ.get("LA_GRAPH_DRILL") != MARKER:
        raise ValueError("This probe is restricted to the disposable graph drill")


def engine():
    spec = importlib.util.spec_from_file_location("graph_drill_serving", ROOT / "ontology/serving.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state():
    value = json.loads((WORK / "fixture.json").read_bytes())
    if value["marker"] != MARKER or set(value["releases"]) != {"a", "b", "c"}:
        raise ValueError("Missing disposable fixture identity")
    return value


@contextmanager
def synthetic_guard(info, action):
    require_drill()
    allowed = {entry["release_id"] for entry in state()["releases"].values()}
    if (action not in {"install", "activate", "rollback"} or info["release_id"] not in allowed
            or info["review"]["verified"] is not True or info["review"]["reviewer"] != REVIEWER):
        raise ValueError("Only this drill's invented signed releases are permitted")
    yield


def bootstrap():
    # The generated project owns these two new named volumes. Refuse existing
    # content before any chmod/chown; no arbitrary paths or bind mounts accepted.
    if os.geteuid() != 0 or any(list(path.iterdir()) for path in (VOLUME, WORK)):
        raise ValueError("Bootstrap requires two empty disposable volumes")
    for path in (VOLUME, WORK):
        path.chmod(0o755)
        os.chown(path, 10002, 10002)
    return {"initialized_empty_volumes": True}


def seed(serving):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if list(WORK.iterdir()) or list(VOLUME.iterdir()):
        raise ValueError("Seed requires empty disposable volumes")
    release = serving._release
    key = Ed25519PrivateKey.generate()  # Private key exists only in this process.
    public = WORK / "TEST-ONLY-public.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo))
    result = {"marker": MARKER, "nodes_per_family_per_release": NODES, "releases": {}}
    for variant in ("a", "b", "c"):
        directory = WORK / variant
        directory.mkdir()
        inputs = {}
        for family in serving.FAMILIES:
            path = directory / f"{family}.ttl"
            path.write_text("\n".join(
                f'<urn:test-only:{family}:{variant}:{number}> '
                f'<urn:test-only:variant> "{variant}" ; <urn:test-only:ordinal> {number} ; '
                f'<urn:test-only:link> <urn:test-only:{family}:{variant}:{(number + 1) % NODES}> .'
                for number in range(NODES)) + "\n")
            inputs[family] = path
        evidence = directory / "evidence"
        evidence.mkdir()
        body = {"reviewer": REVIEWER, "reviewed_at": "2026-01-01T00:00:00Z",
                "decision": "approve", "scope": "national_ontology_and_assertions",
                "ontology_sha256": release.ontology_digest(ROOT / "ontology"),
                "input_graphs_sha256": {name: release.file_hash(path) for name, path in inputs.items()}}
        attestation = directory / "TEST-ONLY-review.json"
        attestation.write_bytes(release.canonical({"algorithm": "Ed25519", "body": body,
            "signature": base64.b64encode(key.sign(release.canonical(body))).decode()}))
        bundle = directory / "bundle"
        release.create_bundle(ROOT / "ontology", inputs, evidence, bundle, attestation, public)
        receipt = serving.prepare(bundle, public, directory / "prepared")
        result["releases"][variant] = {name: receipt[name] for name in
                                      ("release_id", "serving_sha256", "graphs", "metadata_graph_iri")}
    (WORK / "fixture.json").write_bytes(release.canonical(result))
    serving.install(VOLUME, WORK / "a/prepared", public, authorization_guard=synthetic_guard)
    serving.activate(VOLUME, result["releases"]["a"]["release_id"], public, expected_current=None,
                     authorization_guard=synthetic_guard)
    return result


def select(family, query):
    name = "structural" if family == "structure" else family
    request = Request(f"http://fuseki:3030/{name}/query", data=query.encode(),
                      headers={"Content-Type": "application/sparql-query", "Accept": "application/sparql-results+json"})
    with urlopen(request, timeout=10) as response:
        return json.load(response)["results"]["bindings"]


def verify_served(variant):
    receipt = state()["releases"][variant]
    result = {}
    for family, graph in receipt["graphs"].items():
        rows = select(family, "SELECT ?g (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g")
        counts = {row["g"]["value"]: int(row["count"]["value"]) for row in rows}
        if counts != {graph["graph_iri"]: graph["triple_count"], receipt["metadata_graph_iri"]: 5}:
            raise ValueError("Runtime contains missing, extra or mixed-release named graphs")
        rows = select(family, "SELECT ?variant (COUNT(*) AS ?count) WHERE { GRAPH ?g { "
                             "?s <urn:test-only:variant> ?variant } } GROUP BY ?variant")
        # Shared resource context deliberately includes both family inputs.
        if rows != [{"variant": {"type": "literal", "value": variant},
                     "count": {"type": "literal", "datatype": "http://www.w3.org/2001/XMLSchema#integer", "value": str(NODES * 2)}}]:
            raise ValueError("Runtime synthetic sentinel content differs")
        result[family] = counts
    return {"release_id": receipt["release_id"], "named_graph_counts": result}


def overlap(serving):
    from load_metrics import distribution

    stop, ready = Event(), Event()
    samples, errors = [], []

    def reader():
        try:
            while not stop.is_set():
                started = time.monotonic()
                verify_served("a")
                samples.append((started, time.monotonic()))
                ready.set()
                stop.wait(.05)
        except Exception:
            errors.append("query_or_inventory_failure")
            ready.set()

    thread = Thread(target=reader, daemon=True)
    thread.start()
    pointer = serving.read_pointer(VOLUME)
    try:
        if not ready.wait(20) or errors:
            raise ValueError("Reader did not become ready")
        started = time.monotonic()
        serving.install(VOLUME, WORK / "b/prepared", WORK / "TEST-ONLY-public.pem", authorization_guard=synthetic_guard)
        finished = time.monotonic()
    finally:
        stop.set()
        thread.join(timeout=45)
    during = [(begin, end) for begin, end in samples if started <= begin <= end <= finished]
    if thread.is_alive() or errors or not during or serving.read_pointer(VOLUME) != pointer:
        raise ValueError("Import overlap did not preserve observed active queries/pointer")
    verify_served("a")
    return {"query_rounds_wholly_during_install": len(during), "install_seconds": round(finished - started, 3),
            "query_round_ms": distribution([round((end - begin) * 1000, 3) for begin, end in during]),
            "active_pointer_unchanged": True, "query_errors": len(errors)}


def transition(serving, action, current, sequence, target=None):
    releases = state()["releases"]
    kwargs = {"expected_current": releases[current]["release_id"], "expected_sequence": sequence,
              "authorization_guard": synthetic_guard}
    if action == "activate":
        return serving.activate(VOLUME, releases[target]["release_id"], WORK / "TEST-ONLY-public.pem", **kwargs)
    return serving.rollback(VOLUME, WORK / "TEST-ONLY-public.pem", **kwargs)


def denied(serving, operation, reason):
    before = serving.read_pointer(VOLUME)
    try:
        operation()
    except ValueError as error:
        if reason not in str(error):
            raise ValueError("Wrong denial reason") from None
    else:
        raise ValueError("Unsafe transition unexpectedly succeeded")
    if serving.read_pointer(VOLUME) != before:
        raise ValueError("Denied transition changed pointer")
    return {"denied": True, "pointer_unchanged": True}


def interrupt_install(serving):
    # Pause the actual install after its first copied file, before validation,
    # fsync and atomic publication. The host kills this one fixture container.
    def partial_copy(source, destination, **kwargs):
        if source != WORK / "c/prepared" or not destination.name.startswith(".installing-"):
            raise ValueError("Unexpected fault injection location")
        shutil.copyfile(source / "serving.json", destination / "serving.json")
        with (WORK / "interruption-ready").open("x") as stream:
            stream.write(destination.name)
            stream.flush()
            os.fsync(stream.fileno())
        while True:
            signal.pause()

    serving.shutil.copytree = partial_copy  # This short-lived fixture process only.
    serving.install(VOLUME, WORK / "c/prepared", WORK / "TEST-ONLY-public.pem", authorization_guard=synthetic_guard)
    raise ValueError("Fault injection unexpectedly returned")


def recover_install(serving):
    fixture = state()
    pointer = serving.read_pointer(VOLUME)
    expected = fixture["releases"]["a"]["release_id"]
    stages = list((VOLUME / "releases").glob(".installing-*"))
    target = VOLUME / "releases" / fixture["releases"]["c"]["release_id"]
    if pointer["release_id"] != expected or pointer["sequence"] != 1 or target.exists() or len(stages) != 1:
        raise ValueError("Interrupted installation changed publication state")
    if sorted(path.name for path in stages[0].iterdir()) != ["serving.json"]:
        raise ValueError("Expected incomplete stage was not retained")
    verify_served("a")
    installed = serving.install(VOLUME, WORK / "c/prepared", WORK / "TEST-ONLY-public.pem", authorization_guard=synthetic_guard)
    if serving.read_pointer(VOLUME) != pointer or not stages[0].exists():
        raise ValueError("Retry changed active pointer or discarded partial-stage evidence")
    return {"incomplete_stage_retained": True, "unpublished_after_sigkill": True,
            "retry_installed_release_id": installed["release_id"], "active_pointer_unchanged": True}


def corrupt(serving):
    pointer = serving.read_pointer(VOLUME)
    if pointer["release_id"] != state()["releases"]["b"]["release_id"] or pointer["sequence"] != 2:
        raise ValueError("Only stopped synthetic release B may be corrupted")
    path = VOLUME / "releases" / pointer["release_id"] / "structure.nq"
    path.chmod(0o644)
    with path.open("ab") as stream:
        stream.write(b'# TEST ONLY deliberate corruption\n')
    path.chmod(0o444)
    return {"synthetic_active_payload_corrupted": True}


def dispatch(action):
    require_drill()
    if action == "bootstrap":
        return bootstrap()
    serving = engine()
    if action == "seed":
        return seed(serving)
    if action in {"verify-a", "verify-b"}:
        return verify_served(action[-1])
    if action == "overlap":
        return overlap(serving)
    if action == "deny-live-activate":
        return denied(serving, lambda: transition(serving, "activate", "a", 1, "b"), "stop Fuseki")
    if action == "interrupted-install":
        return interrupt_install(serving)
    if action == "ready":
        return {"ready": (WORK / "interruption-ready").is_file()}
    if action == "recover-install":
        return recover_install(serving)
    if action == "activate-b":
        return transition(serving, "activate", "a", 1, "b")
    if action == "corrupt-b":
        return corrupt(serving)
    if action == "rollback-a":
        return transition(serving, "rollback", "b", 2)
    if action == "deny-stale-sequence":
        return denied(serving, lambda: transition(serving, "activate", "a", 1, "c"), "compare-and-swap")
    if action == "deny-corrupt-rollback":
        return denied(serving, lambda: transition(serving, "rollback", "a", 3), "signed source graph")
    raise ValueError("Unknown drill action")


if __name__ == "__main__":
    try:
        print(json.dumps(dispatch(sys.argv[1]), sort_keys=True))
    except Exception as error:
        # No tracebacks, credentials, host paths or source content in the report.
        print(json.dumps({"status": "failed", "failure_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
