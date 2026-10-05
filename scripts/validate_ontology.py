#!/usr/bin/env python3
"""Validate ontology/schema consistency and SYNTHETIC competency examples locally.

Requires backend rdflib and pyshacl dependencies. No network or production writes.
SHACL conformance never changes the mandatory UNREVIEWED legal-review status.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pyshacl import validate
from rdflib import OWL, RDF, RDFS, SKOS, Graph, Namespace, URIRef

ROOT = Path(__file__).resolve().parents[1]
LA = Namespace("https://lawyer-assistant.local/ontology/")


def load_ontology(directory: Path) -> Graph:
    graph = Graph()
    for path in sorted((directory / "modules").glob("*.ttl")):
        graph.parse(path, format="turtle")
    graph.parse(directory / "domains.ttl", format="turtle")
    return graph


def validate_catalog(directory: Path) -> dict:
    catalog = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    ontology = load_ontology(directory)
    classes = {str(s) for s in ontology.subjects(RDF.type, OWL.Class)}
    expected_classes = {c["id"] for c in catalog["classes"]}
    if classes != expected_classes:
        raise ValueError("Turtle classes and JSON catalog differ")
    if len(expected_classes) != len(catalog["classes"]):
        raise ValueError("Duplicate class identifier")
    expected_relations = {r["id"] for r in catalog["relations"]}
    if len(expected_relations) != len(catalog["relations"]):
        raise ValueError("Duplicate relation identifier")
    for relation in catalog["relations"]:
        uri = URIRef(relation["id"])
        if (uri, RDF.type, OWL.ObjectProperty) not in ontology:
            raise ValueError("Relation missing from Turtle: " + relation["id"])
        for predicate, key in ((RDFS.domain, "domain"), (RDFS.range, "range")):
            if relation[key] not in expected_classes or (uri, predicate, URIRef(relation[key])) not in ontology:
                raise ValueError("Invalid relation " + key + ": " + relation["id"])
    concepts = {str(s) for s in ontology.subjects(RDF.type, SKOS.Concept)}
    if concepts != {d["id"] for d in catalog["domains"]}:
        raise ValueError("SKOS and JSON domain catalogs differ")
    for domain in catalog["domains"]:
        if domain["broader"] and domain["broader"] not in concepts:
            raise ValueError("Dangling broader domain")
    fixture = Graph().parse(directory / "fixtures" / "competency.ttl", format="turtle")
    shapes = Graph().parse(directory / "shapes.ttl", format="turtle")
    conforms, _, report = validate(data_graph=fixture, shacl_graph=shapes,
                                    ont_graph=ontology, inference="rdfs", advanced=True)
    if not conforms:
        raise ValueError(str(report))
    # All bundled assertions must stay synthetic and cannot be presented as real law.
    from rdflib import Literal
    for assertion in fixture.subjects(RDF.type, LA.Assertion):
        if (assertion, LA.synthetic, Literal(True)) not in fixture:
            raise ValueError("Bundled fixture assertion lacks synthetic flag")
    return {"conforms": True, "ontology_version": catalog["version"], "review_status": catalog["review_status"],
            "classes": len(classes), "relations": len(expected_relations), "domains": len(concepts),
            "schema_triples": len(ontology), "synthetic_fixture_assertions": len(set(fixture.subjects(RDF.type, LA.Assertion))),
            "competency_questions": len(json.loads((directory / "fixtures" / "competency_questions.json").read_text())["cases"]),
            "historical_records_published": 0, "legal_review_performed": False}


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        commands = parser.add_subparsers(dest="command")
        create = commands.add_parser("create-bundle", help="Create a new immutable offline staging snapshot; never upload")
        fingerprint = commands.add_parser("fingerprint", help="Print exact input fingerprints for independent legal review")
        for command in (create, fingerprint):
            command.add_argument("--structure", type=Path, required=True)
            command.add_argument("--jurisprudence", type=Path, required=True)
        create.add_argument("--evidence-dir", type=Path, required=True)
        create.add_argument("--output", type=Path, required=True)
        create.add_argument("--review-attestation", type=Path)
        create.add_argument("--trusted-review-key", type=Path)
        check = commands.add_parser("validate-bundle", help="Verify manifest, physical evidence, SHACL and review signature")
        check.add_argument("bundle", type=Path)
        check.add_argument("--trusted-review-key", type=Path)
        args = parser.parse_args()
        if args.command:
            sys.path.insert(0, str(ROOT))
            from ontology.releases import create_bundle, file_hash, ontology_digest, validate_bundle
            if args.command == "create-bundle":
                result = create_bundle(ROOT / "ontology", {"structure": args.structure, "jurisprudence": args.jurisprudence},
                                       args.evidence_dir, args.output, args.review_attestation, args.trusted_review_key)
            elif args.command == "validate-bundle":
                result = validate_bundle(args.bundle, args.trusted_review_key)
            else:
                result = {"ontology_sha256": ontology_digest(ROOT / "ontology"),
                          "input_graphs_sha256": {"structure": file_hash(args.structure), "jurisprudence": file_hash(args.jurisprudence)}}
        else:
            result = validate_catalog(ROOT / "ontology")
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
