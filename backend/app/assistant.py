"""Read-only, permission-scoped portfolio assistant and source-backed product guide."""
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .auth import authenticate, require_matter
from .db import Audit, Record
from .portfolio import list_workspaces
from .provider import ProviderError

TURKEY = ZoneInfo("Europe/Istanbul")
SECTIONS = {"overview", "documents", "facts", "practice", "research", "comments"}
GUIDE = {
    "overview": "Çalışma alanının amacını, temsil edilen tarafı ve ilgili tarihi kontrol edin. Müvekkil etiketleri erişim yetkisi vermez.",
    "documents": "Dosyaları açık çalışma alanına yükleyin. Dosyayı seçerek çıkarılan pasajları ve çıkarım uyarılarını inceleyin; yüklenemeyen içerik araştırma dayanağı değildir.",
    "facts": "Belgelenmiş olguları, taraf beyanlarını, varsayımları ve çıkarımları ayrı kaydedin. Belgelenmiş olguyu ilgili kaynak pasajına bağlayın.",
    "practice": "Senaryoları, çelişkileri, destekleyen ve karşıt argümanları çalışma notlarında hazırlayın. Yapılandırılmış analizde öncül, kural, koşul, uygulama ve alternatifleri bağlayın; kritik kontroller sonucu bekletir. Kontroller hukuki doğrulama değildir. Taslakların önceki sürümleri korunur.",
    "research": "Araştırma sorunuzu ve ilgili tarihi belirtin. Sonuçta her iddianın pasajını ve uygulanabilirliğini kontrol edin; eksik hukuki kaynak yerine kesin sonuç üretmeyin.",
    "comments": "Çalışma alanındaki yorumlara not ekleyin. Yorumlar yazar ve kayıt tarihiyle saklanır; yorum bir hukuki otorite veya doğrulanmış olgu değildir.",
}
SOURCE_REVIEW_GUIDE = (
    "Kaynak incelemesini üstlenin; özgün dosyayı indirip çıkarılan pasajlarla karşılaştırın. "
    "Kullanım haklarını, kaynak kimliğini, metin çıkarımını ve hukuki sürüm uygunluğunu ayrı değerlendirin. "
    "Her kabulü bir dayanak ve içerik özetiyle kaydedin; metin çıkarımı için incelenen pasajları seçin. "
    "Kaynakta sonraki değişikliklerin bulunup bulunmadığını ve bilinmeyen tarihleri kontrol edin. "
    "Madde eşlemesinde başlık adayını seçin ve metin sınırlarını önizlemede doğrulayın. "
    "Düzenleme, madde ve tarihsel sürüm referanslarını ayrı kaydedin; bilinmeyen yürürlük tarihlerini boş bırakın. "
    "Kaynak incelemesi değişirse kabul edilmiş eşlemeyi yeniden değerlendirin. "
    "İnceleme tamamlanınca kayıt dosyasını dışa aktarın. Bu kayıt graf yayımlama onayı değildir; "
    "ayrı yayın incelemesi ve imzalı sürüm gerekir."
)


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str | None = Field(default=None, max_length=64)
    page: str = Field(default="workspaces", max_length=64)
    section: str = Field(default="overview", max_length=64)
    customer_ids: list[str] = Field(default_factory=list, max_length=100)
    date_from: date | None = None
    date_to: date | None = None
    date_field: Literal["created_at", "updated_at", "relevant_date"] = "created_at"

    @model_validator(mode="after")
    def valid_range(self):
        if self.page == "sources" and self.workspace_id:
            raise ValueError("Kaynak incelemesi çalışma alanı bağlamıyla birleştirilemez")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz")
        if any(not value or len(value) > 64 for value in self.customer_ids):
            raise ValueError("Geçersiz müvekkil kimliği")
        return self


class AssistantInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    mode: Literal["guide", "chat", "daily", "weekly", "monthly"] = "guide"
    question: str = Field(default="", max_length=2000)
    context: Context = Field(default_factory=Context)


def calendar_period(mode, current=None):
    today = (current or datetime.now(TURKEY)).astimezone(TURKEY).date()
    start = today if mode == "daily" else today - timedelta(days=today.weekday()) if mode == "weekly" else today.replace(day=1)
    return start, today


def source(workspace, label=None):
    return {"id": workspace["id"], "label": label or workspace["title"],
            "workspace_id": workspace["id"], "href": f"#/matters/{workspace['id']}"}


def exact_claims(raw, evidence):
    """Never display a free-form model summary as verified portfolio information."""
    try:
        value = json.loads(raw)
        claims = value.get("claims") if isinstance(value, dict) else None
        if not isinstance(claims, list) or not 1 <= len(claims) <= 8:
            raise ValueError()
        index = {item["id"]: item["text"] for item in evidence}
        results = []
        for claim in claims:
            if not isinstance(claim, dict):
                raise ValueError()
            text, ids = claim.get("text"), claim.get("evidence_ids")
            if (not isinstance(text, str) or not text.strip() or len(text) > 1200
                    or not isinstance(ids, list) or not 1 <= len(ids) <= 4
                    or any(not isinstance(key, str) or key not in index or text not in index[key] for key in ids)):
                raise ValueError()
            results.append((text, ids))
        return results
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProviderError("Assistant response did not match supplied evidence") from exc


def recheck_context(request, user, workspaces, comments):
    """Invalidate in-flight answers when their access or saved sources change."""
    current = authenticate(request)
    if current.id != user.id or current.firm_id != user.firm_id:
        raise HTTPException(401, "Oturum geçersiz")
    store = request.app.state.store
    with store.session() as session:
        for item in workspaces:
            record = require_matter(session, item["id"], current)
            if record.revision != item["revision"]:
                raise HTTPException(409, "Çalışma bağlamı değişti; güncel kaynaklarla yeniden deneyin.")
        for item in comments:
            record = session.get(Record, item["id"])
            if (not record or record.kind != "workspace_comment" or record.firm_id != current.firm_id
                    or record.matter_id != item["workspace_id"] or record.revision != item["revision"]):
                raise HTTPException(409, "Çalışma bağlamı değişti; güncel kaynaklarla yeniden deneyin.")


def assistant_router():
    router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

    @router.post("/respond")
    def respond(body: AssistantInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        context = body.context
        if context.page == "sources" and body.mode in {"guide", "chat"}:
            if body.mode == "chat" and not body.question:
                raise HTTPException(422, "Asistana bir soru yazın")
            # The source-review panel exposes a product guide only. It must not
            # collect unrelated portfolio records or send pending public sources
            # and confidential reviewer notes to inference implicitly.
            return {"answer": SOURCE_REVIEW_GUIDE, "mode": body.mode,
                    "sources": [{"id": "guide:source-review", "label": "Kaynak inceleme kullanım rehberi",
                                 "href": "#/coverage"}],
                    "suggestions": [{"label": "Kaynak kapsamına dön", "href": "#/coverage"}],
                    "period": None, "provider_used": False,
                    "limitations": ["Bu yanıt yalnızca ekranın kullanım rehberidir. Kaynak metni, inceleme notları ve kaydedilmemiş girdiler okunmaz; değerlendirme veya hukuki sonuç üretilmez."]}
        with store.session() as session:
            # Explicit current workspace IDs are checked even if filters omit them.
            active = None
            if context.workspace_id:
                active_record = require_matter(session, context.workspace_id, user)
                active = store.view(active_record)
            workspaces = list_workspaces(
                store, session, user, customer_ids=context.customer_ids,
                date_from=context.date_from.isoformat() if context.date_from else None,
                date_to=context.date_to.isoformat() if context.date_to else None,
                date_field=context.date_field,
            )
            ids = [item["id"] for item in workspaces]
            response = {"answer": "", "mode": body.mode, "sources": [], "suggestions": [],
                        "period": None, "provider_used": False, "limitations": []}
            if body.mode in {"daily", "weekly", "monthly"}:
                start, end = calendar_period(body.mode)
                lower = datetime.combine(start, time.min, TURKEY).astimezone(timezone.utc).isoformat()
                upper = datetime.combine(end + timedelta(days=1), time.min, TURKEY).astimezone(timezone.utc).isoformat()
                events = session.scalars(select(Audit).where(
                    Audit.matter_id.in_(ids), Audit.created_at >= lower, Audit.created_at < upper,
                ).order_by(Audit.created_at.desc()).limit(2001)).all() if ids else []
                limited = len(events) > 2000
                events = events[:2000]
                active_ids = {event.matter_id for event in events}
                active_workspaces = [item for item in workspaces if item["id"] in active_ids]
                documents = sum(item.get("document_count", 0) for item in workspaces)
                labels = {"daily": "Günlük", "weekly": "Haftalık", "monthly": "Aylık"}
                response["period"] = {"from": start.isoformat(), "to": end.isoformat()}
                response["answer"] = (
                    f"{labels[body.mode]} portföy özeti · {start.isoformat()} — {end.isoformat()} (Türkiye saati)\n\n"
                    f"Seçili filtrelerde erişebildiğiniz {len(workspaces)} çalışma alanı ve şu anda kayıtlı {documents} dosya var. "
                    f"Bu dönemde {len(active_ids)} çalışma alanında {'en az ' if limited else ''}{len(events)} kayıtlı işlem bulunuyor.\n\n"
                    + ("Dönemde işlem görülen çalışma alanları:\n" + "\n".join(
                        f"• {item['title']}" for item in active_workspaces[:100]
                    ) if active_ids else "Bu dönemde kayıtlı çalışma alanı işlemi bulunamadı.")
                )
                response["sources"] = [source(item) for item in workspaces if item["id"] in active_ids][:100]
                response["limitations"] = ["Özet mevcut erişim yetkileri, seçili filtreler ve kayıtlı işlemlerle sınırlıdır. Dosya sayısı dönem içi yükleme sayısı değil, güncel toplamdır. Süreler veya hukuki sonuçlar çıkarılmaz."]
                if limited:
                    response["limitations"].append("İşlem özeti en yeni 2.000 kayıtla sınırlı; daha dar filtre seçin.")
                if len(active_workspaces) > 100:
                    response["limitations"].append("Çalışma alanı başlıkları ve dayanak bağlantıları ilk 100 alanla sınırlı; toplam sayılar seçili kapsamı içerir.")
                return response

            section = context.section if context.section in SECTIONS else "overview"
            if active:
                response["answer"] = f"{active['title']} · {GUIDE[section]}"
                response["sources"] = [source(active)]
                response["suggestions"] = [
                    {"label": "Dosyaları incele", "href": f"#/matters/{active['id']}?tab=documents"},
                    {"label": "Yorum ekle", "href": f"#/matters/{active['id']}?tab=comments"},
                ]
            elif context.page == "graphs":
                response["answer"] = "Hukuk haritasında kavram ve kurum bağlantılarını inceleyin. Ontoloji kapsamını gerçek kaynak kapsamından ayırın; bir grafik yolu tek başına hukuki sonuca dayanak oluşturmaz."
            elif context.page == "coverage":
                response["answer"] = "Kaynak kapsamı sayfasında hangi kaynak ve dönemlerin edinildiğini kontrol edin. Korpusta bulunmayan kararlar hakkında eksiksizlik varsaymayın."
            elif context.page == "system":
                response["answer"] = "Sistem durumunda sağlayıcı, kaynak kapsamı ve hizmet sınırlamalarını inceleyin. Hizmetin çalışması, hukuki doğruluğun veya kaynak yeterliliğinin doğrulandığı anlamına gelmez."
            else:
                response["answer"] = (f"Seçili filtrelerde {len(workspaces)} çalışma alanınız var. Soldan bir veya birden fazla müvekkil seçin; seçilenlerden herhangi biriyle etiketli çalışma alanları listelenir. "
                                      "Tarih türünü ve aralığını seçerek daraltın. Çalışma alanını açın; dosyaları oraya yükleyin ve yorumları orta bölümde kaydedin.")
                response["suggestions"] = [{"label": "Çalışma alanları", "href": "#/workspaces"}]
            response["sources"].append({"id": f"guide:{section}", "label": "Platform kullanım rehberi", "href": "#/workspaces"})
            if body.mode == "guide":
                return response
            if not body.question:
                raise HTTPException(422, "Asistana bir soru yazın")
            # Curated instructions and saved workspace metadata are the only chat
            # inputs here. Original documents, unsaved editor contents and other
            # customers' work are not implicitly included.
            evidence = [{"id": "guide", "text": GUIDE[section]}]
            evidence_sources = {"guide": {"id": f"guide:{section}", "label": "Platform kullanım rehberi", "href": "#/workspaces"}}
            comment_snapshots = []
            selected = [active] if active else workspaces[:8]
            for item in selected:
                text = f"Çalışma alanı: {item['title']}. Amaç: {item.get('objective', '')}. Süreç: {item.get('stage', '')}."
                evidence.append({"id": item["id"], "text": text[:1400]})
                evidence_sources[item["id"]] = source(item)
            if active:
                comments = session.scalars(select(Record).where(
                    Record.kind == "workspace_comment", Record.matter_id == active["id"], Record.firm_id == user.firm_id
                ).order_by(Record.created_at.desc()).limit(4)).all()
                for record in comments:
                    data = store.view(record)
                    comment_snapshots.append({"id": record.id, "revision": record.revision,
                                              "workspace_id": active["id"]})
                    evidence.append({"id": record.id, "text": "Avukat yorumu: " + data.get("text", "")[:1000]})
                    evidence_sources[record.id] = {"id": record.id, "label": "Kayıtlı yorum", "workspace_id": active["id"], "href": f"#/matters/{active['id']}?tab=comments"}
        provider = request.app.state.provider
        if not provider.configured:
            response["limitations"] = ["Dil modeli henüz yapılandırılmadı. Yukarıdaki bağlama uygun kullanım rehberi yerel olarak gösteriliyor."]
            return response
        try:
            claims = exact_claims(provider.generate(body.question, evidence), evidence)
            # Exact quotes must still resolve to unchanged saved sources, and
            # the session itself may have expired or been revoked during inference.
            recheck_context(request, user, selected, comment_snapshots)
            response["answer"] = "Kaydedilmiş bağlamdan ilgili alıntılar:\n\n" + "\n\n".join(text for text, _ in claims)
            used = list(dict.fromkeys(key for _, keys in claims for key in keys))
            response["sources"] = [evidence_sources[key] for key in used]
            response["provider_used"] = True
            response["limitations"] = ["Yanıt kaynakla eşleşen alıntılarla sınırlıdır; yorumlar doğrulanmış hukuki olgu sayılmaz. Hukuki değerlendirme için araştırma akışını kullanın."]
        except ProviderError:
            # Recheck even on failure: the fallback also contains private context.
            recheck_context(request, user, selected, comment_snapshots)
            response["limitations"] = ["Model yanıtı alınamadı veya kaynakla doğrulanamadı. Bağlama uygun yerel kullanım rehberi gösteriliyor."]
        return response

    return router
