"""Offline R01 inspection; declarations never grant review or execution authority."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .analysis_contracts import AnalysisContract, ScenarioContract, summarize_analysis, summarize_scenario
from .qualification_catalog import AssetCatalog, SourceCatalog, summarize_catalogs
from .qualification_evidence import read_exact_directory
from .research_qualification import ResearchDossier, summarize_research_dossier

MAX_COMPONENT_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 40
MAX_JSON_NODES = 250_000
COMPONENTS = {
    "source-catalog.json": SourceCatalog,
    "asset-catalog.json": AssetCatalog,
    "analysis-fixture.json": AnalysisContract,
    "scenario-fixture.json": ScenarioContract,
    "research-dossier.json": ResearchDossier,
}


class QualificationError(ValueError):
    """Fixed diagnostic code, without input values or filesystem details."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise QualificationError("duplicate_json_field")
        result[key] = value
    return result


def _invalid_number(value):
    raise QualificationError("nonfinite_json_number")


def parse_component(raw: bytes):
    if len(raw) > MAX_COMPONENT_BYTES:
        raise QualificationError("component_size_exceeded")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid_number)
    pending = [(value, 0)]
    nodes = 1
    while pending:
        current, depth = pending.pop()
        if depth > MAX_DEPTH:
            raise QualificationError("component_depth_exceeded")
        if isinstance(current, float) and not math.isfinite(current):
            raise QualificationError("nonfinite_json_number")
        if isinstance(current, dict):
            nodes += len(current)
            if nodes > MAX_JSON_NODES:
                raise QualificationError("component_nodes_exceeded")
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            nodes += len(current)
            if nodes > MAX_JSON_NODES:
                raise QualificationError("component_nodes_exceeded")
            pending.extend((child, depth + 1) for child in current)
    return value


def read_components(directory: Path) -> dict[str, bytes]:
    """Require exactly five regular components through the shared no-follow capture."""
    return read_exact_directory(directory, dict.fromkeys(COMPONENTS, MAX_COMPONENT_BYTES),
                                MAX_COMPONENT_BYTES * len(COMPONENTS))


def inspect_components(raw: dict[str, bytes]) -> dict:
    if set(raw) != set(COMPONENTS):
        raise QualificationError("incomplete_component_inventory")
    records = {name: model.model_validate(parse_component(raw[name]))
               for name, model in COMPONENTS.items()}
    # Private work products belong to authorized matter storage, not the packet.
    for name in ("analysis-fixture.json", "scenario-fixture.json"):
        if records[name].data_classification != "synthetic_fixture":
            raise QualificationError("dossier_requires_synthetic_fixtures")
    inventory = {name: {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
                 for name, value in sorted(raw.items())}
    digest = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": "r01-inspection-v1",
        "structurally_valid": True,
        "purpose": "planning_and_contract_validation_only",
        "dossier_sha256": digest,
        "components": inventory,
        "catalogs": summarize_catalogs(records["source-catalog.json"], records["asset-catalog.json"]),
        "analysis_fixture": summarize_analysis(records["analysis-fixture.json"]),
        "scenario_fixture": summarize_scenario(records["scenario-fixture.json"]),
        "research": summarize_research_dossier(records["research-dossier.json"]),
        "r01_exit_gate": "independent_review_and_evidence_required",
        "production_qualified": False,
        "runtime_authorization": "none",
        "limitations": [
            "Declarations and hashes are not independently verified rights or legal review.",
            "Schema validation is not a PII detector, legal-fidelity assessment or dispatch approval.",
            "Synthetic fixtures do not establish legal accuracy or real review throughput.",
            "Recorded samples require independent evidence and representativeness checks.",
            "This command does not alter source registries, review ledgers, graphs or provider configuration.",
        ],
    }


def inspect_dossier(directory: Path) -> dict:
    return inspect_components(read_components(directory))


def contract_schemas() -> dict:
    return {
        "schema_version": "r01-schema-bundle-v1",
        "purpose": "planning_and_contract_validation_only",
        "runtime_authorization": "none",
        "validation_note": "JSON Schema is supplementary; check also runs Python cross-record validators.",
        "components": {name: model.model_json_schema() for name, model in COMPONENTS.items()},
    }
