"""Deterministic review candidate conversion; this module never grants authority.

Outputs are private signing inputs. Independent public review, private audience
authorization and a live source-review gate are all required before publication.
"""

from datetime import date, datetime, timezone

from rdflib import RDF, XSD, Graph, Literal

from .release_preparation import LA, canonical, digest

TRANSFORMATION = "reviewed-provision-promotion-v1"


def promoted_graphs(files: dict[str, bytes], public_reviewer: str, reviewed_at: str) -> dict[str, bytes]:
    if (not isinstance(public_reviewer, str) or not public_reviewer.strip()
            or len(public_reviewer) > 160 or any(ord(c) < 32 for c in public_reviewer)):
        raise ValueError("Supply an intentional bounded public reviewer identity")
    timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
        raise ValueError("A nonfuture timezone-aware public review timestamp is required")
    output = {}
    marker_subjects = set()
    assertions = 0
    for family in ("structure", "jurisprudence"):
        raw = files.get(f"candidate/{family}.ttl")
        if not isinstance(raw, bytes) or not raw or len(raw) > 32 * 1024 * 1024:
            raise ValueError("Complete unblocked preparation graphs are required")
        graph = Graph().parse(data=raw, format="turtle")
        markers = list(graph.triples((None, LA.reviewPreparationOnly, None)))
        if len(markers) != 1 or markers[0][2] != Literal(True):
            raise ValueError("Only marked preparation graphs may be converted")
        marker_subjects.add(markers[0][0])
        graph.remove(markers[0])
        # The public review must occur on/after the independently checked UTC
        # day. Preserve the legal dates and horizon exactly; neither becomes a
        # repeal date or an assertion of perpetual validity during promotion.
        for cutoff in graph.objects(None, LA.validityCheckedThrough):
            if (not isinstance(cutoff, Literal) or cutoff.datatype != XSD.date
                    or date.fromisoformat(str(cutoff)).isoformat() != str(cutoff)
                    or date.fromisoformat(str(cutoff)) > timestamp.astimezone(timezone.utc).date()):
                raise ValueError("Public review must follow the open-ended validity checking date")
        for node in list(graph.subjects(RDF.type, LA.Assertion)):
            assertions += 1
            if (family != "structure" or set(graph.objects(node, LA.claimStatus)) != {Literal("unreviewed")}
                    or set(graph.objects(node, LA.graphFamily)) != {Literal(family)}
                    or set(graph.objects(node, LA.predicate)) not in
                    ({LA.containsProvision}, {LA.hasProvisionVersion})
                    or list(graph.objects(node, LA.reviewer)) or list(graph.objects(node, LA.reviewedAt))):
                raise ValueError("Unsupported provision review transformation")
            recorded = list(graph.objects(node, LA.recordedAt))
            if len(recorded) != 1:
                raise ValueError("Exact preparation provenance is required")
            prior_time = datetime.fromisoformat(str(recorded[0]).replace("Z", "+00:00"))
            if prior_time.tzinfo is None or prior_time > timestamp:
                raise ValueError("Public review must follow the prepared mapping review")
            # No private ledger timestamps are carried into a shared release.
            for predicate, value in ((LA.claimStatus, Literal("legally_reviewed")),
                                     (LA.reviewer, Literal(public_reviewer)),
                                     (LA.reviewedAt, Literal(reviewed_at, datatype=XSD.dateTime)),
                                     (LA.recordedAt, Literal(reviewed_at, datatype=XSD.dateTime))):
                graph.set((node, predicate, value))
        output[family] = ("\n".join(sorted(line for line in graph.serialize(format="nt").splitlines()
                                          if line.strip())) + "\n").encode()
    if len(marker_subjects) != 1 or not assertions:
        raise ValueError("A single-source provision preparation is required")
    return output


def signing_inputs(files, *, ontology_sha256, public_reviewer, reviewed_at):
    graphs = promoted_graphs(files, public_reviewer, reviewed_at)
    body = {"reviewer": public_reviewer, "reviewed_at": reviewed_at, "decision": "approve",
            "scope": "national_ontology_and_assertions", "ontology_sha256": ontology_sha256,
            "input_graphs_sha256": {family: digest(raw) for family, raw in graphs.items()}}
    result = {f"inputs/{family}.ttl": raw for family, raw in graphs.items()}
    for name in ("raw.bin", "text.txt", "locators.json"):
        raw = files[f"candidate/{name}"]
        result[f"evidence/{digest(raw)}.bin"] = raw
    result["public-review-body.json"] = canonical(body)
    result["NOTICE.json"] = canonical({"schema_version": TRANSFORMATION, "signed": False,
                                       "publication_eligible": False, "confidentiality": "firm_confidential",
                                       "purpose": "Independent review input; no publication authorization"})
    return result
