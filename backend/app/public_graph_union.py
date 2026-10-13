"""Deterministic declared public union; structural checks confer no approval."""
from pathlib import Path
from tempfile import TemporaryDirectory

from rdflib import BNode, Graph, Literal, Namespace, URIRef

from .graph_release import _load_serving
from .release_authorization import _packet_tools
from .release_preparation import canonical, digest

MAX_BYTES = 64 * 1024 * 1024
ASM = Namespace("urn:la:declared-assembly:")


def compile_union(prepared, *, base, trusted_key, ontology_root):
    """Preserve every captured triple, manifestation and physical evidence byte.

    Caller has already matched EVERY component to current permission/original
    source state. This pure compiler is not an authorization boundary.
    """
    if type(prepared) is not dict or not 2 <= len(prepared) <= 9:
        raise ValueError("A complete bounded component inventory is required")
    tools, serving = _packet_tools(), _load_serving()
    captured = {}
    for ident, path in sorted(prepared.items()):
        info = serving.validate_prepared(Path(path), trusted_key)
        files = {name: tools.read_file(Path(path) / name, tools.MAX_FILE) for name in serving._files(Path(path))}
        if serving.validate_prepared(Path(path), trusted_key) != info:
            raise ValueError("Component changed during capture")
        captured[ident] = (info, files)
    return compile_captured_union(captured, base=base, ontology_root=ontology_root)


def compile_captured_union(captured, *, base, ontology_root):
    """Trusted internal compiler of per-operation independently verified bytes.

    This is NEVER a signature/permission verifier. Only the guarded assembler
    supplies captures, after exact component/source/grant matching; no API or
    agent accepts captures from a caller. No validation survives the operation.
    """
    if type(captured) is not dict or not 2 <= len(captured) <= 9:
        raise ValueError("A complete bounded component inventory is required")
    tools, serving = _packet_tools(), _load_serving()
    release = serving._release
    ontology_sha = release.ontology_digest(ontology_root)
    graphs = {family: Graph() for family in release.FAMILIES}
    definitions, evidence, members, total = {}, {}, [], 0
    for ident, (info, files) in sorted(captured.items()):
        if type(ident) is not str or not tools.HASH.fullmatch(ident):
            raise ValueError("Invalid component identity")
        if info["release_id"] != ident or info["ontology_sha256"] != ontology_sha:
            raise ValueError("Component identity or ontology differs")
        manifest_raw = files["bundle/manifest.json"]
        if digest(manifest_raw) != ident:
            raise ValueError("Component manifest changed")
        manifest = tools.parse_json(manifest_raw)
        own, hashes = {}, {}
        for family in graphs:
            raw = files["bundle/inputs/" + family + ".ttl"]
            total += len(raw)
            if total > MAX_BYTES or digest(raw) != manifest["input_graphs_sha256"][family]:
                raise ValueError("Component bytes changed or exceed budget")
            hashes[family] = digest(raw)
            graph = Graph().parse(data=raw, format="turtle", publicID=(info["bundle_path"] / "inputs" / (family + ".ttl")).absolute().as_uri())
            for triple in graph:
                if any(isinstance(term, BNode) or isinstance(term, URIRef) and
                       not str(term).startswith(("urn:", "http:", "https:")) for term in triple):
                    raise ValueError("Absolute stable public identifiers are required")
                own.setdefault(triple[0], set()).add(triple)
            graphs[family] += graph
        for subject, triples in own.items():
            if subject in definitions and definitions[subject] != triples:
                raise ValueError("Shared identity definitions conflict; explicit review is required")
            definitions[subject] = triples
        for name, raw in sorted(files.items()):
            if not name.startswith("bundle/evidence/"):
                continue
            fingerprint = digest(raw)
            if name != "bundle/evidence/" + fingerprint + ".bin" or fingerprint in evidence and evidence[fingerprint] != raw:
                raise ValueError("Physical evidence identity differs")
            if fingerprint not in evidence:
                total += len(raw)
                if total > MAX_BYTES:
                    raise ValueError("Union exceeds budget")
            evidence[fingerprint] = raw
        members.append({"release_id": ident, "serving_sha256": info["serving_sha256"],
                        "input_graphs_sha256": hashes})
    inventory = {"schema_version": "declared-public-graph-inventory-v1", "ontology_sha256": ontology_sha,
                 "components": members, "retained_base": base, "coverage_scope": "declared_components_only"}
    inventory_hash = digest(canonical(inventory))
    # Membership is INSIDE the final graph hashes signed by the final reviewer.
    # It cannot be removed/edited as an unattested sidecar.
    node = URIRef(str(ASM) + inventory_hash)
    graphs["structure"].add((node, ASM.inventorySha256, Literal(inventory_hash)))
    graphs["structure"].add((node, ASM.inventoryJson, Literal(canonical(inventory).decode("utf-8"))))
    # Internal structural/temporal checks only. No approval is returned or stored.
    checked = release.check_data(graphs, Path(ontology_root), {"verified": True})
    if set(evidence) != release.required_physical_hashes(checked):
        raise ValueError("Union contains missing or unused physical evidence")
    with TemporaryDirectory(prefix="legal-union-grounding-") as scratch:
        physical = {}
        for key, raw in evidence.items():
            physical[key] = Path(scratch) / (key + ".bin")
            physical[key].write_bytes(raw)
        release.check_quote_grounding(checked, physical)
    files = {"inputs/" + family + ".ttl": ("\n".join(sorted(
        line for line in graph.serialize(format="nt").splitlines() if line.strip())) + "\n").encode("utf-8")
        for family, graph in graphs.items()}
    files.update({"evidence/" + key + ".bin": raw for key, raw in sorted(evidence.items())})
    files["assembly-inputs.json"] = canonical(inventory)
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("Union exceeds output budget")
    return files, inventory
