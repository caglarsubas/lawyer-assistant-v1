"""Bounded, evidence-bearing graph reads. This module never publishes graph data.

Only ontology schema is available without Fuseki. Synthetic competency fixtures are
never read here. Legal relationships are reified assertions, not unrestricted paths.
"""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlparse

import httpx
from rdflib import Literal, URIRef

from .graph_release import RuntimeGraphRelease

NS = "https://lawyer-assistant.local/ontology/"
PREFIXES = f"""PREFIX la: <{NS}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
TOOL_NAMES = frozenset(
    {
        "locate_issues",
        "resolve_authority",
        "trace_norm_history",
        "trace_institution_history",
        "trace_decision_history",
        "expand_authorities",
        "get_evidence",
        "get_coverage",
    }
)
GRAPH_DATASETS = {"structure": "structural", "jurisprudence": "jurisprudence"}
HISTORY_RELATIONS = {
    "trace_norm_history": {
        "versionOf",
        "hasInstrumentVersion",
        "hasProvisionVersion",
        "amends",
        "createsVersion",
        "repeals",
        "annuls",
        "replaces",
        "renumbers",
        "splitsFrom",
        "mergesFrom",
        "hasTransitionRule",
        "predecessorOf",
    },
    "trace_institution_history": {
        "establishedBy",
        "renamedFrom",
        "successorOf",
        "abolishedBy",
        "organizationalPartOf",
        "heldBy",
        "authorizedBy",
        "coversSubject",
        "coversTerritory",
        "routeFrom",
        "routeTo",
    },
    "trace_decision_history": {
        "reviewsDecision",
        "affirms",
        "setsAside",
        "remands",
        "decidedIn",
        "issuedAtStage",
        "hasDecisionVersion",
        "hasOpinion",
        "distinguishes",
        "declinesToApply",
        "cites",
    },
}


class GraphBackendError(RuntimeError):
    """A configured graph backend could not provide a verified read result."""


def _date(value: str | None, field: str = "as_of") -> str:
    if value is None or value == "":
        return datetime.now(timezone.utc).date().isoformat()
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid date") from exc


def _datetime(value: str | None) -> str:
    if value is None or value == "":
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str):
        raise ValueError("known_at must be an ISO datetime with a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError as exc:
        raise ValueError("known_at must be an ISO datetime with a timezone") from exc


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _text(value: Any, field: str = "query", maximum: int = 300) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"{field} must be text of at most {maximum} characters without control characters")
    return unicodedata.normalize("NFC", value.strip())


def _iri(value: Any, field: str = "entity_id") -> str:
    value = _text(value, field, 500)
    if not re.fullmatch(r"(?:https?://|urn:)[^\s<>\"{}|\\^`]+", value):
        raise ValueError(f"{field} must be an absolute HTTP(S) or URN identifier")
    return URIRef(value).n3()


def _search_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("I", "ı").replace("İ", "i").casefold()


def valid_on(valid_from: str | None, valid_to: str | None, as_of: str, status: str = "known", *,
             end_status: str | None = None, checked_through: str | None = None, history=False) -> bool:
    """Date filter only; reviewed evidence is checked by SPARQL and signed RDF."""
    if status != "known" or not valid_from:
        return False
    try:
        point, start = date.fromisoformat(as_of), date.fromisoformat(valid_from)
        if valid_to is not None:
            end = date.fromisoformat(valid_to)
            return (end_status in {None, 'closed'} and checked_through is None and start < end
                    and start <= point and (history or point < end))
        if end_status != 'open_ended' or checked_through is None:
            return False
        through = date.fromisoformat(checked_through)
        return start <= through and start <= point and (history or point <= through)
    except (TypeError, ValueError):
        return False


class GraphService:
    def __init__(
        self, ontology_dir: Path, fuseki_url: str = "", fuseki_user: str = "", fuseki_password: str = "",
        release_root: Path | None = None, trusted_review_key: Path | None = None,
        authorization_guard=None,
    ):
        self.release = RuntimeGraphRelease(release_root, trusted_review_key, authorization_guard)
        self.ontology_dir = (self.release.info["bundle_path"] / "ontology"
                             if self.release.info else Path(ontology_dir).resolve())
        raw = (self.release.catalog_bytes if self.release.info
               else (self.ontology_dir / "catalog.json").read_bytes())
        self._catalog = json.loads(raw)
        self.ontology_version = self._catalog["version"]
        self._catalog_digest = hashlib.sha256(raw).hexdigest()
        self.fuseki_url = fuseki_url.rstrip("/")
        if self.fuseki_url:
            parsed = urlparse(self.fuseki_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
                or parsed.port == 0
                or parsed.username
                or parsed.password
                or "\\" in fuseki_url
                or fuseki_url != fuseki_url.strip()
                or any(ord(c) < 32 or ord(c) == 127 for c in fuseki_url)
            ):
                raise ValueError("Fuseki requires a private server origin and separate credentials")
            if parsed.hostname != "fuseki":
                try:
                    address = ipaddress.ip_address(parsed.hostname)
                    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
                    permitted = address.is_loopback or any(
                        address in ipaddress.ip_network(n) for n in networks
                    )
                    if (
                        not permitted
                        or address.is_link_local
                        or address.is_unspecified
                        or address.is_multicast
                        or (address.is_reserved and not address.is_loopback)
                        or getattr(address, "ipv4_mapped", None) is not None
                        or "%" in parsed.hostname
                    ):
                        raise ValueError("Nonprivate graph address")
                except ValueError as exc:
                    raise ValueError(
                        "Fuseki requires its isolated service hostname or a vetted private IP"
                    ) from exc
        self._auth = (fuseki_user, fuseki_password) if fuseki_user else None
        self.mode = "fuseki" if self.fuseki_url else "catalog"
        self._relations = {r["id"]: r for r in self._catalog["relations"]}

    @property
    def legal_review_status(self):
        return ('legally_reviewed' if self.release.status()['status'] == 'verified'
                else self._catalog['review_status'])

    def catalog(self) -> dict[str, Any]:
        result = copy.deepcopy(self._catalog)
        result["review_status"] = self.legal_review_status
        result["mode"] = self.mode
        result["coverage"] = self.coverage()
        return result

    def coverage(self) -> dict[str, Any]:
        release_status = self.release.status()
        reviewed_release = release_status["status"] == "verified"
        result: dict[str, Any] = {
            "mode": self.mode,
            "serving_release": release_status,
            "ontology": {
                "version": self.ontology_version,
                "review_status": 'legally_reviewed' if reviewed_release else self._catalog['review_status'],
                "classes": len(self._catalog["classes"]),
                "relations": len(self._catalog["relations"]),
                "domains": len(self._catalog["domains"]),
                "reviewed_classes": len(self._catalog["classes"]) if reviewed_release else 0,
                "reviewed_relations": len(self._catalog["relations"]) if reviewed_release else 0,
                "national_legal_review_complete": reviewed_release,
            },
            "institutional": {"status": "not_loaded", "observed_count": 0, "total_expected": None},
            "corpus": {
                "status": "not_loaded",
                "source_artifacts": 0,
                "total_expected": None,
                "historical_scope": copy.deepcopy(self._catalog["historical_scope"]),
                "coverage_by_source_institution_domain_period": [],
            },
            "assertion": {
                "status": "not_loaded",
                "observed_count": 0,
                "legally_reviewed": 0,
                "eligible_for_legal_claims": False,
            },
            "limitations": [
                "Signed national review is recorded for this exact release; legal correctness and applicability require lawyer review."
                if reviewed_release else "National schema is an UNREVIEWED engineering baseline, not an approved statement of Turkish law.",
                "Historical population is staged from 1920, with earlier continuity/applicable-law predecessors only.",
                "Schema breadth, source counts and graph density do not establish corpus completeness.",
            ],
        }
        if not self.fuseki_url:
            result["limitations"].append(
                "Catalog mode has no imported legal corpus or institutional registry; fixtures are excluded."
            )
            return result
        totals = {"institutions": 0, "artifacts": 0, "assertions": 0, "reviewed": 0}
        try:
            for family in GRAPH_DATASETS:
                selectors = {
                    "institutions": '?item rdf:type/rdfs:subClassOf* la:Institution ; la:scope "public" ; la:synthetic false .',
                    "artifacts": '?item a la:SourceArtifact ; la:scope "public" ; la:synthetic false .',
                    "assertions": '?item a la:Assertion ; la:scope "public" ; la:synthetic false .',
                    "reviewed": '?item a la:Assertion ; la:scope "public" ; la:synthetic false ; la:claimStatus "legally_reviewed" ; la:reviewer ?reviewer ; la:reviewedAt ?reviewedAt .',
                }
                subqueries = " ".join(f"{{ SELECT (COUNT(DISTINCT ?item) AS ?{name}) WHERE {{ {selector} }} }}"
                                     for name, selector in selectors.items())
                bindings = self._select(family, PREFIXES + "SELECT ?institutions ?artifacts ?assertions ?reviewed WHERE { " + subqueries + " }")
                if len(bindings) != 1:
                    raise GraphBackendError("Missing coverage result")
                for name in totals:
                    value = int(bindings[0].get(name, {}).get("value", "-1"))
                    if value < 0:
                        raise GraphBackendError("Invalid coverage count")
                    totals[name] += value
            result["institutional"].update(status="observed", observed_count=totals["institutions"])
            result["corpus"].update(status="observed", source_artifacts=totals["artifacts"])
            result["assertion"].update(
                status="observed", observed_count=totals["assertions"], legally_reviewed=totals["reviewed"]
            )
            result["limitations"].append(
                "Counts are dataset-local observations summed across two graphs; shared representations may overlap. Source completeness remains unknown."
            )
        except (GraphBackendError, ValueError, IndexError):
            result["mode"] = "unavailable"
            if reviewed_release:
                result["serving_release"].update(
                    status="unavailable",
                    reason="İmzalı dosyalar doğrulandı; çalışan graf hizmetinin sürümü veya yanıtı doğrulanamadı.",
                )
            for key in ("institutional", "corpus", "assertion"):
                result[key]["status"] = "unavailable"
                for field in ("observed_count", "source_artifacts", "legally_reviewed"):
                    if field in result[key]:
                        result[key][field] = None
            result["limitations"].append(
                "Configured Fuseki coverage could not be read. No historical coverage is inferred."
            )
        return result

    def explore(
        self, query: str = "", graph: str = "structure", as_of: str | None = None, limit: int = 30
    ) -> dict[str, Any]:
        query = _text(query)
        self._graph(graph)
        point = _date(as_of)
        limit = _integer(limit, "limit", 1, 100)
        if not self.fuseki_url:
            return self._catalog_explore(query, graph, point, limit)
        return self._read(graph=graph, query=query, as_of=point, limit=limit)

    def tool(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise ValueError("Unknown graph tool; raw query execution is not available")
        if not isinstance(payload, dict):
            raise ValueError("Tool payload must be an object")
        allowed = {"as_of", "known_at", "limit", "graph"}
        if name == "get_coverage":
            allowed = set()
        elif name == "locate_issues":
            allowed |= {"query"}
        elif name == "resolve_authority":
            allowed |= {"identifier"}
        elif name == "get_evidence":
            allowed |= {"assertion_id"}
        else:
            allowed |= {"entity_id", "hops"}
        extra = set(payload) - allowed
        if extra:
            raise ValueError("Unsupported tool payload keys: " + ", ".join(sorted(extra)))
        if name == "get_coverage":
            return {"tool": name, **self.coverage()}
        graph = payload.get("graph", "jurisprudence" if name == "trace_decision_history" else "structure")
        self._graph(graph)
        point = _date(payload.get("as_of"))
        known_at = _datetime(payload.get("known_at"))
        limit = _integer(payload.get("limit", 30), "limit", 1, 100)
        hops = _integer(payload.get("hops", 1), "hops", 1, 2)
        query, identifier, entity_id, assertion_id = "", None, None, None
        if name == "locate_issues":
            query = _text(payload.get("query", ""))
            if not query:
                raise ValueError("locate_issues requires query")
        elif name == "resolve_authority":
            identifier = _text(payload.get("identifier", ""), "identifier", 500)
            if not identifier:
                raise ValueError("resolve_authority requires identifier")
        elif name == "get_evidence":
            assertion_id = _iri(payload.get("assertion_id", ""), "assertion_id")
        else:
            entity_id = _iri(payload.get("entity_id", ""))
        if not self.fuseki_url:
            if name == "locate_issues":
                result = self._catalog_explore(query, graph, point, limit)
            else:
                result = self._empty(
                    graph,
                    point,
                    known_at,
                    "catalog",
                    "No legal corpus is loaded; this tool cannot establish legal or historical facts from the schema.",
                )
            result["tool"] = name
            return result
        result = self._read(
            graph,
            query,
            point,
            limit,
            known_at=known_at,
            identifier=identifier,
            entity_id=entity_id,
            assertion_id=assertion_id,
            hops=hops,
            relations=HISTORY_RELATIONS.get(name),
            history=name in HISTORY_RELATIONS or name == "get_evidence",
        )
        result["tool"] = name
        return result

    def _graph(self, graph: str) -> None:
        if graph not in GRAPH_DATASETS:
            raise ValueError("graph must be structure or jurisprudence")

    def release_status(self) -> dict:
        return self.release.status()

    def release_pin(self) -> dict:
        status = self.release.status()
        result = {"status": status["status"], "release_id": status.get("release_id")}
        if status["status"] == "verified":
            result.update(serving_sha256=self.release.info["serving_sha256"],
                          activation_sequence=self.release.info["pointer"]["sequence"])
        return result

    def _snapshot(self, graph: str, as_of: str, known_at: str, mode: str) -> dict[str, Any]:
        serving = self.release.status()
        result = {
            "mode": mode,
            "graph": graph,
            "ontology_version": self.ontology_version,
            "ontology_sha256": self._catalog_digest,
            "as_of": as_of,
            "known_at": known_at,
            "legal_review_status": self.legal_review_status,
            "serving_release": serving,
            "reproducibility": "catalog_digest" if mode == "catalog" else "unverified_backend",
        }
        if serving["status"] == "verified" and mode == "fuseki":
            result.update(release_id=serving["release_id"], ontology_sha256=serving["ontology_sha256"],
                          serving_sha256=self.release.info["serving_sha256"], reproducibility="immutable_verified_release")
        return result

    def _empty(self, graph: str, as_of: str, known_at: str, mode: str, limitation: str) -> dict[str, Any]:
        return {
            "nodes": [],
            "edges": [],
            "mode": mode,
            "limitations": [limitation],
            "snapshot": self._snapshot(graph, as_of, known_at, mode),
        }

    def _catalog_explore(self, query: str, graph: str, as_of: str, limit: int) -> dict[str, Any]:
        key = _search_key(query)
        candidates = [c for c in self._catalog["classes"] if c["graph"] in {graph, "shared"}]
        if graph == "structure":
            candidates += [
                {**d, "module": "domains", "graph": "structure", "parent": d["broader"]}
                for d in self._catalog["domains"]
            ]
        selected = [
            c
            for c in candidates
            if not key
            or key in _search_key(" ".join(str(c.get(f, "")) for f in ("id", "label", "label_en", "module")))
        ][:limit]
        ids = {c["id"] for c in selected}
        result = self._empty(
            graph,
            as_of,
            _datetime(None),
            "catalog",
            "Ontology schema only: no real institutional or historical records are loaded, and synthetic fixtures are never exposed.",
        )
        result["nodes"] = [
            {
                "id": c["id"],
                "label": c["label"],
                "type": "domain_concept" if c["module"] == "domains" else "ontology_class",
                "graph": graph,
                "review_status": "unreviewed",
                "module": c["module"],
                "legal_usable": False,
            }
            for c in selected
        ]
        result["edges"] = [
            {
                "id": c["id"] + "/schema-parent",
                "source": c["id"],
                "target": c["parent"],
                "label": "Üst kavrama bağlıdır" if c["module"] == "domains" else "Alt türüdür",
                "predicate_code": "broader_concept" if c["module"] == "domains" else "subclass_of",
                "status": "unreviewed_schema",
                "legal_usable": False,
            }
            for c in selected
            if c.get("parent") in ids
        ]
        result["limitations"].append(
            "An as-of date does not turn ontology categories into historical legal evidence."
        )
        return result

    def _select(self, graph: str, sparql: str) -> list[dict[str, Any]]:
        self._graph(graph)
        try:
            info = self.release.require_current()
            metadata = self._transport_select(graph, self.release.metadata_query(graph))
            if not self.release.metadata_matches(graph, metadata):
                raise ValueError("Runtime release does not match the verified publication")
            # Every query, including counts and nested paths, sees only this exact
            # family graph. The default dataset and other releases are excluded.
            scoped = sparql.replace("WHERE", f"FROM <{info['graphs'][graph]['graph_iri']}> WHERE", 1)
            rows = self._transport_select(graph, scoped)
            self.release.require_current()
            return rows
        except ValueError as exc:
            raise GraphBackendError("Verified graph release is unavailable or changed") from exc

    def _transport_select(self, graph: str, sparql: str) -> list[dict[str, Any]]:
        self._graph(graph)
        endpoint = f"{self.fuseki_url}/{GRAPH_DATASETS[graph]}/query"
        deadline = monotonic() + 15.0
        try:
            with httpx.Client(
                timeout=httpx.Timeout(10.0, connect=3.0),
                follow_redirects=False,
                trust_env=False,
                auth=self._auth,
            ) as client:
                with client.stream(
                    "POST",
                    endpoint,
                    data={"query": sparql},
                    headers={"Accept": "application/sparql-results+json", "Accept-Encoding": "identity"},
                ) as response:
                    response.raise_for_status()
                    if response.headers.get("content-encoding", "").strip().lower() not in {"", "identity"}:
                        raise GraphBackendError("Compressed graph responses are not accepted")
                    chunks, received = [], 0
                    for chunk in response.iter_bytes():
                        if monotonic() > deadline:
                            raise GraphBackendError("Graph response exceeds the total streaming deadline")
                        received += len(chunk)
                        if received > 2_000_000:
                            raise GraphBackendError("Graph response exceeds the bounded read budget")
                        chunks.append(chunk)
            bindings = json.loads(b"".join(chunks))["results"]["bindings"]
            if (
                not isinstance(bindings, list)
                or len(bindings) > 400
                or not all(isinstance(row, dict) for row in bindings)
            ):
                raise GraphBackendError("Invalid or excessive graph results")
            return bindings
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise GraphBackendError("Configured graph backend unavailable or returned invalid data") from exc

    def _assertion_pattern(self, suffix: str, as_of: str, known_at: str, history: bool = False) -> str:
        a, s, p, o = ("?" + name + suffix for name in ("a", "s", "p", "o"))
        point = Literal(as_of, datatype=URIRef("http://www.w3.org/2001/XMLSchema#date")).n3()
        known = Literal(known_at, datatype=URIRef("http://www.w3.org/2001/XMLSchema#dateTime")).n3()
        def temporal_filter(node, start, end, end_status, through, *, reviewed=False):
            expiry = 'true' if history else f"{point} < {end}"
            horizon = 'true' if history else f"{point} <= {through}"
            review = (f'?claimStatus{suffix} = "legally_reviewed" && '
                      f'?reviewedAt{suffix} >= xsd:dateTime(CONCAT(STR({through}), "T00:00:00Z")) && '
                      f'?recordedAt{suffix} >= xsd:dateTime(CONCAT(STR({through}), "T00:00:00Z"))'
                      if reviewed else 'true')
            return f"""
            OPTIONAL {{ {node} la:validityEndStatus {end_status} }}
            OPTIONAL {{ {node} la:validityCheckedThrough {through} }}
            FILTER NOT EXISTS {{
              VALUES ?temporalProperty{suffix} {{ la:validFrom la:validTo la:validityEndStatus la:validityCheckedThrough }}
              {node} ?temporalProperty{suffix} ?firstTemporal{suffix}, ?secondTemporal{suffix} .
              FILTER (?firstTemporal{suffix} != ?secondTemporal{suffix})
            }}
            FILTER ((BOUND({end}) && (!BOUND({end_status}) || {end_status} = "closed")
                     && !BOUND({through}) && {start} < {end} && ({expiry})
                     && NOT EXISTS {{ {node} la:validityEvidence ?closedProof{suffix} }})
              || (!BOUND({end}) && {end_status} = "open_ended" && BOUND({through})
                  && {start} <= {through} && ({horizon}) && ({review})
                  && EXISTS {{ {node} la:validityEvidence ?someProof{suffix} }}
                  && NOT EXISTS {{
                    {node} la:validityEvidence ?validityProof{suffix} .
                    FILTER NOT EXISTS {{
                      ?validityProof{suffix} a la:EvidencePassage ; la:scope "public" ;
                        la:artifact ?proofArtifact{suffix} ; la:textRepresentation ?proofRepresentation{suffix} .
                      ?proofArtifact{suffix} la:scope "public" ; la:synthetic false ; la:rightsStatus "permitted" .
                      ?proofRepresentation{suffix} a la:SourceRepresentation ; la:scope "public" ;
                        la:synthetic false ; la:artifact ?proofArtifact{suffix} .
                    }}
                  }}))
            """
        expiry = temporal_filter(a, f'?validFrom{suffix}', f'?validTo{suffix}',
                                 f'?validityEndStatus{suffix}', f'?validityCheckedThrough{suffix}', reviewed=True)
        version_expiry = temporal_filter(o, f'?targetVersionFrom{suffix}', f'?targetVersionTo{suffix}',
                                         f'?targetEndStatus{suffix}', f'?targetCheckedThrough{suffix}')
        # An open target needs its own reviewed version-link assertion. A version
        # label or a citation's dates cannot independently establish its horizon.
        version_basis = f"""
            FILTER (!BOUND(?targetEndStatus{suffix}) || ?targetEndStatus{suffix} != "open_ended" || EXISTS {{
              ?versionBasis{suffix} a la:Assertion ; la:subject ?basisProvision{suffix} ;
                la:predicate la:hasProvisionVersion ; la:object {o} ; la:scope "public" ;
                la:synthetic false ; la:claimStatus "legally_reviewed" ; la:validityStatus "known" ;
                la:validityEndStatus "open_ended" ; la:validFrom ?targetVersionFrom{suffix} ;
                la:validityCheckedThrough ?targetCheckedThrough{suffix} ;
                la:reviewer ?basisReviewer{suffix} ; la:reviewedAt ?basisReviewed{suffix} ;
                la:recordedAt ?basisRecorded{suffix} ; la:evidence ?basisEvidence{suffix} .
              {o} la:versionOf ?basisProvision{suffix} ; la:versionResolution "resolved" .
              ?basisProvision{suffix} a la:Provision ; la:scope "public" .
              ?basisEvidence{suffix} a la:EvidencePassage ; la:scope "public" ;
                la:artifact ?basisArtifact{suffix} ; la:textRepresentation ?basisRepresentation{suffix} .
              ?basisArtifact{suffix} a la:SourceArtifact ; la:scope "public" ; la:synthetic false ; la:rightsStatus "permitted" .
              ?basisRepresentation{suffix} a la:SourceRepresentation ; la:scope "public" ;
                la:synthetic false ; la:artifact ?basisArtifact{suffix} .
              FILTER (STRLEN(STR(?basisReviewer{suffix})) > 0 && ?basisReviewed{suffix} <= {known}
                && ?basisRecorded{suffix} <= {known}
                && ?basisReviewed{suffix} >= xsd:dateTime(CONCAT(STR(?targetCheckedThrough{suffix}), "T00:00:00Z"))
                && ?basisRecorded{suffix} >= xsd:dateTime(CONCAT(STR(?targetCheckedThrough{suffix}), "T00:00:00Z")))
              FILTER NOT EXISTS {{ ?versionBasis{suffix} la:supersededAt ?basisSuperseded{suffix} . FILTER (?basisSuperseded{suffix} <= {known}) }}
              FILTER NOT EXISTS {{
                VALUES ?basisProperty{suffix} {{ la:validFrom la:validTo la:validityEndStatus la:validityCheckedThrough la:validityEvidence }}
                {{ ?versionBasis{suffix} ?basisProperty{suffix} ?basisValue{suffix} .
                   FILTER NOT EXISTS {{ {o} ?basisProperty{suffix} ?basisValue{suffix} }} }}
                UNION {{ {o} ?basisProperty{suffix} ?basisValue{suffix} .
                   FILTER NOT EXISTS {{ ?versionBasis{suffix} ?basisProperty{suffix} ?basisValue{suffix} }} }}
              }}
            }})
            FILTER ({p} != la:hasProvisionVersion ||
              ((!BOUND(?validityEndStatus{suffix}) || ?validityEndStatus{suffix} != "open_ended") &&
               (!BOUND(?targetEndStatus{suffix}) || ?targetEndStatus{suffix} != "open_ended")) || NOT EXISTS {{
                VALUES ?linkProperty{suffix} {{ la:validFrom la:validTo la:validityEndStatus la:validityCheckedThrough la:validityEvidence }}
                {{ {a} ?linkProperty{suffix} ?linkValue{suffix} . FILTER NOT EXISTS {{ {o} ?linkProperty{suffix} ?linkValue{suffix} }} }}
                UNION {{ {o} ?linkProperty{suffix} ?linkValue{suffix} . FILTER NOT EXISTS {{ {a} ?linkProperty{suffix} ?linkValue{suffix} }} }}
              }})
        """
        allowed_predicates = ", ".join(
            URIRef(ident).n3()
            for ident, metadata in self._relations.items()
            if metadata["module"] != "private_overlay"
        )
        return f"""
        FILTER ({p} IN ({allowed_predicates}))
        {a} a la:Assertion ; la:subject {s} ; la:predicate {p} ; la:object {o} ;
            la:scope "public" ; la:synthetic false ; la:claimStatus ?claimStatus{suffix} ;
            la:validityStatus "known" ; la:validFrom ?validFrom{suffix} ; la:recordedAt ?recordedAt{suffix} ;
            la:evidence ?evidence{suffix} .
        {s} la:scope "public" . {o} la:scope "public" .
        ?evidence{suffix} la:artifact ?artifact{suffix} ; la:scope "public" ; la:locator ?locator{suffix} ; la:quotedText ?quotedText{suffix} .
        ?evidence{suffix} la:textRepresentation ?representation{suffix} ; la:startOffset ?startOffset{suffix} ; la:endOffset ?endOffset{suffix} .
        ?representation{suffix} a la:SourceRepresentation ; la:artifact ?artifact{suffix} ; la:scope "public" ;
            la:synthetic false ; la:contentHash ?textHash{suffix} ; la:locatorMapHash ?locatorMapHash{suffix} .
        ?artifact{suffix} la:scope "public" ; la:synthetic false ; la:rightsStatus "permitted" ; la:contentHash ?contentHash{suffix} .
        OPTIONAL {{ {a} la:validTo ?validTo{suffix} }}
        OPTIONAL {{ {a} la:supersededAt ?supersededAt{suffix} }}
        OPTIONAL {{ {a} la:reviewer ?reviewer{suffix} ; la:reviewedAt ?reviewedAt{suffix} }}
        FILTER (?validFrom{suffix} <= {point})
        {expiry}
        FILTER (?recordedAt{suffix} <= {known} && (!BOUND(?supersededAt{suffix}) || {known} < ?supersededAt{suffix}))
        FILTER (?claimStatus{suffix} IN ("unreviewed", "source_verified", "legally_reviewed", "contested", "superseded"))
        FILTER (?claimStatus{suffix} != "legally_reviewed" || (BOUND(?reviewer{suffix}) && STRLEN(STR(?reviewer{suffix})) > 0 && ?reviewedAt{suffix} <= {known}))
        FILTER NOT EXISTS {{ {a} la:scope "private" }}
        FILTER NOT EXISTS {{ ?evidence{suffix} la:scope "private" }}
        FILTER NOT EXISTS {{ ?artifact{suffix} la:scope "private" }}
        FILTER NOT EXISTS {{ ?representation{suffix} la:scope "private" }}
        FILTER NOT EXISTS {{ {a} la:synthetic true }}
        FILTER NOT EXISTS {{ ?artifact{suffix} la:synthetic true }}
        FILTER NOT EXISTS {{ ?representation{suffix} la:synthetic true }}
        FILTER NOT EXISTS {{ {s} la:scope "private" }}
        FILTER NOT EXISTS {{ {o} la:scope "private" }}
        FILTER NOT EXISTS {{ {s} la:synthetic true }}
        FILTER NOT EXISTS {{ {o} la:synthetic true }}
        FILTER ({p} NOT IN (la:applies, la:interprets) || EXISTS {{
            {o} a la:ProvisionVersion ; la:versionResolution "resolved" ; la:versionOf ?resolvedProvision{suffix} .
        }})
        FILTER ({p} NOT IN (la:hasProvisionVersion, la:applies, la:interprets) || EXISTS {{
            {o} a la:ProvisionVersion ; la:validFrom ?targetVersionFrom{suffix} .
            OPTIONAL {{ {o} la:validTo ?targetVersionTo{suffix} }}
            FILTER (?targetVersionFrom{suffix} <= {point})
            {version_expiry}
            {version_basis}
        }})
        """

    def _build_query(
        self,
        *,
        graph: str,
        query: str,
        as_of: str,
        limit: int,
        known_at: str,
        identifier: str | None = None,
        entity_id: str | None = None,
        assertion_id: str | None = None,
        hops: int = 1,
        relations: set[str] | None = None,
        history: bool = False,
    ) -> str:
        # Every returned relationship has its own evidence and both temporal filters.
        filters = [f"FILTER EXISTS {{ ?a la:graphFamily {Literal(graph).n3()} }}"]
        if query:
            literal = Literal(query).n3()
            filters.append(
                f"FILTER(CONTAINS(LCASE(STR(?sLabel)), LCASE({literal})) || CONTAINS(LCASE(STR(?oLabel)), LCASE({literal})))"
            )
        if identifier:
            exact = Literal(identifier).n3()
            filters.append(
                f"FILTER(STR(?s) = {exact} || STR(?o) = {exact} || ?sIdentifier = {exact} || ?oIdentifier = {exact})"
            )
        if assertion_id:
            filters.append(f"FILTER(?a = {assertion_id})")
        if relations:
            filters.append("VALUES ?p { " + " ".join("la:" + r for r in sorted(relations)) + " }")
        if entity_id:
            direct = f"(?s = {entity_id} || ?o = {entity_id})"
            if hops == 1:
                filters.append("FILTER" + direct)
            else:
                adjacent_relations = ""
                if relations:
                    adjacent_relations = (
                        "VALUES ?p2 { " + " ".join("la:" + r for r in sorted(relations)) + " }"
                    )
                filters.append(f"""FILTER ({direct} || EXISTS {{
                    {self._assertion_pattern("2", as_of, known_at, history)}
                    ?a2 la:graphFamily {Literal(graph).n3()} .
                    {adjacent_relations}
                    FILTER (?s2 = {entity_id} || ?o2 = {entity_id})
                    FILTER (?s = ?s2 || ?s = ?o2 || ?o = ?s2 || ?o = ?o2)
                }})""")
        return (
            PREFIXES
            + f"""
        SELECT DISTINCT ?a ?s ?p ?o ?sLabel ?oLabel ?sType ?oType ?claimStatus ?validFrom ?validTo
          ?validityEndStatus ?validityCheckedThrough
          ?recordedAt ?supersededAt ?evidence ?artifact ?locator ?quotedText ?contentHash ?reviewer ?reviewedAt
          ?sourceVersionResolution ?targetVersionResolution
          ?representation ?textHash ?locatorMapHash ?startOffset ?endOffset
        WHERE {{
          {self._assertion_pattern("", as_of, known_at, history)}
          OPTIONAL {{ ?s rdfs:label ?sLabel }} OPTIONAL {{ ?o rdfs:label ?oLabel }}
          OPTIONAL {{ ?s a ?sType }} OPTIONAL {{ ?o a ?oType }}
          OPTIONAL {{ ?s la:canonicalId ?sIdentifier }} OPTIONAL {{ ?o la:canonicalId ?oIdentifier }}
          OPTIONAL {{ ?s la:versionResolution ?sourceVersionResolution }}
          OPTIONAL {{ ?o la:versionResolution ?targetVersionResolution }}
          {" ".join(filters)}
        }} ORDER BY ?a ?evidence LIMIT {min(limit * 2, 200)}
        """
        )

    def _read(
        self,
        graph: str,
        query: str,
        as_of: str,
        limit: int,
        *,
        known_at: str | None = None,
        identifier: str | None = None,
        entity_id: str | None = None,
        assertion_id: str | None = None,
        hops: int = 1,
        relations: set[str] | None = None,
        history: bool = False,
    ) -> dict[str, Any]:
        known_at = known_at or _datetime(None)
        sparql = self._build_query(
            graph=graph,
            query=query,
            as_of=as_of,
            limit=limit,
            known_at=known_at,
            identifier=identifier,
            entity_id=entity_id,
            assertion_id=assertion_id,
            hops=hops,
            relations=relations,
            history=history,
        )
        try:
            rows = self._select(graph, sparql)
        except GraphBackendError:
            return self._empty(
                graph,
                as_of,
                known_at,
                "unavailable",
                "Configured Fuseki could not be read; no catalog or synthetic records have been substituted for legal evidence.",
            )
        result = self._empty(
            graph,
            as_of,
            known_at,
            "fuseki",
            "Graph relationships are evidence candidates; citation, applicability, binding effect and completeness are separate judgments.",
        )
        result["snapshot"]["temporal_mode"] = "history_inspection" if history else "as_of_candidates"
        result["snapshot"]["applicability"] = "not_established"
        nodes: dict[str, Any] = {}
        edges: dict[str, Any] = {}
        for raw in rows:
            row = {key: cell.get("value") for key, cell in raw.items() if isinstance(cell, dict)}
            if not all(
                row.get(k)
                for k in ("a", "s", "p", "o", "evidence", "artifact", "locator", "quotedText", "contentHash")
            ):
                continue
            if row["p"] not in self._relations:
                continue
            if self.release.info and not self.release.matches(
                graph, row, as_of=as_of, known_at=known_at, history=history,
                entity_id=entity_id, hops=hops, relations=relations,
                identifier=identifier, assertion_id=assertion_id, query=query,
            ):
                return self._empty(graph, as_of, known_at, "unavailable",
                                   "Runtime assertions do not match the independently verified source release.")
            if not valid_on(row.get("validFrom"), row.get("validTo"), as_of, history=history,
                            end_status=row.get("validityEndStatus"),
                            checked_through=row.get("validityCheckedThrough")):
                continue
            if (
                row["p"] in {NS + "applies", NS + "interprets"}
                and row.get("targetVersionResolution") != "resolved"
            ):
                continue
            if row["a"] not in edges and len(edges) >= limit:
                continue
            try:
                validity_evidence = (self.release.validity_evidence(graph, URIRef(row["a"]))
                                     if self.release.info else [])
            except (ValueError, TypeError):
                return self._empty(graph, as_of, known_at, "unavailable",
                                   "Reviewed validity evidence could not be verified within its bounded inspection budget.")
            status = row.get("claimStatus", "unreviewed")
            # Even signed, source-grounded publication does not assess a matter's
            # applicability, omitted issues or the correctness of a legal conclusion.
            eligible = False
            for prefix in ("s", "o"):
                ident = row[prefix]
                nodes.setdefault(
                    ident,
                    {
                        "id": ident,
                        "label": row.get(prefix + "Label") or ident.rsplit("/", 1)[-1],
                        "type": row.get(prefix + "Type", NS + "Entity"),
                        "graph": graph,
                        "review_status": status,
                        "legal_usable": eligible,
                    },
                )
            edge = edges.setdefault(
                row["a"],
                {
                    "id": row["a"],
                    "source": row["s"],
                    "target": row["o"],
                    "label": self._relations[row["p"]]["label"],
                    "predicate_code": self._relations[row["p"]]["predicate_code"],
                    "predicate": row["p"],
                    "status": status,
                    "evidence_id": row["evidence"],
                    "evidence": [],
                    "valid_from": row.get("validFrom"),
                    "valid_to": row.get("validTo"),
                    "validity_end_status": row.get("validityEndStatus") or ("closed" if row.get("validTo") else "unknown"),
                    "validity_checked_through": row.get("validityCheckedThrough"),
                    "validity_evidence": validity_evidence,
                    "temporal_mode": "history_inspection" if history else "as_of_candidates",
                    "recorded_at": row.get("recordedAt"),
                    "superseded_at": row.get("supersededAt"),
                    "requires_legal_review": self._relations[row["p"]]["requires_legal_review"],
                    "legal_usable": eligible,
                    "matter_applicability": "not_assessed",
                    # _select and the final check authorize the whole response;
                    # do not replay the private ledger for every individual edge.
                    "release_verified": self.release.info is not None,
                },
            )
            evidence = {
                "id": row["evidence"],
                "artifact_id": row["artifact"],
                "locator": row["locator"],
                "text": row["quotedText"],
                "sha256": row["contentHash"],
                "text_representation_id": row.get("representation"),
                "text_sha256": row.get("textHash"),
                "locator_map_sha256": row.get("locatorMapHash"),
                "start_offset": row.get("startOffset"),
                "end_offset": row.get("endOffset"),
                "grounding_status": "verified_release_quote" if self.release.info else "requires_verified_runtime_release",
            }
            if evidence not in edge["evidence"]:
                edge["evidence"].append(evidence)
        result["nodes"], result["edges"] = list(nodes.values()), list(edges.values())
        result["limitations"].extend(
            [
                "Unknown validity/version references are excluded from applicability answers, never resolved to the latest version.",
                "Open-ended validity is considered only through its evidenced review cutoff; a missing end date never establishes current force.",
                "Only public, nonsynthetic assertions with permitted source evidence are returned; missing results do not prove absence of authority.",
                "Exact extracted quote grounding and release integrity are distinct from OCR fidelity, legal correctness and matter applicability.",
            ]
        )
        if history:
            result["limitations"].append(
                "Historical evidence inspection may include expired intervals or elapsed review cutoffs; applicability at the requested date is not established."
            )
        if self.legal_review_status != "legally_reviewed":
            result["limitations"].append(
                "National ontology review is incomplete; no result is eligible as an approved legal conclusion."
            )
        if not edges:
            result["limitations"].append(
                "No qualifying evidenced assertions were found for these identifiers, dates and access conditions; version resolution may be unavailable."
            )
        if self.release.info:
            try:
                self.release.require_current()
            except ValueError:
                return self._empty(graph, as_of, known_at, "unavailable",
                                   "Current public release authorization changed; graph results were discarded.")
        return result
