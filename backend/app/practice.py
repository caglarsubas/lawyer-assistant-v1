"""Lawyer-authored preparation records; never generated facts or legal authorities."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from .auth import authenticate, require_child, require_matter
from .db import Audit, Record, digest, now, uid

Identifier = Annotated[str, Field(min_length=1, max_length=500)]
ShortText = Annotated[str, Field(min_length=1, max_length=2000)]
PracticeKind = Literal["scenarios", "contradictions", "arguments", "drafts"]
KINDS = {
    "scenarios": "practice_scenario",
    "contradictions": "practice_contradiction",
    "arguments": "practice_argument",
    "drafts": "practice_draft",
}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class VersionInput(StrictInput):
    expected_revision: int | None = Field(default=None, ge=1)
    change_note: str = Field(default="", max_length=2000)


class ScenarioInput(VersionInput):
    title: str = Field(min_length=1, max_length=200)
    assumptions: list[ShortText] = Field(min_length=1, max_length=20)
    fact_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=4000)
    status: Literal["active", "retired"] = "active"


class ContradictionInput(VersionInput):
    fact_ids: list[Identifier] = Field(min_length=2, max_length=2)
    status: Literal["open", "resolved", "dismissed"] = "open"
    reason: str = Field(min_length=3, max_length=4000)

    @model_validator(mode="after")
    def distinct_facts(self):
        if self.fact_ids[0] == self.fact_ids[1]:
            raise ValueError("Çelişki için iki farklı olgu seçin")
        return self


class AuthorityReference(StrictInput):
    product_id: Identifier
    passage_id: Identifier


class ArgumentInput(VersionInput):
    issue: str = Field(min_length=3, max_length=1000)
    position: Literal["supporting", "adverse", "alternative"]
    text: str = Field(min_length=3, max_length=8000)
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    authority_refs: list[AuthorityReference] = Field(default_factory=list, max_length=10)
    status: Literal["working", "ready_for_review", "withdrawn"] = "working"

    @model_validator(mode="after")
    def needs_reference(self):
        if not self.evidence_ids and not self.authority_refs:
            raise ValueError("Argüman için en az bir yerel belge veya kamu kaynak adayı bağlayın")
        return self


class DraftInput(VersionInput):
    title: str = Field(min_length=1, max_length=200)
    draft_kind: Literal["preparation", "review_note"] = "preparation"
    text: str = Field(min_length=1, max_length=30000)
    review_note: str = Field(default="", max_length=4000)
    status: Literal["working", "ready_for_review", "withdrawn"] = "working"


class PlaybookInput(VersionInput):
    title: str = Field(min_length=1, max_length=200)
    domain: Literal["contracts", "commercial", "employment", "general"]
    text: str = Field(min_length=1, max_length=20000)
    curation_status: Literal["draft", "curated", "retired"] = "draft"
    curation_note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def explicit_curation(self):
        if self.curation_status == "curated" and len(self.curation_note) < 3:
            raise ValueError("Kurum rehberinin kürasyonu için bir inceleme notu girin")
        return self


class AdoptionInput(StrictInput):
    playbook_id: Identifier
    version_id: Identifier
    purpose: str = Field(min_length=3, max_length=2000)


MODELS = {
    "scenarios": ScenarioInput,
    "contradictions": ContradictionInput,
    "arguments": ArgumentInput,
    "drafts": DraftInput,
}


def _validated(model, body):
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                  for error in exc.errors(include_input=False, include_url=False)]
        raise HTTPException(422, errors) from None


def _audit(session, user, action, record_id, matter_id=None):
    session.add(Audit(actor_id=user.id, matter_id=matter_id, action=action, object_id=record_id))


def _invalidate(store, session, matter, reason):
    data = store.decode(matter)
    data.update(updated_at=now(), practice_revision=data.get("practice_revision", 0) + 1)
    store.update(matter, data)
    for product in session.scalars(select(Record).where(
        Record.kind == "product", Record.matter_id == matter.id, Record.firm_id == matter.firm_id
    )):
        data = store.decode(product)
        data.update(status="stale", stale_reason=reason)
        store.update(product, data)


def _fact_snapshots(store, session, matter_id, user, ids):
    snapshots = []
    for fact_id in dict.fromkeys(ids):
        fact = require_child(session, fact_id, "fact", matter_id, user)
        data = store.decode(fact)
        snapshots.append({"id": fact.id, "revision": fact.revision, "text": data["text"],
                          "status": data["status"], "evidence_id": data.get("evidence_id")})
    return snapshots


def _evidence_snapshots(store, session, matter_id, user, ids):
    missing = set(ids)
    snapshots = []
    if not missing:
        return snapshots
    documents = session.scalars(select(Record).where(
        Record.kind == "document", Record.matter_id == matter_id, Record.firm_id == user.firm_id
    ).limit(500))
    for document in documents:
        data = store.decode(document)
        for passage in data.get("passages", []):
            if passage["id"] in missing:
                snapshots.append({"id": passage["id"], "document_id": document.id,
                                  "name": data["name"], "locator": passage["locator"],
                                  "source_sha256": data.get("sha256"),
                                  "passage_sha256": digest(passage["text"])})
                missing.remove(passage["id"])
        if not missing:
            break
    if missing:
        raise HTTPException(422, "Kanıtlar bu dosyanın erişilebilir yerel pasajlarından seçilmelidir")
    return snapshots


def _authority_snapshots(store, session, matter_id, user, refs):
    snapshots = []
    seen = set()
    for ref in refs:
        identity = (ref["product_id"], ref["passage_id"])
        if identity in seen:
            continue
        seen.add(identity)
        product = require_child(session, ref["product_id"], "product", matter_id, user)
        candidates = store.decode(product).get("authority_candidates") or {}
        hit = next((item for item in candidates.get("hits", [])
                    if item.get("passage_id") == ref["passage_id"]), None)
        if not hit:
            raise HTTPException(422, "Kamu referansı bu dosyada kaydedilmiş bir kaynak adayından seçilmelidir")
        snapshots.append({**ref, "authority_id": hit.get("authority_id"),
                          "source_version_id": hit.get("source_version_id"),
                          "source_sha256": hit.get("source_sha256"),
                          "review_status": hit.get("review_status"), "candidate_only": True})
    return snapshots


def _content(store, session, matter_id, user, body):
    data = body.model_dump(exclude={"expected_revision", "change_note"})
    data.update(authorship="user", authored_by=user.id, legal_authority=False)
    if "fact_ids" in data:
        data["fact_snapshots"] = _fact_snapshots(store, session, matter_id, user, data["fact_ids"])
    if "evidence_ids" in data:
        data["evidence_snapshots"] = _evidence_snapshots(
            store, session, matter_id, user, data["evidence_ids"]
        )
        data["authority_snapshots"] = _authority_snapshots(
            store, session, matter_id, user, data["authority_refs"]
        )
    return data


def _write_version(store, session, user, kind, body, content, matter_id=None, record=None):
    if record is None:
        if body.expected_revision is not None:
            raise HTTPException(422, "Yeni kayıtta expected_revision kullanılamaz")
        entity_id, version_number = uid(), 1
    else:
        if body.expected_revision != record.revision:
            raise HTTPException(409, "Kayıt değişti; güncel sürümü açıp yeniden deneyin")
        if len(body.change_note) < 3:
            raise HTTPException(422, "Yeni sürüm için değişiklik gerekçesi girin")
        entity_id, version_number = record.id, store.decode(record)["version"] + 1
    version_id = f"{entity_id}-{uid()[:24]}"
    version_data = {"entity_id": entity_id, "entity_kind": kind, "version": version_number,
                    "content": content, "authored_by": user.id,
                    "change_note": body.change_note, "immutable": True}
    store.add(session, "practice_version", user, version_data, matter_id, version_id)
    latest = {**content, "version": version_number, "latest_version_id": version_id, "updated_at": now()}
    if record is None:
        record = store.add(session, kind, user, latest, matter_id, entity_id)
    else:
        store.update(record, latest)
    return record


def _versions(store, session, entity, limit, offset):
    # Authorization is performed on the entity before this bounded history lookup.
    rows = session.scalars(select(Record).where(
        Record.kind == "practice_version", Record.firm_id == entity.firm_id,
        Record.matter_id == entity.matter_id,
        Record.id.startswith(entity.id + "-", autoescape=True),
    ).order_by(Record.created_at.desc()).limit(limit).offset(offset))
    return [store.view(row) for row in rows if store.decode(row).get("entity_id") == entity.id]


def _require_playbook(session, playbook_id, user):
    row = session.get(Record, playbook_id)
    if not row or row.kind != "firm_playbook" or row.firm_id != user.firm_id or row.matter_id:
        raise HTTPException(404, "Kurum rehberi bulunamadı")
    return row


def _curator(user):
    if user.role not in {"admin", "curator"}:
        raise HTTPException(403, "Kurum rehberini yalnızca yetkili küratör düzenleyebilir")


def practice_router():
    router = APIRouter(prefix="/api/v1", tags=["lawyer-authored-practice"])

    @router.get("/playbooks")
    def playbooks(request: Request, user=Depends(authenticate),
                  limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            rows = session.scalars(select(Record).where(
                Record.kind == "firm_playbook", Record.firm_id == user.firm_id, Record.matter_id.is_(None)
            ).order_by(Record.created_at.desc()).limit(limit).offset(offset))
            return [store.view(row) for row in rows]

    @router.post("/playbooks", status_code=201)
    def create_playbook(body: PlaybookInput, request: Request, user=Depends(authenticate)):
        _curator(user)
        store = request.app.state.store
        with store.session() as session:
            content = _content(store, session, None, user, body)
            content["classification"] = "firm_preference"
            row = _write_version(store, session, user, "firm_playbook", body, content)
            _audit(session, user, "playbook_created", row.id)
            session.commit()
            return store.view(row)

    @router.get("/playbooks/{playbook_id}/versions")
    def playbook_versions(playbook_id: str, request: Request, user=Depends(authenticate),
                          limit: int = Query(default=100, ge=1, le=100),
                          offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            return _versions(store, session, _require_playbook(session, playbook_id, user), limit, offset)

    @router.post("/playbooks/{playbook_id}/versions", status_code=201)
    def revise_playbook(playbook_id: str, body: PlaybookInput, request: Request,
                        user=Depends(authenticate)):
        _curator(user)
        store = request.app.state.store
        with store.session() as session:
            row = _require_playbook(session, playbook_id, user)
            content = _content(store, session, None, user, body)
            content["classification"] = "firm_preference"
            _write_version(store, session, user, "firm_playbook", body, content, record=row)
            _audit(session, user, "playbook_version_created", row.id)
            session.commit()
            return store.view(row)

    @router.get("/matters/{matter_id}/practice/playbooks")
    def adopted_playbooks(matter_id: str, request: Request, user=Depends(authenticate),
                         limit: int = Query(default=100, ge=1, le=100),
                         offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rows = session.scalars(select(Record).where(
                Record.kind == "practice_playbook", Record.matter_id == matter_id,
                Record.firm_id == user.firm_id,
            ).order_by(Record.created_at.desc()).limit(limit).offset(offset))
            return [store.view(row) for row in rows]

    @router.post("/matters/{matter_id}/practice/playbooks", status_code=201)
    def adopt_playbook(matter_id: str, body: AdoptionInput, request: Request,
                       user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            playbook = _require_playbook(session, body.playbook_id, user)
            version = session.get(Record, body.version_id)
            if (not version or version.kind != "practice_version" or version.firm_id != user.firm_id
                    or version.matter_id is not None):
                raise HTTPException(404, "Rehber sürümü bulunamadı")
            snapshot = store.decode(version)
            if snapshot.get("entity_id") != playbook.id:
                raise HTTPException(404, "Rehber sürümü bulunamadı")
            if (snapshot["content"]["curation_status"] != "curated"
                    or store.decode(playbook)["curation_status"] != "curated"):
                raise HTTPException(409, "Yalnızca küratör incelemesinden geçmiş etkin rehberler benimsenebilir")
            data = {"playbook_id": playbook.id, "version_id": version.id, "version": snapshot["version"],
                    "title": snapshot["content"]["title"], "text": snapshot["content"]["text"],
                    "domain": snapshot["content"]["domain"], "purpose": body.purpose,
                    "source_sha256": digest(snapshot["content"]["text"]), "classification": "firm_preference",
                    "legal_authority": False, "adopted_by": user.id, "immutable": True}
            row = store.add(session, "practice_playbook", user, data, matter_id)
            _invalidate(store, session, matter, "Kurum rehberi açıkça benimsendi; hazırlık bağlamını inceleyin.")
            _audit(session, user, "playbook_adopted", row.id, matter_id)
            session.commit()
            return store.view(row)

    @router.get("/matters/{matter_id}/practice/{kind}")
    def list_records(matter_id: str, kind: PracticeKind, request: Request, user=Depends(authenticate),
                     limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rows = session.scalars(select(Record).where(
                Record.kind == KINDS[kind], Record.matter_id == matter_id, Record.firm_id == user.firm_id
            ).order_by(Record.created_at.desc()).limit(limit).offset(offset))
            return [store.view(row) for row in rows]

    @router.post("/matters/{matter_id}/practice/{kind}", status_code=201)
    def create_record(matter_id: str, kind: PracticeKind, body: dict[str, Any], request: Request,
                      user=Depends(authenticate)):
        parsed = _validated(MODELS[kind], body)
        store = request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            content = _content(store, session, matter_id, user, parsed)
            row = _write_version(store, session, user, KINDS[kind], parsed, content, matter_id)
            _invalidate(store, session, matter, "Avukat çalışma kaydı eklendi; hazırlık bağlamı değişti.")
            _audit(session, user, "practice_created", row.id, matter_id)
            session.commit()
            return store.view(row)

    @router.get("/matters/{matter_id}/practice/{kind}/{record_id}/versions")
    def record_versions(matter_id: str, kind: PracticeKind, record_id: str, request: Request,
                        user=Depends(authenticate), limit: int = Query(default=100, ge=1, le=100),
                        offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            row = require_child(session, record_id, KINDS[kind], matter_id, user)
            return _versions(store, session, row, limit, offset)

    @router.post("/matters/{matter_id}/practice/{kind}/{record_id}/versions", status_code=201)
    def revise_record(matter_id: str, kind: PracticeKind, record_id: str, body: dict[str, Any],
                       request: Request, user=Depends(authenticate)):
        parsed = _validated(MODELS[kind], body)
        store = request.app.state.store
        with store.session() as session:
            row = require_child(session, record_id, KINDS[kind], matter_id, user)
            content = _content(store, session, matter_id, user, parsed)
            _write_version(store, session, user, KINDS[kind], parsed, content, matter_id, row)
            _invalidate(store, session, require_matter(session, matter_id, user),
                        "Avukat çalışma kaydı değişti; bağlı hazırlıkları yeniden inceleyin.")
            _audit(session, user, "practice_version_created", row.id, matter_id)
            session.commit()
            return store.view(row)

    return router
