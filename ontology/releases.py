"""Offline, content-addressed graph snapshots. Never uploads to a runtime database.

A valid signature establishes integrity and the operator's trusted reviewer identity,
not the truth of a legal conclusion or the reviewer's professional qualification.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from rdflib import RDF, BNode, Graph, Literal, Namespace
from rdflib.compare import isomorphic

LA = Namespace("https://lawyer-assistant.local/ontology/")
FAMILIES = ("structure", "jurisprudence")
_temporal_spec = importlib.util.spec_from_file_location("lawyer_release_temporal", Path(__file__).with_name("temporal.py"))
_temporal = importlib.util.module_from_spec(_temporal_spec)
_temporal_spec.loader.exec_module(_temporal)
_validation_spec = importlib.util.spec_from_file_location("lawyer_release_validation", Path(__file__).with_name("validation.py"))
_validation = importlib.util.module_from_spec(_validation_spec)
_validation_spec.loader.exec_module(_validation)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ontology_files(root: Path) -> list[Path]:
    return [root / "catalog.json", root / "domains.ttl", root / "shapes.ttl", *sorted((root / "modules").glob("*.ttl"))]


def ontology_digest(root: Path) -> str:
    files = {str(path.relative_to(root)): file_hash(path) for path in ontology_files(root)}
    return hashlib.sha256(canonical(files)).hexdigest()


def load_schema(root: Path) -> Graph:
    return _validation.load_ontology_graph([*sorted((root / "modules").glob("*.ttl")), root / "domains.ttl"])


def check_review_attestation(path: Path | None, trusted_key: Path | None, expected: dict) -> dict:
    if path is None:
        return {"verified": False, "reason": "No trusted legal-review attestation supplied"}
    if trusted_key is None:
        raise ValueError("An attestation requires an operator-supplied trusted Ed25519 public key")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    body = envelope.get("body", {})
    if envelope.get("algorithm") != "Ed25519" or not isinstance(body, dict):
        raise ValueError("Unsupported review attestation envelope")
    required = {"reviewer", "reviewed_at", "decision", "scope", "ontology_sha256", "input_graphs_sha256"}
    if set(body) != required or not isinstance(body["reviewer"], str) or not body["reviewer"].strip():
        raise ValueError("Review attestation fields or reviewer identity are incomplete")
    if body["decision"] != "approve" or body["scope"] != "national_ontology_and_assertions":
        raise ValueError("Review attestation does not approve the required ontology and assertion scope")
    reviewed_at = datetime.fromisoformat(body["reviewed_at"].replace("Z", "+00:00"))
    if reviewed_at.tzinfo is None or reviewed_at > datetime.now(timezone.utc):
        raise ValueError("Review timestamp requires a timezone and cannot be in the future")
    for field in ("ontology_sha256", "input_graphs_sha256"):
        if body[field] != expected[field]:
            raise ValueError("Review attestation is for different " + field)
    key = serialization.load_pem_public_key(trusted_key.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Trusted review key must be Ed25519")
    try:
        key.verify(base64.b64decode(envelope["signature"], validate=True), canonical(body))
    except (InvalidSignature, ValueError, KeyError) as exc:
        raise ValueError("Review attestation signature is invalid") from exc
    return {"verified": True, "reviewer": body["reviewer"], "reviewed_at": body["reviewed_at"],
            "key_sha256": hashlib.sha256(key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).hexdigest()}


def check_data(graphs: dict[str, Graph], ontology_root: Path, review: dict) -> dict:
    catalog = json.loads((ontology_root / "catalog.json").read_text())
    relations = {row["id"]: row for row in catalog["relations"]}
    private_classes = {row["id"] for row in catalog["classes"] if row["module"] == "private_overlay"}
    combined = Graph()
    partitions = {}
    for family, graph in graphs.items():
        combined += graph
        assertions = set(graph.subjects(RDF.type, LA.Assertion))
        proposed, reviewed = set(), set()
        for subject, predicate, obj in graph:
            if predicate == LA.reviewPreparationOnly:
                raise ValueError("Preparation-only graphs cannot enter a publication bundle")
            if any(isinstance(term, BNode) for term in (subject, predicate, obj)):
                raise ValueError("Release data requires stable identifiers; blank nodes cannot be partitioned safely")
            if str(subject).startswith("urn:synthetic:") or str(obj).startswith("urn:synthetic:"):
                raise ValueError("Synthetic fixture identifiers cannot enter an offline release")
            if predicate == LA.synthetic and obj == Literal(True):
                raise ValueError("Synthetic records cannot enter an offline release")
            if predicate == LA.scope and str(obj) == "private":
                raise ValueError("Private matter data cannot enter a public graph release")
            if predicate == LA.matterId or (predicate == RDF.type and str(obj) in private_classes):
                raise ValueError("Private matter identifiers/classes cannot enter a public graph release")
            if str(predicate) in relations and relations[str(predicate)]["module"] == "private_overlay":
                raise ValueError("Private matter relations cannot enter a public graph release")
            if str(predicate) in relations and relations[str(predicate)]["requires_legal_review"]:
                raise ValueError("Consequential legal relationships must be reified evidenced assertions")
        for assertion in assertions:
            if str(graph.value(assertion, LA.graphFamily)) != family:
                raise ValueError("Assertion graphFamily does not match its input file")
            if graph.value(assertion, LA.synthetic) != Literal(False):
                raise ValueError("Every release assertion requires explicit synthetic=false")
            if str(graph.value(assertion, LA.scope)) != "public":
                raise ValueError("Every release assertion requires public scope")
            relation = relations.get(str(graph.value(assertion, LA.predicate)))
            if relation is None:
                raise ValueError("Assertion predicate is not in the reviewed-contract relation catalog")
            status = str(graph.value(assertion, LA.claimStatus))
            if status == "legally_reviewed":
                reviewed.add(assertion)
            else:
                proposed.add(assertion)
            if relation["requires_legal_review"] and (status != "legally_reviewed" or not review["verified"]):
                raise ValueError("Consequential assertion needs an exact-snapshot trusted legal-review attestation")
            if status == "legally_reviewed" and not review["verified"]:
                raise ValueError("Claimed legal review requires a trusted review attestation")
        partitions[family] = {"proposed": sorted(str(a) for a in proposed), "reviewed": sorted(str(a) for a in reviewed)}
    for assertion in combined.subjects(RDF.type, LA.Assertion):
        for predicate in (LA.subject, LA.object):
            target = combined.value(assertion, predicate)
            if (target, LA.scope, Literal("public")) not in combined:
                raise ValueError("Public assertion endpoints require explicit public scope")
    for owner in set(combined.subjects(RDF.type, LA.Assertion)) | set(combined.subjects(RDF.type, LA.ProvisionVersion)):
        passages = set(combined.objects(owner, LA.validityEvidence))
        if (owner, RDF.type, LA.Assertion) in combined:
            passages.update(combined.objects(owner, LA.evidence))
        for passage in passages:
            artifact = combined.value(passage, LA.artifact)
            if (passage, LA.scope, Literal("public")) not in combined or (artifact, LA.scope, Literal("public")) not in combined:
                raise ValueError("Public evidence passage and source artifact require public scope")
            if (artifact, LA.synthetic, Literal(False)) not in combined or (artifact, LA.rightsStatus, Literal("permitted")) not in combined:
                raise ValueError("Public source evidence needs nonsynthetic status and permitted-use rights")
            representation = combined.value(passage, LA.textRepresentation)
            if (representation, LA.artifact, artifact) not in combined:
                raise ValueError("Passage text representation is not linked to the same raw source artifact")
            if (representation, LA.synthetic, Literal(False)) not in combined or (representation, LA.scope, Literal("public")) not in combined:
                raise ValueError("Text representations must be explicitly public and nonsynthetic")
    _temporal.validate_graph_temporality(combined)
    conforms, _, report = _validation.validate_graph(
        combined, _validation.load_ontology_graph([ontology_root / "shapes.ttl"]), load_schema(ontology_root))
    if not conforms:
        raise ValueError("Snapshot violates SHACL: " + str(report))
    return {"partitions": partitions, "assertions": sum(len(p[s]) for p in partitions.values() for s in ("proposed", "reviewed")),
            "artifacts": {str(a): str(combined.value(a, LA.contentHash)) for a in combined.subjects(RDF.type, LA.SourceArtifact)},
            "representations": {str(r): {"artifact_id": str(combined.value(r, LA.artifact)),
                                         "text_sha256": str(combined.value(r, LA.contentHash)),
                                         "locator_map_sha256": str(combined.value(r, LA.locatorMapHash)),
                                         "extractor_version": str(combined.value(r, LA.extractorVersion))}
                                for r in combined.subjects(RDF.type, LA.SourceRepresentation)},
            "passages": [{"id": str(p), "representation_id": str(combined.value(p, LA.textRepresentation)),
                          "locator": str(combined.value(p, LA.locator)), "text": str(combined.value(p, LA.quotedText)),
                          "start": int(combined.value(p, LA.startOffset)), "end": int(combined.value(p, LA.endOffset))}
                         for p in combined.subjects(RDF.type, LA.EvidencePassage)]}


def required_physical_hashes(checked: dict) -> set[str]:
    return set(checked["artifacts"].values()) | {
        representation[field] for representation in checked["representations"].values()
        for field in ("text_sha256", "locator_map_sha256")
    }


def check_quote_grounding(checked: dict, physical: dict[str, Path]) -> None:
    """Check exact Unicode code-point spans in hash-linked UTF-8 text and locator maps.

    This verifies what the extraction contains, not OCR fidelity to a scanned image.
    Source-to-extraction fidelity still needs parser QA and, where required, review.
    """
    decoded = {}
    for ident, representation in checked["representations"].items():
        text_path = physical[representation["text_sha256"]]
        map_path = physical[representation["locator_map_sha256"]]
        if text_path.stat().st_size > 64 * 1024 * 1024 or map_path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Extracted text or locator map exceeds the offline validation size limit")
        text = text_path.read_bytes().decode("utf-8")
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
        if (mapping.get("schema_version") != 1
                or mapping.get("artifact_sha256") != checked["artifacts"].get(representation["artifact_id"])
                or mapping.get("text_sha256") != representation["text_sha256"]
                or mapping.get("extractor_version") != representation["extractor_version"]
                or not isinstance(mapping.get("spans"), list)):
            raise ValueError("Locator map does not match its raw source, extracted text and extractor version")
        decoded[ident] = (text, mapping)
    for passage in checked["passages"]:
        if passage["representation_id"] not in decoded:
            raise ValueError("Passage has no validated text representation")
        text, mapping = decoded[passage["representation_id"]]
        start, end = passage["start"], passage["end"]
        if not 0 <= start < end <= len(text) or text[start:end] != passage["text"]:
            raise ValueError("Quoted source text does not exist at its declared exact offsets")
        if not any(isinstance(span, dict) and span.get("locator") == passage["locator"]
                   and type(span.get("start")) is int and type(span.get("end")) is int
                   and span["start"] <= start < end <= span["end"] <= len(text)
                   for span in mapping["spans"]):
            raise ValueError("Quoted source offsets do not fall within the declared locator")


def _safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unsafe snapshot-relative path")
    candidate = root / relative
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError("Snapshot path must name a regular internal file")
    return candidate


def create_bundle(ontology_root: Path, graph_paths: dict[str, Path], evidence_dir: Path, output: Path,
                  attestation: Path | None = None, trusted_key: Path | None = None) -> dict:
    if output.exists():
        raise ValueError("Snapshot output already exists; immutable bundles cannot be overwritten")
    if set(graph_paths) != set(FAMILIES):
        raise ValueError("Both structure and jurisprudence Turtle inputs are required")
    inputs = {family: file_hash(path) for family, path in graph_paths.items()}
    expected = {"ontology_sha256": ontology_digest(ontology_root), "input_graphs_sha256": inputs}
    review = check_review_attestation(attestation, trusted_key, expected)
    graphs = {family: Graph().parse(path, format="turtle") for family, path in graph_paths.items()}
    checked = check_data(graphs, ontology_root, review)
    physical = {}
    if not evidence_dir.is_dir():
        raise ValueError("Evidence directory is missing")
    for path in evidence_dir.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(evidence_dir.resolve()):
            physical.setdefault(file_hash(path), path)
    if any(digest not in physical for digest in required_physical_hashes(checked)):
        raise ValueError("A source artifact hash has no matching physical evidence file")
    check_quote_grounding(checked, physical)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for relative in ("inputs", "graphs", "evidence", "ontology/modules"):
            (output / relative).mkdir(parents=True, exist_ok=True)
        for source in ontology_files(ontology_root):
            destination = output / "ontology" / source.relative_to(ontology_root)
            shutil.copyfile(source, destination)
        for family, source in graph_paths.items():
            shutil.copyfile(source, output / "inputs" / f"{family}.ttl")
            graph = graphs[family]
            all_assertions = set(graph.subjects(RDF.type, LA.Assertion))
            for stage in ("proposed", "reviewed"):
                staged = Graph()
                chosen = set(checked["partitions"][family][stage])
                for subject, predicate, obj in graph:
                    if subject not in all_assertions or str(subject) in chosen:
                        staged.add((subject, predicate, obj))
                staged.serialize(output / "graphs" / f"{family}.{stage}.ttl", format="turtle")
        for digest in sorted(required_physical_hashes(checked)):
            shutil.copyfile(physical[digest], output / "evidence" / f"{digest}.bin")
        if attestation:
            shutil.copyfile(attestation, output / "review-attestation.json")
        manifest = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    **expected, "review": review, "partitions": checked["partitions"], "artifacts": checked["artifacts"],
                    "representations": checked["representations"],
                    "runtime_mutation": False, "legal_publication_eligible": review["verified"],
                    "release_status": "staged_reviewed_not_published" if review["verified"] else "staged_blocked_pending_national_legal_review",
                    "files": {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob("*")) if p.is_file()}}
        raw = canonical(manifest)
        (output / "manifest.json").write_bytes(raw)
        (output / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
        result = validate_bundle(output, trusted_key)
        for path in output.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
        return result
    except Exception:
        shutil.rmtree(output)
        raise


def validate_bundle(root: Path, trusted_key: Path | None = None) -> dict:
    raw = _safe_file(root, "manifest.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _safe_file(root, "manifest.sha256").read_text().strip():
        raise ValueError("Snapshot manifest hash mismatch")
    manifest = json.loads(raw)
    if manifest.get("format_version") != 1 or manifest.get("runtime_mutation") is not False:
        raise ValueError("Unsupported or unsafe snapshot manifest")
    expected_files = set(manifest["files"]) | {"manifest.json", "manifest.sha256"}
    actual_files = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    if actual_files != expected_files:
        raise ValueError("Snapshot has missing or undeclared files")
    for relative, expected_hash in manifest["files"].items():
        if file_hash(_safe_file(root, relative)) != expected_hash:
            raise ValueError("Snapshot content hash mismatch: " + relative)
    for family in FAMILIES:
        if file_hash(_safe_file(root, f"inputs/{family}.ttl")) != manifest["input_graphs_sha256"][family]:
            raise ValueError("Input graph fingerprint mismatch")
    if ontology_digest(root / "ontology") != manifest["ontology_sha256"]:
        raise ValueError("Ontology fingerprint mismatch")
    attestation = root / "review-attestation.json"
    review = check_review_attestation(attestation if attestation.exists() else None, trusted_key, manifest)
    if review != manifest["review"] or bool(review["verified"]) != manifest["legal_publication_eligible"]:
        raise ValueError("Review eligibility differs from independently verified attestation")
    expected_status = "staged_reviewed_not_published" if review["verified"] else "staged_blocked_pending_national_legal_review"
    if manifest.get("release_status") != expected_status:
        raise ValueError("Release status differs from the independently verified review gate")
    graphs = {family: Graph().parse(root / "inputs" / f"{family}.ttl", format="turtle") for family in FAMILIES}
    checked = check_data(graphs, root / "ontology", review)
    if checked["partitions"] != manifest["partitions"] or checked["artifacts"] != manifest["artifacts"]:
        raise ValueError("Snapshot assertion partitions or physical evidence mappings differ")
    if checked["representations"] != manifest["representations"]:
        raise ValueError("Snapshot extraction representations differ")
    for family in FAMILIES:
        merged = Graph()
        for stage in ("proposed", "reviewed"):
            part = Graph().parse(root / "graphs" / f"{family}.{stage}.ttl", format="turtle")
            actual_assertions = {str(a) for a in part.subjects(RDF.type, LA.Assertion)}
            if actual_assertions != set(checked["partitions"][family][stage]):
                raise ValueError("Proposed/reviewed assertion partition was changed")
            merged += part
        if not isomorphic(merged, graphs[family]):
            raise ValueError("Partitioned graphs are not equivalent to their source graph")
    physical = {}
    for evidence_hash in required_physical_hashes(checked):
        if file_hash(_safe_file(root, f"evidence/{evidence_hash}.bin")) != evidence_hash:
            raise ValueError("Physical evidence content does not match graph provenance")
        physical[evidence_hash] = _safe_file(root, f"evidence/{evidence_hash}.bin")
    check_quote_grounding(checked, physical)
    return {"valid": True, "bundle_sha256": digest, "assertions": checked["assertions"],
            "physical_evidence_files": len(required_physical_hashes(checked)), "review": review,
            "legal_publication_eligible": bool(review["verified"]), "release_status": manifest["release_status"],
            "runtime_mutation": False, "notice": "Hashes, exact extracted quote spans and locator mappings are verified. OCR fidelity, legal correctness and reviewer qualification are not certified by this tool."}
