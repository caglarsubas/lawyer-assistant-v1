"""Explicit temporal states; absence of an end date never establishes open validity."""
from datetime import date, datetime, timezone

from rdflib import RDF, XSD, Literal, Namespace, URIRef

LA = Namespace("https://lawyer-assistant.local/ontology/")


def one(graph, node, predicate):
    values = set(graph.objects(node, predicate))
    if len(values) > 1:
        raise ValueError("Temporal property has conflicting values")
    return next(iter(values), None)


def day(value):
    if value is None:
        return None
    if not isinstance(value, Literal) or value.datatype != XSD.date:
        raise ValueError("Temporal date requires xsd:date")
    parsed = date.fromisoformat(str(value))
    if parsed.isoformat() != str(value):
        raise ValueError("Temporal date is not canonical")
    return parsed


def instant(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Temporal provenance requires a timezone")
    return parsed.astimezone(timezone.utc)


def public_evidence(graph, node):
    """Physical quote bytes are checked independently by the release validator."""
    if not isinstance(node, URIRef) or (node, RDF.type, LA.EvidencePassage) not in graph:
        return False
    try:
        artifact = one(graph, node, LA.artifact)
        representation = one(graph, node, LA.textRepresentation)
        if (not isinstance(artifact, URIRef) or not isinstance(representation, URIRef)
                or (artifact, RDF.type, LA.SourceArtifact) not in graph):
            return False
        return (one(graph, node, LA.scope) == Literal("public")
                and one(graph, artifact, LA.scope) == Literal("public")
                and one(graph, artifact, LA.synthetic) == Literal(False)
                and one(graph, artifact, LA.rightsStatus) == Literal("permitted")
                and one(graph, representation, LA.scope) == Literal("public")
                and one(graph, representation, LA.synthetic) == Literal(False)
                and one(graph, representation, LA.artifact) == artifact
                and (representation, RDF.type, LA.SourceRepresentation) in graph)
    except ValueError:
        return False


def interval_state(graph, node, *, evidence_graph=None):
    start, end = (day(one(graph, node, prop)) for prop in (LA.validFrom, LA.validTo))
    status_value = one(graph, node, LA.validityEndStatus)
    if status_value is not None and (not isinstance(status_value, Literal)
                                    or status_value.datatype not in {None, XSD.string}
                                    or status_value.language is not None):
        raise ValueError("Temporal end status requires an untagged string literal")
    status = str(status_value) if status_value is not None else None
    checked = day(one(graph, node, LA.validityCheckedThrough))
    evidence = frozenset(graph.objects(node, LA.validityEvidence))
    if status not in {None, "closed", "open_ended", "unknown"}:
        raise ValueError("Unsupported temporal end status")
    if end is not None:
        if status not in {None, "closed"} or checked is not None or evidence:
            raise ValueError("Closed interval cannot declare open-ended evidence")
        if start is not None and end <= start:
            raise ValueError("Temporal interval must be nonempty and ordered")
        kind = "closed" if start is not None else "unknown"
    elif status == "open_ended":
        if start is None or checked is None or checked < start or not evidence:
            raise ValueError("Open-ended validity needs a start, checked-through date and evidence")
        if any(not public_evidence(evidence_graph if evidence_graph is not None else graph, item) for item in evidence):
            raise ValueError("Open-ended validity evidence is not public source evidence")
        kind = "open_ended"
    else:
        if status == "closed" or checked is not None or evidence:
            raise ValueError("Unknown end cannot contain an open-ended declaration")
        kind = "unknown"
    return {"kind": kind, "start": start, "end": end, "checked_through": checked, "evidence": evidence}


def valid_at(state, as_of, *, history=False):
    if state["kind"] == "unknown" or state["start"] is None:
        return False
    if as_of is None:
        return True  # Discovery retains explicit state; it makes no as-of claim.
    point = date.fromisoformat(as_of)
    if point < state["start"]:
        return False
    if history:
        return True
    return (point < state["end"] if state["kind"] == "closed"
            else point <= state["checked_through"])


def intervals_overlap(left, right):
    if left["kind"] == "unknown" or right["kind"] == "unknown":
        return False
    # Checked-through is an observation cutoff, never an expiry boundary.
    return ((right["end"] is None or left["start"] < right["end"])
            and (left["end"] is None or right["start"] < left["end"]))


def reviewed_open(graph, assertion, state, *, known_at=None):
    if state["kind"] != "open_ended":
        return True
    if one(graph, assertion, LA.claimStatus) != Literal("legally_reviewed"):
        return False
    reviewer = one(graph, assertion, LA.reviewer)
    reviewed = instant(one(graph, assertion, LA.reviewedAt))
    return (reviewer is not None and bool(str(reviewer).strip())
            and state["checked_through"] <= reviewed.date()
            and (known_at is None or reviewed <= instant(known_at)))


def validate_graph_temporality(graph):
    """Structural validation, including conflicting unconditional provision versions."""
    states = {}
    for kind in (LA.Assertion, LA.ProvisionVersion):
        for node in set(graph.subjects(RDF.type, kind)):
            state = states.setdefault(node, interval_state(graph, node))
            if kind == LA.Assertion and state["kind"] == "open_ended":
                recorded = instant(one(graph, node, LA.recordedAt))
                if state["checked_through"] > recorded.date():
                    raise ValueError("Open-ended cutoff exceeds recorded provenance")
                if one(graph, node, LA.claimStatus) == Literal("legally_reviewed") and not reviewed_open(graph, node, state):
                    raise ValueError("Open-ended cutoff exceeds reviewed provenance")
    grouped = {}
    for node in set(graph.subjects(RDF.type, LA.ProvisionVersion)):
        provision = one(graph, node, LA.versionOf)
        state = states[node]
        for other in grouped.setdefault(provision, []):
            if intervals_overlap(state, states[other]):
                raise ValueError("Provision version validity intervals conflict")
        grouped[provision].append(node)
    for assertion in graph.subjects(LA.predicate, LA.hasProvisionVersion):
        version = one(graph, assertion, LA.object)
        if (assertion in states and version in states and (
                states[assertion]["kind"] == "open_ended" or states[version]["kind"] == "open_ended")
                and states[assertion] != states[version]):
            raise ValueError("Open-ended version and linking assertion must share dates and evidence")
    return states
