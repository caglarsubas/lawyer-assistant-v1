"""Start query-only Fuseki from a fully reverified immutable release."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SERVING_PATH = Path("/opt/ontology/serving.py")
if not SERVING_PATH.exists():
    SERVING_PATH = Path(__file__).resolve().parents[2] / "ontology" / "serving.py"
SPEC = importlib.util.spec_from_file_location("lawyer_serving", SERVING_PATH)
serving = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serving)
JAVA = ["java", "-Xms64m", "-Xmx512m", "-cp", "/opt/fuseki/fuseki-server.jar"]


def compile_dataset(receipt: dict, root: Path, work: Path, family: str) -> Path:
    dataset = work / ("structural" if family == "structure" else family)
    dataset.mkdir()
    source = root / "releases" / receipt["release_id"] / receipt["graphs"][family]["file"]
    private_source = work / f"{family}.nq"
    shutil.copyfile(source, private_source)
    if serving.file_hash(private_source) != receipt["graphs"][family]["sha256"]:
        raise ValueError("Serving payload changed after release validation")
    # The transactional basic loader is deliberate. No other process sees this
    # private temporary database until both families have passed verification.
    subprocess.run([*JAVA, "tdb2.tdbloader", "--loader=basic", f"--loc={dataset}", str(private_source)],
                   check=True, timeout=600, capture_output=True)
    query = work / f"verify-{family}.rq"
    iri = receipt["graphs"][family]["graph_iri"]
    meta = receipt["metadata_graph_iri"]
    query.write_text("SELECT ?g (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g")
    checked = subprocess.run([*JAVA, "tdb2.tdbquery", f"--loc={dataset}", f"--query={query}", "--results=JSON"],
                             check=True, timeout=60, capture_output=True)
    bindings = json.loads(checked.stdout)["results"]["bindings"]
    counts = {row["g"]["value"]: int(row["count"]["value"]) for row in bindings}
    expected = {meta: 5}
    if receipt["graphs"][family]["triple_count"]:
        expected[iri] = receipt["graphs"][family]["triple_count"]
    if counts != expected:
        raise ValueError("Compiled TDB2 graph inventory differs from verified release")
    return dataset


def configuration(datasets: dict[str, Path] | None) -> str:
    lines = ['@prefix fuseki: <http://jena.apache.org/fuseki#> .',
             '@prefix tdb2: <http://jena.apache.org/2016/tdb#> .',
             '@prefix ja: <http://jena.hpl.hp.com/2005/11/Assembler#> .',
             '[] a fuseki:Server ; fuseki:services ( <#structural> <#jurisprudence> ) .']
    for family in serving.FAMILIES:
        name = "structural" if family == "structure" else family
        lines.append(f'<#{name}> a fuseki:Service ; fuseki:name "{name}" ; '
                     f'fuseki:serviceQuery "query", "sparql" ; fuseki:dataset <#{name}-data> .')
        if datasets is None:
            lines.append(f'<#{name}-data> a ja:MemoryDataset .')
        else:
            path = str(datasets[family])
            if not path.startswith("/tmp/") or any(char in path for char in '\\"\n\r'):
                raise ValueError("Unsafe temporary database path")
            lines.append(f'<#{name}-data> a tdb2:DatasetTDB2 ; tdb2:location "{path}" ; '
                         'ja:context [ ja:cxtName "arq:queryTimeout" ; ja:cxtValue "10000,30000" ] .')
    return "\n".join(lines) + "\n"


def start() -> None:
    root = Path("/fuseki")
    key_value = os.environ.get("LA_GRAPH_TRUSTED_REVIEW_KEY", "").strip()
    key = Path(key_value) if key_value else None
    with serving.publication_lock(root, shared=True) as descriptor:
        # Keep the shared lock across exec for the entire JVM lifetime. The
        # volume is read-only; flock is advisory state on the existing inode.
        os.set_inheritable(descriptor, True)
        receipt = serving.load_active(root, key)
        work = Path(tempfile.mkdtemp(prefix="fuseki-serving-", dir="/tmp"))
        datasets = None
        if receipt is not None:
            datasets = {family: compile_dataset(receipt, root, work, family) for family in serving.FAMILIES}
            # Detect privileged out-of-band pointer changes before the JVM opens.
            if serving.read_pointer(root) != receipt["pointer"]:
                raise ValueError("Active pointer changed while compiling the serving release")
            print(json.dumps({"event": "verified_release_loaded", "release_id": receipt["release_id"]}), flush=True)
        else:
            print(json.dumps({"event": "no_active_release", "legal_records_served": 0}), flush=True)
        config = work / "config.ttl"
        config.write_text(configuration(datasets))
        os.execvp("java", [*JAVA, "org.apache.jena.fuseki.main.cmds.FusekiMainCmd",
                          f"--config={config}", "--port=3030"])


if __name__ == "__main__":
    try:
        start()
    except Exception as exc:
        # Never fall back to old mutable databases, catalog data, or a different
        # release after integrity, trust, lock, or compilation failure.
        print("Fuseki serving release startup failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
