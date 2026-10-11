"""Revision-pinned confidential decision-review evidence; never publication input."""
import hashlib

from fastapi import HTTPException
from pydantic import Field, StrictInt
from sqlalchemy import select

from . import decision_mappings as mappings
from . import source_reviews as reviews
from .db import now
from .decision_mapping_models import DecisionMappingEvent
from .jurisprudence_candidates import encode
from .public_sources import PublicSourceStore
from .source_review_models import SourceReviewHead
from .source_reviews import StrictInput

MAX_DOSSIER_BYTES = 4 * 1024 * 1024


class DossierInput(StrictInput):
    expected_revision: StrictInt = Field(ge=0, le=1000)
    expected_source_review_revision: StrictInt = Field(ge=0, le=1000)


def handoff_checks(state):
    """Literal inconsistencies in reviewer-declared identities, not legal inference."""
    groups, unresolved = {}, []
    for item in state["items"]:
        resolution = item["resolution"]
        if item["status"] != "accepted" or item["stale"] or resolution is None:
            unresolved.append(item["id"])
            continue
        role = resolution["occurrence_role"]
        if (role == "unknown" or (role == "cited_authority" and not resolution["target_ref"])
                or (role == "cited_authority" and item["candidate"]["kind"].endswith("_reference")
                    and not resolution["target_version_ref"])):
            unresolved.append(item["id"])
        if role != "own_decision":
            continue
        reference = resolution["decision_ref"]
        group = groups.setdefault(reference, {})
        values = {"proceeding_ref": resolution["proceeding_ref"], "institution_ref": resolution["institution_ref"]}
        kind = item["candidate"]["kind"]
        if kind in {"application_number", "case_number", "decision_number"}:
            values[kind] = item["candidate"]["parsed_value"]
        if resolution["event_date"] is not None:
            values[resolution["event_role"] + "_date"] = resolution["event_date"]
        for field, value in values.items():
            group.setdefault(field, {}).setdefault(value, []).append(item["id"])
    conflicts = []
    for reference, fields in sorted(groups.items()):
        for field, values in sorted(fields.items()):
            if len(values) > 1:
                conflicts.append({"decision_ref": reference, "field": field,
                                  "alternatives": [{"value": value, "mapping_ids": sorted(ids)}
                                                   for value, ids in sorted(values.items())]})
    return {"source_reviews_ready": state["source_review_ready"],
            "all_current_reviews_accepted": bool(state["items"]) and all(
                item["status"] == "accepted" and not item["stale"] for item in state["items"]),
            "has_reviewed_self_identity": bool(groups), "unresolved_mapping_ids": sorted(unresolved),
            "identity_conflicts": conflicts, "comparison_basis": "literal_reviewer_declared_references_only",
            "independent_review_ready": state["handoff_ready"] and bool(groups) and not unresolved and not conflicts,
            "canonical_identity_resolved": False, "legal_effect_verified": False, "publication_eligible": False}


def build_dossier(request, source_id, body, user):
    package = reviews._package(request, source_id, user)
    store = request.app.state.store
    with store.session() as session:
        current = reviews._lock_identity(session, request, user)
        source_review = mappings._source_review(store, session, package, current.firm_id, lock=True)
        head = mappings._head(session, current.firm_id, source_id)
        revision = head.revision if head else 0
        if (body.expected_revision != revision
                or body.expected_source_review_revision != source_review["revision"]):
            raise HTTPException(409, "Dossier için güncel karar ve kaynak inceleme revizyonlarını açın")
        if not source_review["export_allowed"]:
            raise HTTPException(409, "Dayanak metnini içeren dosya için kabul edilmiş açık dışa aktarma izni gerekir")
        source_head = session.scalar(select(SourceReviewHead).where(
            SourceReviewHead.firm_id == current.firm_id, SourceReviewHead.source_id == source_id))
        source_projection = reviews._projection(store, source_head, package)
        source_history = reviews._history(store, session, source_head)
        projection, _ = mappings._projection(store, session, head, package)
        # Display truncation must never silently truncate a review handoff.
        history, lookup = [], {}
        if head:
            rows = session.scalars(select(DecisionMappingEvent).where(
                DecisionMappingEvent.head_id == head.id, DecisionMappingEvent.firm_id == current.firm_id,
            ).order_by(DecisionMappingEvent.revision.desc()).limit(mappings.MAX_EVENTS + 1))
            history = [mappings._verified_event(mappings._event_header(store, row, head, package), package, lookup)
                       for row in rows]
        if [event["revision"] for event in history] != list(range(revision, 0, -1)):
            raise mappings._error()
        state = mappings._state(package, revision, source_review, projection, history)
        passage_ids = {event["snapshot"]["passage_id"] for event in history}
        passage_ids.update(passage_id for event in source_history for passage_id in event["passage_ids"])
        from .provision_candidates import span_details
        for event in history:
            resolution = event["snapshot"]["resolution"]
            if resolution is not None:
                passage_ids.update(span_details(package, resolution["start"], resolution["end"])["passage_ids"])
        passages = [{"id": passage.id, "start": passage.start, "end": passage.end,
                     "text": package.text[passage.start:passage.end], "sha256": passage.text_sha256,
                     "locator": passage.locator} for passage in package.locators.passages if passage.id in passage_ids]
        result = {"schema_version": "decision-review-dossier-v1", "confidentiality": "firm_confidential",
                  "firm_id": current.firm_id, "exported_by": {"id": current.id, "name": current.name},
                  "exported_at": now(), "signed": False, "publication_eligible": False,
                  "source_binding": reviews._binding(package), "mappings": state,
                  "source_review": {"revision": source_review["revision"],
                                    "assigned_to": source_projection["assigned_to"],
                                    "assessments": source_projection["assessments"],
                                    "history": source_history, "history_complete": True},
                  "history_complete": True, "supporting_passages": passages,
                  "handoff_checks": handoff_checks(state),
                  "limitations": ["Büroya özel inceleme dosyası; metin ve incelemeci bilgileri gizlidir.",
                                   "İçerik özeti imza veya yayımlama yetkisi değildir; bağımsız inceleme gerekir.",
                                   "Referans karşılaştırması harfiyendir; eşdeğer kimlikler veya tüm hukuki çelişkiler çözümlenmez."]}
        encoded = encode(result)
        if len(encoded) > MAX_DOSSIER_BYTES:
            raise HTTPException(409, "Tam inceleme dosyası boyut sınırını aşıyor; kısmi dosya verilmedi")
        # A changed retained artifact withholds the complete response.
        refreshed = PublicSourceStore(request.app.state.settings.public_source_dir).verified_package(source_id)
        if refreshed.artifacts != package.artifacts:
            raise HTTPException(409, "Kaynak dosyası dışa aktarma sırasında değişti")
        if mappings._source_review(store, session, package, current.firm_id, lock=True) != source_review:
            raise HTTPException(409, "Kaynak incelemesi dışa aktarma sırasında değişti")
        reviews._lock_identity(session, request, user)
        return {"evidence_json": encoded.decode("utf-8"), "evidence_sha256": hashlib.sha256(encoded).hexdigest()}
