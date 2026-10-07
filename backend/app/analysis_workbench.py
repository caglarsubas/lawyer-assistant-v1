"""Private, lawyer-authored rationale drafts and structural consistency checks.

Successful checks neither establish passage entailment nor legal applicability.
The R01 offline contracts remain separate; this editor permits incomplete drafts.
"""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, model_validator
from sqlalchemy import select

from .analysis_contracts import ISODate
from .auth import authenticate, require_child, require_matter
from .db import Record, digest
from .exports import render_export
from .practice import StrictInput, VersionInput, _audit, _fact_snapshots, _invalidate, _write_version

RECIPE = "private-rationale-checks-v1"
NodeID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
NodeRefs = Annotated[list[NodeID], Field(max_length=20)]
PassageRefs = Annotated[list[str], Field(max_length=20)]


class Selection(StrictInput):
    evidence_id: str = Field(min_length=1, max_length=500)
    passage_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    document_revision: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if not 0 < self.end - self.start <= 4000:
            raise ValueError("Select an exact span of 1–4000 Unicode code points")
        return self


class Premise(StrictInput):
    id: NodeID
    kind: Literal["fact", "assumption", "unknown"]
    fact_id: str | None = Field(default=None, min_length=1, max_length=500)
    fact_revision: int | None = Field(default=None, ge=1)
    text: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def source(self):
        if self.kind == "fact":
            if not self.fact_id or self.fact_revision is None or self.text:
                raise ValueError("Ledger premises use a fact identifier; their text and role come from the server")
        elif self.fact_id or self.fact_revision is not None or not self.text:
            raise ValueError("Assumptions and unknowns need explicit text and cannot impersonate ledger facts")
        return self


class Condition(StrictInput):
    id: NodeID
    text: Text
    kind: Literal["element", "exception", "jurisdiction", "burden"] = "element"
    required_status: Literal["met", "not_met"] = "met"


class Rule(StrictInput):
    id: NodeID
    kind: Literal["contract_clause", "legal_norm"] = "contract_clause"
    text: Text
    evidence_ids: PassageRefs = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list, max_length=12)


class Assessment(StrictInput):
    condition_id: NodeID
    status: Literal["met", "not_met", "unknown"] = "unknown"
    premise_ids: NodeRefs = Field(default_factory=list)


class Application(StrictInput):
    id: NodeID
    rule_id: NodeID
    premise_ids: NodeRefs = Field(default_factory=list)
    rationale: Text
    assessments: list[Assessment] = Field(default_factory=list, max_length=12)


class Alternative(StrictInput):
    id: NodeID
    kind: Literal["adverse_argument", "alternative_classification", "material_distinction", "search_gap"]
    text: Text
    evidence_ids: PassageRefs = Field(default_factory=list)


class Conclusion(StrictInput):
    text: Text
    requested_disposition: Literal["supported_candidate", "conditional", "withheld"] = "conditional"
    application_ids: NodeRefs = Field(default_factory=list)
    alternative_ids: NodeRefs = Field(default_factory=list)
    uncertainty: list[Text] = Field(default_factory=list, max_length=20)
    next_step: Text


class AnalysisInput(VersionInput):
    title: str = Field(min_length=3, max_length=200)
    issue: str = Field(min_length=3, max_length=2000)
    posture: str = Field(default="", max_length=2000)
    event_date: ISODate | None = None
    evidence: list[Selection] = Field(default_factory=list, max_length=20)
    premises: list[Premise] = Field(default_factory=list, max_length=20)
    rules: list[Rule] = Field(default_factory=list, max_length=12)
    applications: list[Application] = Field(default_factory=list, max_length=12)
    alternatives: list[Alternative] = Field(default_factory=list, max_length=12)
    conclusion: Conclusion

    @model_validator(mode="after")
    def references(self):
        nodes = [*self.premises, *self.rules, *self.applications, *self.alternatives,
                 *(condition for rule in self.rules for condition in rule.conditions)]
        if len({node.id for node in nodes}) != len(nodes):
            raise ValueError("Rationale node identifiers must be unique")
        evidence = [item.evidence_id for item in self.evidence]
        if len(set(evidence)) != len(evidence) or sum(item.end - item.start for item in self.evidence) > 20000:
            raise ValueError("Use unique passage selections with at most 20000 code points in total")

        def refs(values, known):
            if len(set(values)) != len(values) or not set(values) <= set(known):
                raise ValueError("Duplicate, unresolved or cross-step references")

        rules = {rule.id: rule for rule in self.rules}
        for item in [*self.rules, *self.alternatives]:
            refs(item.evidence_ids, evidence)
        for application in self.applications:
            refs([application.rule_id], rules)
            refs(application.premise_ids, [item.id for item in self.premises])
            refs([item.condition_id for item in application.assessments],
                 [item.id for item in rules[application.rule_id].conditions])
            for item in application.assessments:
                refs(item.premise_ids, application.premise_ids)
        refs(self.conclusion.application_ids, [item.id for item in self.applications])
        refs(self.conclusion.alternative_ids, [item.id for item in self.alternatives])
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 100000:
            raise ValueError("Rationale input exceeds the 100000-byte draft budget")
        return self


def _passages(store, session, matter_id, user, needed):
    """Bounded local lookup; unexamined or ambiguous references fail closed."""
    found, examined, characters = {}, 0, 0
    documents = session.scalars(select(Record).where(
        Record.kind == "document", Record.firm_id == user.firm_id, Record.matter_id == matter_id
    ).order_by(Record.created_at, Record.id).limit(501))
    document_count = 0
    for document in documents:
        document_count += 1
        if document_count > 500:
            raise HTTPException(422, "Belge arama sınırı aşıldı; daha küçük bir çalışma alanı kullanın.")
        data = store.decode(document)
        for passage in data.get("passages", []):
            examined += 1
            characters += len(passage["text"])
            if examined > 2000 or characters > 2000000:
                raise HTTPException(422, "Pasaj arama sınırı aşıldı; dayanakları daha küçük bir çalışma alanında seçin.")
            if passage["id"] in needed:
                if passage["id"] in found:
                    raise HTTPException(422, "Pasaj kimliği belirsiz; belge kaydını inceleyin.")
                found[passage["id"]] = {
                    "evidence_id": passage["id"], "document_id": document.id,
                    "document_revision": document.revision, "document_sha256": data.get("sha256"),
                    "name": data["name"], "locator": passage["locator"],
                    "passage_sha256": digest(passage["text"]), "text": passage["text"],
                }
    if set(found) != set(needed):
        raise HTTPException(422, "Dayanaklar bu çalışma alanının erişilebilir yerel pasajlarından seçilmelidir.")
    return found


def _contradictions(store, session, matter_id, firm_id, fact_ids):
    relevant = []
    if not fact_ids:
        return relevant
    for examined, row in enumerate(session.scalars(select(Record).where(
        Record.kind == "practice_contradiction", Record.firm_id == firm_id, Record.matter_id == matter_id
    ).order_by(Record.id).limit(1001))):
        if examined >= 1000:
            raise HTTPException(422, "Çelişki kontrol sınırı aşıldı; çalışma alanını daraltın.")
        content = store.decode(row)
        if set(content["fact_ids"]) <= fact_ids:
            relevant.append({"id": row.id, "revision": row.revision, "status": content["status"],
                             "fact_ids": content["fact_ids"]})
    return relevant


def check_rationale(content):
    """Declared-reference checks; never a semantic or legal critic."""
    defects = []

    def add(code, target, severity, message):
        identifier = digest(f"{code}:{target}")[:24]
        if not any(item["id"] == identifier for item in defects):
            defects.append({"id": identifier, "code": code, "target_id": target,
                            "severity": severity, "message": message})

    rules = {item["id"]: item for item in content["rules"]}
    premises = {item["id"]: item for item in content["premises"]}
    facts = {item["id"]: item for item in content["fact_snapshots"]}
    selected_apps = set(content["conclusion"]["application_ids"])
    selected_alts = set(content["conclusion"]["alternative_ids"])
    # Check only dependencies of the conclusion for withholding; omitted branches
    # are exposed separately and remain part of the stored, editable rationale.
    used_premises, used_rules = set(), set()
    if not selected_apps:
        add("missing_application", "conclusion", "critical", "Sonuç için bir uygulama adımı bağlanmamış.")
    for app in content["applications"]:
        if app["id"] not in selected_apps:
            continue
        rule = rules[app["rule_id"]]
        used_rules.add(rule["id"])
        used_premises.update(app["premise_ids"])
        if not rule["evidence_ids"]:
            add("missing_rule_evidence", rule["id"], "critical", "Kural veya sözleşme maddesi için özgün pasaj bağlanmamış.")
        if rule["kind"] == "legal_norm":
            add("unqualified_legal_norm", rule["id"], "critical",
                "Özel belge, mevzuat otoritesini doğrulamaz. Hüküm sürümü, zaman ve yetki incelemesi gerekli.")
        if not rule["conditions"]:
            add("missing_conditions", rule["id"], "critical", "Kuralın koşulları ve istisnaları tanımlanmamış.")
        if not app["premise_ids"]:
            add("missing_premises", app["id"], "critical", "Uygulama adımına öncül bağlanmamış.")
        assessments = {item["condition_id"]: item for item in app["assessments"]}
        for condition in rule["conditions"]:
            assessment = assessments.get(condition["id"])
            target = f"{app['id']}:{condition['id']}"
            if assessment is None:
                add("unassessed_condition", target, "critical", "Bu koşul veya istisna değerlendirilmemiş.")
            elif assessment["status"] == "unknown":
                add("unknown_condition", target, "major", "Koşulun durumu bilinmiyor; değerlendirme koşullu kalır.")
            elif not assessment["premise_ids"]:
                add("unsupported_assessment", target, "critical", "Belirli koşul değerlendirmesi için öncül bağlanmamış.")
            elif assessment["status"] != condition["required_status"]:
                add("condition_conflict", target, "critical", "Değerlendirme, bu önerme için gereken koşul durumuyla uyuşmuyor.")
    for premise_id in sorted(used_premises):
        premise = premises[premise_id]
        role = facts[premise["fact_id"]]["status"] if premise["kind"] == "fact" else premise["kind"]
        if role != "documented":
            add("unsettled_premise", premise_id, "major", "Beyan, tartışmalı olgu, çıkarım veya varsayım yerleşik olguya dönüştürülmez.")
        elif not facts[premise["fact_id"]]["evidence_id"]:
            add("missing_fact_evidence", premise_id, "critical", "Belgelenmiş olarak kaydedilen öncülün özgün dayanağı eksik.")
    used_facts = {premises[item]["fact_id"] for item in used_premises if premises[item]["kind"] == "fact"}
    for conflict in content["contradiction_snapshots"]:
        if conflict["status"] == "open" and set(conflict["fact_ids"]) <= used_facts:
            add("open_contradiction", conflict["id"], "critical", "Bağlı öncüller arasında açık bir çelişki kaydı var; avukat incelemesi gerekli.")
    alternatives = [item for item in content["alternatives"] if item["id"] in selected_alts]
    if not alternatives:
        add("missing_alternative", "conclusion", "critical", "Sonuca karşı argüman, alternatif veya açık araştırma boşluğu bağlanmamış.")
    for alternative in alternatives:
        if alternative["kind"] == "search_gap":
            add("adverse_search_gap", alternative["id"], "major", "Karşı otorite araştırması tamamlanmamış; bu kayıt bir karşı otorite değildir.")
        elif not alternative["evidence_ids"]:
            add("unsupported_alternative", alternative["id"], "critical", "İleri sürülen alternatif için özgün dayanak bağlanmamış.")
    if (len(used_rules) < len(rules) or len(used_premises) < len(premises)
            or len(selected_apps) < len(content["applications"]) or len(selected_alts) < len(content["alternatives"])):
        add("unlinked_steps", "conclusion", "major", "Bazı çalışma adımları bu sonucun bağımlılıklarına bağlanmamış; ayrıca inceleyin.")
    if not content["conclusion"]["uncertainty"]:
        add("missing_uncertainty", "conclusion", "major", "Belirsizlikleri ve eksik delilleri açıkça yazın.")
    add("semantic_review_required", "conclusion", "major",
        "Bağlantı ve koşul kontrolü metnin doğruluğunu, çıkarımın geçerliliğini veya hukuki uygulanabilirliği kanıtlamaz.")
    requested = content["conclusion"]["requested_disposition"]
    if requested == "supported_candidate":
        add("strong_conclusion_unverified", "conclusion", "major", "Daha güçlü sonuç talebi kaydedildi; anlamsal ve hukuki inceleme olmadan koşullu kalır.")
    critical = any(item["severity"] == "critical" for item in defects)
    return {"recipe": RECIPE, "scope": "declared_structure_only", "legal_approval": "not_granted",
            "effective_disposition": "withheld" if critical or requested == "withheld" else "conditional",
            "critical_count": sum(item["severity"] == "critical" for item in defects), "defects": defects,
            "dependency_nodes": sorted({*used_rules, *used_premises, *selected_apps, *selected_alts})}


def _content(store, session, matter_id, user, body, previous=None):
    content = body.model_dump(exclude={"expected_revision", "change_note"})
    fact_ids = {item.fact_id for item in body.premises if item.kind == "fact"}
    facts = _fact_snapshots(store, session, matter_id, user, sorted(fact_ids))
    revisions = {fact["id"]: fact["revision"] for fact in facts}
    if any(item.fact_revision != revisions[item.fact_id] for item in body.premises if item.kind == "fact"):
        raise HTTPException(409, "Seçilen olgu değişti; çalışma alanını yenileyip güncel kaydı inceleyin.")
    needed = {item.evidence_id for item in body.evidence} | {fact["evidence_id"] for fact in facts if fact["evidence_id"]}
    passages = _passages(store, session, matter_id, user, needed) if needed else {}
    evidence = []
    for selection in body.evidence:
        passage = passages[selection.evidence_id]
        if (selection.passage_sha256 != passage["passage_sha256"]
                or selection.document_revision != passage["document_revision"]):
            raise HTTPException(409, "Seçilen pasaj değişti; güncel belgeyi açıp dayanağı yeniden bağlayın.")
        if selection.end > len(passage["text"]):
            raise HTTPException(422, "Alıntı aralığı özgün pasajın dışına çıkıyor.")
        text = passage["text"][selection.start:selection.end]
        if not text.strip():
            raise HTTPException(422, "Boş veya yalnızca boşluk içeren bir alıntı dayanak olarak seçilemez.")
        evidence.append({**passage, "text": text, "start": selection.start, "end": selection.end,
                         "full_passage_length": len(passage["text"]), "quote_sha256": digest(text)})
    content.update(evidence=evidence, fact_snapshots=facts,
                   source_snapshots=[{key: value for key, value in item.items() if key != "text"}
                                     for item in passages.values()],
                   contradiction_snapshots=_contradictions(store, session, matter_id, user.firm_id, fact_ids),
                   schema_version="private-analysis.v1", authorship="user", authored_by=user.id,
                   status="needs_review", legal_authority=False)
    if (previous or {}).get("ai_assistance"):
        content.update(authorship="user_with_ai_assistance", ai_assistance=previous["ai_assistance"])
    content["checks"] = check_rationale(content)
    old_checks = {item["id"] for item in (previous or {}).get("checks", {}).get("defects", [])}
    new_checks = {item["id"] for item in content["checks"]["defects"]}
    content["revision_comparison"] = {
        "previous_version_id": (previous or {}).get("latest_version_id"),
        "changed_sections": [key for key in body.model_dump(exclude={"expected_revision", "change_note"})
                             if previous is not None and content[key] != previous.get(key)],
        "checks_no_longer_triggered": sorted(old_checks - new_checks),
        "new_check_ids": sorted(new_checks - old_checks),
        "scope": "structural_changes_only",
        "changed_dependency_groups": [key for key in ("fact_snapshots", "source_snapshots", "contradiction_snapshots")
                                      if previous is not None and content[key] != previous.get(key)],
    }
    return content


def _freshness(store, session, matter_id, user, content):
    reasons = []
    if content["checks"]["recipe"] != RECIPE:
        reasons.append("Kontrol kuralları değişti; yeni sürümde kontrolleri yeniden çalıştırın.")
    for fact in content["fact_snapshots"]:
        row = session.get(Record, fact["id"], populate_existing=True)
        if (not row or row.kind != "fact" or row.matter_id != matter_id or row.firm_id != user.firm_id
                or row.revision != fact["revision"] or any(store.decode(row).get(key) != fact.get(key)
                                                         for key in ("text", "status", "evidence_id"))):
            reasons.append("Bağlı olgu değişti veya artık erişilebilir değil.")
            break
    for source in content["source_snapshots"]:
        row = session.get(Record, source["document_id"], populate_existing=True)
        if not row or row.kind != "document" or row.matter_id != matter_id or row.firm_id != user.firm_id:
            reasons.append("Bağlı belge artık erişilebilir değil.")
            break
        document = store.decode(row)
        matches = [item for item in document.get("passages", []) if item["id"] == source["evidence_id"]]
        if (row.revision != source["document_revision"] or document.get("sha256") != source["document_sha256"]
                or len(matches) != 1 or digest(matches[0]["text"]) != source["passage_sha256"]):
            reasons.append("Bağlı belge veya özgün pasaj değişti.")
            break
    fact_ids = {item["id"] for item in content["fact_snapshots"]}
    if _contradictions(store, session, matter_id, user.firm_id, fact_ids) != content["contradiction_snapshots"]:
        reasons.append("Bağlı çelişki kayıtları değişti; öncülleri yeniden inceleyin.")
    return {"status": "stale" if reasons else "current", "reasons": reasons,
            "scope": "selected_private_dependencies_only"}


def _effective_freshness(freshness, review):
    reasons = list(dict.fromkeys([*freshness["reasons"], *review["reasons"]]))
    return {**freshness, "status": "stale" if reasons else "current", "reasons": reasons}


def _view(store, session, matter_id, user, row):
    from .analysis_reviews import projection

    content = store.view(row)
    freshness = _freshness(store, session, matter_id, user, content)
    version = require_child(session, content["latest_version_id"], "practice_version", matter_id, user)
    snapshot = store.decode(version)
    if snapshot.get("entity_id") != row.id or snapshot.get("entity_kind") != "practice_analysis":
        raise HTTPException(409, "Analizin sürüm bağlantısı doğrulanamadı.")
    review = projection(store, session, matter_id, row.id, version.id, user, snapshot["content"], freshness)
    freshness = _effective_freshness(freshness, review)
    effective = "reviewed" if review["effective_state"] == "reviewed_conditional" else content["status"]
    return {**content, "stored_status": content["status"], "status": "stale" if freshness["reasons"] else effective,
            "review": review, "freshness": freshness}


def _export_lines(content, snapshot, version, freshness, review=None):
    lines = [content["title"], "GİZLİ — AVUKAT TARAFINDAN YAZILMIŞ KOŞULLU ANALİZ TASLAĞI",
             "Hukuki onay verilmedi. Kontroller yalnızca beyan edilen yapıyı inceler.",
             f"Sürüm: {snapshot['version']} / {version.id}", f"Yazar kimliği: {snapshot['authored_by']}",
             f"Oluşturulma: {version.created_at}", f"Güncellik: {freshness['status']}", *freshness["reasons"],
             "Mesele: " + content["issue"], "Süreç: " + content["posture"],
             "Olay tarihi: " + (content["event_date"] or "Bilinmiyor"), "Öncüller"]
    if content.get("ai_assistance"):
        lines[1] = "GİZLİ — MODEL ÖNERİSİNDEN UYARLANMIŞ KOŞULLU ANALİZ TASLAĞI"
        lines.extend(["Model katkısı (hukuki inceleme değildir): " + json.dumps(
            {key: value for key, value in content["ai_assistance"].items()
             if key not in {"review_notes", "review_feedback", "feedback_responses"}}, ensure_ascii=False)])
        lines.extend(f"Alınan model önerisinin doğrulanmamış inceleme notu, geçiş {item['pass']} / {item['target_id']}: {item['text']}"
                     for item in content["ai_assistance"].get("review_notes", []))
        feedback = content["ai_assistance"].get("review_feedback")
        if feedback:
            lines.extend(["Seçilen inceleme bulguları ve doğrulanmamış model yanıtları; bulgular otomatik giderilmiş sayılmaz.",
                          f"Kaynak inceleme: {feedback['review_id']} / sürüm: {feedback['source_version_id']} / içerik: {feedback['content_sha256']}"])
            lines.extend(f"Avukat bulgusu {item['finding_id']} / {item['target_id']} / {item['severity']}: {item['text']} "
                         f"İstenen değişiklik: {item['suggested_change']} / dayanaklar: {', '.join(item['evidence_ids'])}"
                         for item in feedback["findings"])
            labels = {"proposed_change": "Düzenleme adayı", "requires_manual_work": "Elle çalışma gerekli", "unresolved": "Çözülmedi"}
            lines.extend(f"Model yanıtı {item['finding_id']} / {labels[item['outcome']]}: {item['text']} "
                         f"Bağlanan düzenlemeler: {', '.join(item['edited_targets']) or 'Yok'} / dayanaklar: {', '.join(item['evidence_ids'])}"
                         for item in content["ai_assistance"].get("feedback_responses", []))
    if review and review["latest"]:
        event = review["latest"]
        lines.extend(["Avukat incelemesi: " + review["effective_state"] + " / kapsam: " + review["scope"],
                      "Bu karar koşullu özel taslakla sınırlıdır; kamu hukuku otoritesi veya makine hukuki onayı değildir.",
                      f"İnceleme: {event['id']} / sıra {event['sequence']} / {event['created_at']}",
                      f"İnceleyen: {event['reviewer_name']} / {event['reviewer_id']}",
                      "İncelenen içerik SHA-256: " + event["content_sha256"], "İnceleme notu: " + event["note"],
                      *review["reasons"]])
        lines.extend(f"İnceleme ölçütü {item['criterion']}: {item['outcome']} / {item['note']}" for item in event["criteria"])
        lines.extend(f"İnceleme bulgusu {item['severity']} / {item['target_id']}: {item['text']} / önerilen değişiklik: {item['suggested_change']} / dayanak: {', '.join(item['evidence_ids'])}"
                     for item in event["findings"])
    facts = {item["id"]: item for item in content["fact_snapshots"]}
    for premise in content["premises"]:
        fact = facts.get(premise["fact_id"], {})
        lines.append(f"[{premise['id']}] {fact.get('status', premise['kind'])}: {fact.get('text', premise['text'])}")
        if fact:
            lines.append(f"Olgu defteri: {fact['id']} / sürüm {fact['revision']} / dayanak {fact['evidence_id'] or 'Bağlanmadı'}")
    for rule in content["rules"]:
        lines.append(f"Kural adayı [{rule['id']}] ({rule['kind']}): {rule['text']} / {', '.join(rule['evidence_ids'])}")
        for condition in rule["conditions"]:
            lines.append(f"Koşul [{condition['id']}] ({condition['kind']}), gereken durum {condition['required_status']}: {condition['text']}")
    for app in content["applications"]:
        lines.append(f"Uygulama [{app['id']}], kural {app['rule_id']}, öncüller {', '.join(app['premise_ids'])}: {app['rationale']}")
        for assessment in app["assessments"]:
            lines.append(f"Koşul {assessment['condition_id']}: {assessment['status']} / {', '.join(assessment['premise_ids'])}")
    for alternative in content["alternatives"]:
        lines.append(f"Alternatif [{alternative['id']}] ({alternative['kind']}): {alternative['text']} / {', '.join(alternative['evidence_ids'])}")
    conclusion = content["conclusion"]
    changes_requested = bool(review and review["latest"] and review["latest"]["decision"] == "changes_requested")
    effective = "withheld" if freshness["reasons"] or changes_requested else content["checks"]["effective_disposition"]
    if changes_requested:
        lines.append("Avukat değişiklik istedi; sonuç değerlendirmesi yeni incelemeye kadar bekletilir. Yapısal kontrollerin özgün sonucu değiştirilmez.")
    lines.extend(["Sonuç değerlendirmesi: " + effective, "Avukatın geçici sonuç metni: " + conclusion["text"],
                  "Bağlı uygulamalar: " + ", ".join(conclusion["application_ids"]),
                  "Bağlı alternatifler: " + ", ".join(conclusion["alternative_ids"]),
                  *["Belirsizlik: " + item for item in conclusion["uncertainty"]], "Sonraki adım: " + conclusion["next_step"]])
    for defect in content["checks"]["defects"]:
        lines.append(f"Kontrol [{defect['code']}] {defect['severity']} / {defect['target_id']}: {defect['message']}")
    for evidence in content["evidence"]:
        lines.extend([f"Özgün dayanak: {evidence['name']} / {evidence['locator']} [{evidence['evidence_id']}]",
                      f"Unicode aralığı: [{evidence['start']}, {evidence['end']}) / {evidence['full_passage_length']}",
                      evidence["text"], "Belge SHA-256: " + (evidence["document_sha256"] or "Kaydedilmedi"),
                      "Pasaj SHA-256: " + evidence["passage_sha256"], "Alıntı SHA-256: " + evidence["quote_sha256"]])
    lines.extend(["Kontrol sürümü: " + content["checks"]["recipe"],
                  "Sürüm karşılaştırması (yapısal): " + json.dumps(content["revision_comparison"], ensure_ascii=False),
                  "Değişiklik gerekçesi: " + snapshot.get("change_note", "")])
    return lines


def analysis_router():
    router = APIRouter(prefix="/api/v1/matters/{matter_id}/analyses", tags=["private-analysis-drafts"])

    @router.post("/check")
    def preview(matter_id: str, body: AnalysisInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            content = _content(store, session, matter_id, user, body)
            require_matter(session, matter_id, user)
            return content

    @router.get("")
    def listing(matter_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rows = session.scalars(select(Record).where(
                Record.kind == "practice_analysis", Record.matter_id == matter_id, Record.firm_id == user.firm_id
            ).order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            return [_view(store, session, matter_id, user, row) for row in rows]

    @router.post("", status_code=201)
    def create(matter_id: str, body: AnalysisInput, request: Request, user=Depends(authenticate)):
        return write(matter_id, body, request, user)

    def write(matter_id, body, request, user, record_id=None):
        store = request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            require_matter(session, matter_id, user)
            row = require_child(session, record_id, "practice_analysis", matter_id, user) if record_id else None
            content = _content(store, session, matter_id, user, body, store.decode(row) if row else None)
            row = _write_version(store, session, user, "practice_analysis", body, content, matter_id, row)
            _invalidate(store, session, matter, "Avukatın yapılandırılmış analizi değişti; hazırlık bağlamını inceleyin.")
            _audit(session, user, "analysis_version_created", row.id, matter_id)
            require_matter(session, matter_id, user)
            session.commit()
            return _view(store, session, matter_id, user, row)

    @router.get("/{record_id}/versions")
    def history(matter_id: str, record_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_child(session, record_id, "practice_analysis", matter_id, user)
            rows = session.scalars(select(Record).where(
                Record.kind == "practice_version", Record.firm_id == user.firm_id, Record.matter_id == matter_id,
                Record.id.startswith(record_id + "-", autoescape=True)
            ).order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            from .analysis_reviews import projection
            result = []
            for row in rows:
                snapshot = store.decode(row)
                if snapshot.get("entity_id") != record_id or snapshot.get("entity_kind") != "practice_analysis":
                    continue
                freshness = _freshness(store, session, matter_id, user, snapshot["content"])
                review = projection(store, session, matter_id, record_id, row.id, user, snapshot["content"], freshness)
                result.append({**store.view(row), "freshness": _effective_freshness(freshness, review), "review": review})
            return result

    @router.post("/{record_id}/versions", status_code=201)
    def revise(matter_id: str, record_id: str, body: AnalysisInput, request: Request, user=Depends(authenticate)):
        return write(matter_id, body, request, user, record_id)

    @router.get("/{record_id}/export")
    def export(matter_id: str, record_id: str, request: Request, version_id: str | None = None,
               format: Literal["docx", "pdf"] = "docx", user=Depends(authenticate)):
        store = request.app.state.store
        from .analysis_reviews import projection
        with store.session() as session:
            row = require_child(session, record_id, "practice_analysis", matter_id, user)
            version = require_child(session, version_id or store.decode(row)["latest_version_id"], "practice_version", matter_id, user)
            snapshot = store.decode(version)
            if snapshot["entity_id"] != row.id or snapshot["entity_kind"] != "practice_analysis":
                raise HTTPException(404, "Analiz sürümü bulunamadı.")
            content = snapshot["content"]
            freshness = _freshness(store, session, matter_id, user, content)
            review = projection(store, session, matter_id, row.id, version.id, user, content, freshness)
            lines = _export_lines(content, snapshot, version, _effective_freshness(freshness, review), review)
            response = render_export(lines, version.id, format)
            require_child(session, version.id, "practice_version", matter_id, user)
            if _freshness(store, session, matter_id, user, content) != freshness:
                raise HTTPException(409, "Dışa aktarım sırasında dayanaklar değişti; güncel durumla yeniden deneyin.")
            if projection(store, session, matter_id, row.id, version.id, user, content, freshness) != review:
                raise HTTPException(409, "Dışa aktarım sırasında avukat incelemesi değişti; yeniden deneyin.")
            _audit(session, user, "analysis_export_prepared", version.id, matter_id)
            session.commit()
            return response

    return router
