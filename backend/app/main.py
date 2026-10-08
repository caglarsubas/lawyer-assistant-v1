import base64
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from .analysis_comparisons import comparison_router
from .analysis_reviews import review_router
from .analysis_suggestions import PURPOSE as ANALYSIS_SUGGESTION_PURPOSE
from .analysis_suggestions import suggestion_router
from .analysis_workbench import analysis_router
from .assistant import assistant_router
from .auth import (
    authenticate,
    bootstrap,
    check_password,
    create_session,
    require_child,
    require_matter,
    user_view,
)
from .config import ROOT, load_settings
from .context_packing import context_export_lines
from .db import Audit, LoginSession, Membership, Record, Store, User, digest, now, uid
from .exports import render_export
from .extract import SUPPORTED_SUFFIXES, ZIP_SUFFIXES
from .extraction_client import ExtractionClient, ExtractionError, validate_result
from .governance import governance_router
from .graph import GraphBackendError, GraphService
from .policy import POLICY_VERSION, evaluate, request_digest
from .portfolio import portfolio_router
from .practice import practice_router
from .provider import Provider
from .provision_mappings import provision_mappings_router
from .public_sources import PublicSourceStore, public_sources_router
from .readiness import readiness_router
from .research import (
    effective_product,
    finalize_product_authorization,
    guard_product_graph,
    mark_authorization_pending,
    run_research,
)
from .research_jobs import (
    QueueUnavailable,
    ResearchJobs,
    coordinator_lease,
    finish_run,
    recover_runs,
    request_stop,
    submission,
)
from .scanner import MalwareDetected, ScannerUnavailable, scan_document
from .search import PublicSearchService
from .source_reviews import source_reviews_router


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class MatterInput(Input):
    title: str = Field(min_length=1, max_length=200)
    domain: Literal["contracts", "commercial", "employment"]
    objective: str = Field(default="", max_length=4000)
    represented_party: str = Field(default="", max_length=200)
    stage: str = Field(default="hazırlık", max_length=200)
    relevant_date: str | None = None


class FactInput(Input):
    text: str = Field(min_length=1, max_length=4000)
    status: Literal["documented", "alleged", "disputed", "assumption", "inference"]
    evidence_id: str | None = None
    reason: str = Field(default="", max_length=1000)


class ResearchInput(Input):
    question: str = Field(min_length=3, max_length=4000)
    as_of: str | None = None


class AuthoritySearch(Input):
    query: str = Field(min_length=1, max_length=4000)
    as_of: str | None = None
    authority_id: str | None = Field(default=None, max_length=500)
    limit: int = Field(default=20, ge=1, le=50)


class ReviewInput(Input):
    claim_id: str | None = None
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)


class GatewayInput(Input):
    query: str = Field(min_length=1, max_length=500)
    destination: str = Field(max_length=500)
    query_type: Literal["public", "matter"] = "public"


class GatewayReference(Input):
    request_id: str


def valid_date(value):
    if value:
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("Noncanonical date")
        except ValueError:
            raise HTTPException(422, "Date must be YYYY-MM-DD") from None


def audit(session, user, action, object_id, matter_id=None):
    session.add(Audit(actor_id=user.id, action=action, object_id=object_id, matter_id=matter_id))


def invalidate(store, session, matter, reason):
    data = store.decode(matter)
    data["updated_at"] = now()
    store.update(matter, data)
    for product in session.scalars(
        select(Record).where(Record.matter_id == matter.id, Record.kind == "product")
    ):
        body = store.decode(product)
        body.update(status="stale", stale_reason=reason)
        store.update(product, body)


def check_evidence(store, session, matter_id, evidence_id):
    if not evidence_id:
        return
    for doc in session.scalars(
        select(Record).where(Record.matter_id == matter_id, Record.kind == "document")
    ):
        if any(p["id"] == evidence_id for p in store.decode(doc).get("passages", [])):
            return
    raise HTTPException(422, "Evidence must belong to this matter")


def seed_demo(store):
    with store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        if session.scalar(select(Record).where(Record.kind == "matter")):
            return
        matter = store.add(
            session,
            "matter",
            user,
            {
                "title": "Örnek hizmet sözleşmesi",
                "domain": "contracts",
                "objective": "Yükümlülükleri ve eksik bilgileri belge üzerinden incele.",
                "represented_party": "Örnek müşteri",
                "stage": "Sözleşme incelemesi",
                "relevant_date": None,
                "status": "draft",
                "synthetic": True,
            },
        )
        session.add(Membership(matter_id=matter.id, user_id=user.id))
        docid = uid()
        text = "TAMAMEN KURGUSAL GELİŞTİRME BELGESİ\n\nMadde 1 — Hizmet kapsamı ek belgede belirlenecektir.\n\nMadde 2 — Ödeme, teslim kabul tutanağının imzalanmasını izleyen otuz gün içinde yapılır.\n\nMadde 3 — Taraflar sözleşmenin sona ermesine ilişkin bildirimi yazılı olarak iletir."
        passages = [
            {"id": uid(), "locator": f"Paragraf {i + 1}", "text": t} for i, t in enumerate(text.split("\n\n"))
        ]
        store.add(
            session,
            "document",
            user,
            {
                "name": "Örnek sözleşme.txt",
                "status": "needs_review",
                "media_type": "text/plain",
                "page_count": None,
                "passage_count": len(passages),
                "passages": passages,
                "extraction_warnings": ["Kurgusal örnek; hukuki otorite değildir."],
                "sha256": digest(text),
                "synthetic": True,
            },
            matter.id,
            docid,
        )
        session.commit()


def create_app(settings=None):
    settings = settings or load_settings()

    @contextmanager
    def authorization_guard(info, action):
        from .release_authorization import ReleaseAuthorization
        from .release_snapshot import readonly_store
        with readonly_store(settings) as reader:
            authorization = ReleaseAuthorization(
                reader, PublicSourceStore(settings.public_source_dir),
                settings.data_dir / 'release-authorizations',
                Path(settings.graph_trusted_review_key), ROOT / 'ontology',
                settings.data_dir / 'publication-epoch',
            )
            with authorization.guard(info, action) as result:
                yield result

    @contextmanager
    def product_guard(data):
        try:
            with guard_product_graph(data, app.state.graph):
                yield
        except GraphBackendError:
            raise HTTPException(409, 'Graf sürümünün güncel yayın izni doğrulanamadı; yeniden araştırma gerekli.') from None

    @asynccontextmanager
    async def lifespan(app):
        store = Store(settings)
        try:
            with coordinator_lease(store) as verify_owner:
                app.state.research_owner = verify_owner
                bootstrap(store, settings)
                app.state.store = store
                app.state.provider = Provider(settings)
                app.state.extractor = (
                    ExtractionClient(settings.extraction_url, settings.extraction_token)
                    if not settings.demo_mode and settings.extraction_url
                    else None
                )
                app.state.graph = GraphService(
                    ROOT / "ontology", settings.graph_url, settings.graph_user, settings.graph_password,
                    release_root=Path(settings.graph_release_dir) if settings.graph_release_dir else None,
                    trusted_review_key=Path(settings.graph_trusted_review_key) if settings.graph_trusted_review_key else None,
                    authorization_guard=authorization_guard,
                )
                app.state.search = PublicSearchService(settings.opensearch_url, index=settings.search_index,
                                                     release_id=settings.search_release_id,
                                                     graph_release=app.state.graph.release)
                recover_runs(store)
                if settings.demo_mode:
                    seed_demo(store)
                app.state.research_jobs = ResearchJobs(
                    lambda ident: run_research(app, ident),
                    lambda ident: request_stop(store, ident, "service_shutdown"),
                    lambda ident: finish_run(store, ident),
                    verify_owner=verify_owner,
                )
                try:
                    yield
                finally:
                    app.state.research_jobs.close()
        finally:
            store.engine.dispose()

    app = FastAPI(
        title="Türkiye Legal Assistant",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.demo_mode else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.demo_mode else None,
    )
    app.state.settings = settings
    app.include_router(analysis_router())
    app.include_router(review_router())
    app.include_router(suggestion_router())
    app.include_router(comparison_router())
    app.include_router(practice_router())
    app.include_router(governance_router())
    app.include_router(portfolio_router())
    app.include_router(assistant_router())
    app.include_router(readiness_router())
    app.include_router(public_sources_router())
    app.include_router(source_reviews_router())
    app.include_router(provision_mappings_router())

    @app.exception_handler(StaleDataError)
    async def concurrent_edit(request, exc):
        return JSONResponse(
            status_code=409, content={"detail": "Kayıt başka bir işlemde değişti; yenileyip tekrar deneyin."}
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/v1/status")
    def status(user=Depends(authenticate)):
        return {
            "demo_mode": settings.demo_mode,
            "provider": {
                "configured": app.state.provider.configured,
                "identity_verified": settings.provider_identity_verified,
                "tenant_id": settings.provider_tenant_id,
                "organization": settings.provider_org_id,
                "key_id": settings.provider_key_id,
                "mode": "configured-unqualified" if app.state.provider.configured else "extractive",
                "readiness": app.state.provider.readiness(),
            },
            "graphs": {
                "mode": app.state.graph.mode,
                "ontology_version": app.state.graph.ontology_version,
                "legal_review_status": app.state.graph.legal_review_status,
                "serving_release": app.state.graph.release_status(),
            },
            "services": {
                "database": "sqlite-demo" if settings.demo_mode else "postgresql",
                "gateway": "enabled" if settings.gateway_enabled else "disabled",
                "search": "configured-unqualified" if app.state.search.configured else "no-qualified-corpus",
                "legal_corpus": "not-published",
            },
            "limitations": [
                "Ulusal ontoloji mühendislik taslağıdır; hukukçu incelemesi bekliyor.",
                "Hukuken doğrulanmış tarihsel karar korpusu henüz yüklenmedi.",
                "Canlı sağlayıcı, güvenlik ve pilot kabul eşikleri tamamlanmadı.",
            ],
        }

    @app.get("/api/v1/bootstrap")
    def bootstrap_status():
        return {"demo_mode": settings.demo_mode, "version": "0.1.0"}

    @app.post("/api/v1/auth/login")
    def login(body: Login, request: Request, response: Response):
        origin = request.headers.get("origin")
        if origin and origin not in settings.origins:
            raise HTTPException(403, "Origin denied")
        store = app.state.store
        # Per-account bucket avoids one failed user throttling every lawyer behind the same proxy.
        client_id = digest((request.client.host if request.client else "unknown") + ":" + body.username)
        with store.session() as session:
            since = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            attempts = session.scalar(
                select(func.count())
                .select_from(Audit)
                .where(
                    Audit.action == "login_failed", Audit.object_id == client_id, Audit.created_at >= since
                )
            )
            if attempts >= 10:
                raise HTTPException(429, "Çok fazla deneme; daha sonra tekrar deneyin")
            user = session.scalar(select(User).where(User.username == body.username, User.active.is_(True)))
            if not user or not check_password(body.password, user.password_hash):
                session.add(Audit(actor_id="anonymous", action="login_failed", object_id=client_id))
                session.commit()
                raise HTTPException(401, "Kullanıcı adı veya parola hatalı")
            token, csrf = create_session(session, user, settings.session_hours)
            response.set_cookie(
                "la_session",
                token,
                httponly=True,
                secure=settings.cookie_secure,
                samesite="strict",
                max_age=settings.session_hours * 3600,
                path="/",
            )
            return {"user": user_view(user), "csrf_token": csrf, "demo_mode": settings.demo_mode}

    @app.get("/api/v1/auth/me")
    def me(request: Request, user=Depends(authenticate)):
        return {"user": user_view(user), "csrf_token": request.state.csrf, "demo_mode": settings.demo_mode}

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response, user=Depends(authenticate)):
        with app.state.store.session() as session:
            item = session.get(LoginSession, digest(request.cookies["la_session"]))
            if item:
                session.delete(item)
                session.commit()
        response.delete_cookie("la_session", path="/")
        return {"ok": True}

    @app.get("/api/v1/matters")
    def matters(user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            rows = session.scalars(
                select(Record)
                .join(Membership, Membership.matter_id == Record.id)
                .where(Record.kind == "matter", Record.firm_id == user.firm_id, Membership.user_id == user.id)
                .order_by(Record.created_at.desc())
            ).all()
            return [
                {
                    **store.view(row),
                    "document_count": session.scalar(
                        select(func.count())
                        .select_from(Record)
                        .where(Record.kind == "document", Record.matter_id == row.id)
                    ),
                }
                for row in rows
            ]

    @app.post("/api/v1/matters", status_code=201)
    def new_matter(body: MatterInput, user=Depends(authenticate)):
        valid_date(body.relevant_date)
        store = app.state.store
        with store.session() as session:
            rec = store.add(session, "matter", user, {**body.model_dump(), "status": "draft"})
            session.add(Membership(matter_id=rec.id, user_id=user.id))
            audit(session, user, "matter_created", rec.id, rec.id)
            session.commit()
            return store.view(rec)

    @app.get("/api/v1/matters/{matter_id}")
    def get_matter(matter_id: str, user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            rec = require_matter(session, matter_id, user)
            children = session.scalars(
                select(Record).where(Record.matter_id == matter_id).order_by(Record.created_at.desc())
            ).all()
            result = store.view(rec)
            for kind, key in (
                ("document", "documents"),
                ("fact", "facts"),
                ("product", "products"),
                ("research", "research_runs"),
            ):
                result[key] = [
                    {
                        k: v
                        for k, v in store.view(row).items()
                        if k not in ("passages", "evidence", "original_path")
                    }
                    for row in children
                    if row.kind == kind and (kind != "research" or store.decode(row).get("purpose") != ANALYSIS_SUGGESTION_PURPOSE)
                ]
            result['products'] = [effective_product(item, app.state.graph) for item in result['products']]
            return result

    @app.post("/api/v1/matters/{matter_id}/documents", status_code=201)
    def upload(request: Request, matter_id: str, file: UploadFile = File(...), user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
        if not settings.demo_mode and not settings.clamav_host:
            raise HTTPException(503, "Mandatory malware scanner is not configured")
        if not settings.demo_mode and app.state.extractor is None:
            raise HTTPException(503, "Mandatory isolated extraction worker is not configured")
        content = file.file.read(settings.upload_max_bytes + 1)
        file.file.close()
        if len(content) > settings.upload_max_bytes or not content:
            raise HTTPException(413, "Belge boş veya boyut sınırını aşıyor")
        name = Path(file.filename or "document").name[:200]
        suffix = Path(name).suffix.casefold()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(
                415, "Bu format henüz doğrulanmadı; yerel olarak desteklenen biçime dönüştürün"
            )
        if suffix == ".pdf" and not content.startswith(b"%PDF-"):
            raise HTTPException(415, "PDF imzası doğrulanamadı")
        if suffix in ZIP_SUFFIXES and not content.startswith(b"PK"):
            raise HTTPException(415, "Office dosya imzası doğrulanamadı")
        scanner = settings.clamav_host
        if scanner:
            try:
                scan_document(content, scanner, port=settings.clamav_port,
                              timeout_seconds=settings.scanner_timeout_seconds,
                              max_bytes=settings.upload_max_bytes,
                              max_signature_age_days=settings.scanner_max_signature_age_days)
            except MalwareDetected:
                raise HTTPException(422, "Belge güvenlik denetiminden geçmedi") from None
            except ScannerUnavailable:
                raise HTTPException(503, "Zorunlu güvenlik taraması tamamlanamadı. Tarayıcı ve imza güncelliğini kontrol edin.") from None
        docid = uid()
        original_path = store.cipher.encrypt(content)
        vault = settings.data_dir / "documents"
        vault.mkdir(exist_ok=True, mode=0o700)
        target = vault / (docid + ".enc")
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(original_path)
        if not settings.demo_mode:
            try:
                extracted = app.state.extractor.execute(content, suffix)
            except ExtractionError:
                extracted = {"error": "extraction_failed"}
        else:
            # Synthetic demo only. Production always delegates to the network-isolated service.
            with tempfile.TemporaryDirectory(prefix="la-extract-") as temporary:
                path = Path(temporary) / ("input" + suffix)
                path.write_bytes(content)
                os.chmod(path, 0o600)
                env = {
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "PYTHONPATH": str(ROOT / "backend"),
                    "LANG": "en_US.UTF-8",
                }
                try:
                    completed = subprocess.run(
                        [sys.executable, "-m", "app.extract", str(path), suffix],
                        capture_output=True,
                        timeout=settings.extraction_timeout_seconds,
                        env=env,
                        cwd=temporary,
                        check=False,
                    )
                    extracted = (
                        validate_result(json.loads(completed.stdout))
                        if completed.returncode == 0
                        else {"error": "extraction_failed"}
                    )
                except (subprocess.TimeoutExpired, ValueError, ExtractionError):
                    extracted = {"error": "extraction_failed"}
        passages = [{**p, "id": uid()} for p in extracted.get("passages", [])]
        warnings = extracted.get("warnings", [])
        if "error" in extracted or not passages:
            warnings.append("Metin çıkarılamadı. Kaynak saklandı; içerik analize katılmadı.")
        if settings.demo_mode and not scanner:
            warnings.append(
                "Geliştirme modu: zararlı yazılım taraması yapılmadı. Gerçek müşteri belgeleri için kullanmayın."
            )
        data = {
            "name": name,
            "status": "needs_review" if passages else "failed",
            "media_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
            "page_count": extracted.get("page_count"),
            "passage_count": len(passages),
            "passages": passages,
            "extraction_warnings": warnings,
            "sha256": digest(content),
            "parser_version": "bounded-extractor-2",
            "original_path": target.name,
        }
        try:
            # Scanning/parsing may outlast logout, expiry or administrative revocation.
            # Keep this inside the cleanup boundary so denied intake leaves no original.
            user = authenticate(request)
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                rec = store.add(session, "document", user, data, matter_id, docid)
                invalidate(store, session, matter, "Yeni belge eklendi; kanıt kapsamı değişti.")
                audit(session, user, "document_ingested", rec.id, matter_id)
                session.commit()
                return {k: v for k, v in store.view(rec).items() if k not in ("passages", "original_path")}
        except (HTTPException, StaleDataError):
            # This request alone created the uniquely named encrypted object. A denied/failed
            # authorization or rolled-back optimistic update must not leave an orphan.
            # Ambiguous database commit failures retain ciphertext for operator reconciliation.
            target.unlink(missing_ok=True)
            raise

    @app.get("/api/v1/matters/{matter_id}/documents/{document_id}")
    def document(matter_id: str, document_id: str, user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            record = require_child(session, document_id, "document", matter_id, user)
            data = {k: v for k, v in store.view(record).items() if k != "original_path"}
            data["passages"] = [{**passage, "text_sha256": digest(passage["text"])}
                                for passage in data.get("passages", [])]
            return data

    @app.get("/api/v1/matters/{matter_id}/documents/{document_id}/original")
    def original_document(matter_id: str, document_id: str, user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            record = require_child(session, document_id, "document", matter_id, user)
            data = store.decode(record)
            if not data.get("original_path"):
                raise HTTPException(404, "Bu örnek için özgün dosya yok")
            # Paths are generated from document IDs, never supplied by documents or users.
            path = settings.data_dir / "documents" / (record.id + ".enc")
            if not path.is_file():
                raise HTTPException(409, "Özgün kaynak kullanılamıyor")
            content = store.cipher.decrypt(path.read_bytes())
            if digest(content) != data["sha256"]:
                raise HTTPException(409, "Özgün kaynak bütünlüğü doğrulanamadı")
            audit(session, user, "original_exported", record.id, matter_id)
            session.commit()
        suffix = Path(data["name"]).suffix
        return Response(
            content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="source-{document_id}{suffix}"'},
        )

    @app.post("/api/v1/matters/{matter_id}/facts", status_code=201)
    def new_fact(matter_id: str, body: FactInput, user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            check_evidence(store, session, matter_id, body.evidence_id)
            if body.status == "documented" and not body.evidence_id:
                raise HTTPException(422, "Belgelenmiş olgu kaynak gerektirir")
            record = store.add(
                session, "fact", user, {**body.model_dump(), "updated_at": now(), "history": []}, matter_id
            )
            invalidate(store, session, matter, "Olgu kaydı değişti.")
            audit(session, user, "fact_created", record.id, matter_id)
            session.commit()
            return store.view(record)

    @app.patch("/api/v1/matters/{matter_id}/facts/{fact_id}")
    def correct_fact(matter_id: str, fact_id: str, body: FactInput, user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            record = require_child(session, fact_id, "fact", matter_id, user)
            check_evidence(store, session, matter_id, body.evidence_id)
            if body.status == "documented" and not body.evidence_id:
                raise HTTPException(422, "Belgelenmiş olgu kaynak gerektirir")
            old = store.decode(record)
            history = old.pop("history", [])
            history.append({**old, "revision": record.revision, "corrected_by": user.id})
            store.update(record, {**body.model_dump(), "history": history, "updated_at": now()})
            invalidate(
                store,
                session,
                require_matter(session, matter_id, user),
                "Olgu düzeltildi; bağlı sonuçlar yeniden incelenmeli.",
            )
            audit(session, user, "fact_corrected", record.id, matter_id)
            session.commit()
            return store.view(record)

    @app.post("/api/v1/matters/{matter_id}/research", status_code=202)
    def research(matter_id: str, body: ResearchInput, user=Depends(authenticate)):
        valid_date(body.as_of)
        store = app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
        try:
            with app.state.research_jobs.reserve() as ident:
                with store.session() as session:
                    # Recheck access after admission; a rejected request leaves no job or audit record.
                    matter = require_matter(session, matter_id, user)
                    session.refresh(matter, with_for_update=True)
                    require_matter(session, matter_id, user)
                    rec = store.add(session, "research", user, {
                        **body.model_dump(), **submission(settings.research_budget_seconds),
                        "graph_release_pin": app.state.graph.release_pin(),
                    }, matter_id, record_id=ident)
                    audit(session, user, "research_started", rec.id, matter_id)
                    session.commit()
                    result = store.view(rec)
                try:
                    app.state.research_jobs.submit(ident)
                except QueueUnavailable:
                    finish_run(store, ident, "interrupted")
                    raise HTTPException(503, "Araştırma hizmeti durduruluyor") from None
                return result
        except QueueUnavailable as exc:
            raise HTTPException(503 if exc.closed else 429, "Araştırma hizmeti şu anda yeni çalışma kabul edemiyor") from None

    @app.post("/api/v1/matters/{matter_id}/authorities/search")
    def search_authorities(matter_id: str, body: AuthoritySearch, user=Depends(authenticate)):
        valid_date(body.as_of)
        with app.state.store.session() as session:
            require_matter(session, matter_id, user)
        try:
            result = app.state.search.search(**body.model_dump())
        except ValueError:
            raise HTTPException(422, "Geçersiz kaynak arama parametreleri") from None
        with app.state.store.session() as session:
            require_matter(session, matter_id, user)
        return result

    @app.get("/api/v1/matters/{matter_id}/research/{run_id}")
    def research_status(matter_id: str, run_id: str, user=Depends(authenticate)):
        with app.state.store.session() as session:
            return app.state.store.view(require_child(session, run_id, "research", matter_id, user))

    @app.post("/api/v1/matters/{matter_id}/research/{run_id}/cancel")
    def cancel(matter_id: str, run_id: str, user=Depends(authenticate)):
        store = app.state.store
        request_stop(store, run_id, authorize=lambda session: require_child(
            session, run_id, "research", matter_id, user))
        app.state.research_jobs.cancel(run_id)
        with store.session() as session:
            return store.view(require_child(session, run_id, "research", matter_id, user))

    @app.get("/api/v1/matters/{matter_id}/products/{product_id}")
    def product(matter_id: str, product_id: str, user=Depends(authenticate)):
        with app.state.store.session() as session:
            return effective_product(app.state.store.view(
                require_child(session, product_id, "product", matter_id, user)), app.state.graph)

    @app.post("/api/v1/matters/{matter_id}/products/{product_id}/review")
    def review(matter_id: str, product_id: str, body: ReviewInput, user=Depends(authenticate)):
        store = app.state.store
        committed = None
        try:
            with store.session() as session:
                record = require_child(session, product_id, "product", matter_id, user)
                data = store.decode(record)
                with product_guard(data):
                    if data["status"] in ("stale", "reviewed"):
                        raise HTTPException(409, "Bu sürüm değiştirilemez; yeni araştırma başlatın")
                    if body.claim_id:
                        claim = next((c for c in data["claims"] if c["id"] == body.claim_id), None)
                        if not claim:
                            raise HTTPException(404, "Bulgu bulunamadı")
                        claim.update(
                            review_status="approved" if body.decision == "approve" else "rejected",
                            review_note=body.note,
                            reviewed_by=user.id,
                            reviewed_at=now(),
                        )
                    elif body.decision == "approve":
                        if (
                            data.get("critical_gaps")
                            or not data["claims"]
                            or any(c["review_status"] != "approved" for c in data["claims"])
                        ):
                            raise HTTPException(409, "Kritik eksikler veya incelenmemiş bulgular var")
                        data["status"] = "reviewed"
                    else:
                        data["status"] = "needs_review"
                    mark_authorization_pending(data, 'review')
                    store.update(record, data)
                    audit(session, user, "product_reviewed", record.id, matter_id)
                    session.commit()
                    committed = {'product_id': record.id, 'revision': record.revision,
                                 'recorded_status': data['status']}

            return finalize_product_authorization(store, committed['product_id'], committed['revision'])
        except Exception:
            if committed is None:
                raise
            return JSONResponse(status_code=409, content={
                'detail': 'İnceleme kaydedildi; son yayın izni kontrolü tamamlanamadı. Kaydedilen sürümü inceleyip yeni araştırma başlatın.',
                'outcome': 'committed_needs_revalidation', 'needs_revalidation': True, **committed,
            })

    @app.get("/api/v1/matters/{matter_id}/products/{product_id}/export")
    def export(
        matter_id: str, product_id: str, format: Literal["docx", "pdf"] = "docx", user=Depends(authenticate)
    ):
        store = app.state.store
        with store.session() as session:
            record = require_child(session, product_id, "product", matter_id, user)
            data = store.view(record)
        with product_guard(data):
            lines = [data["title"], "GİZLİ — " + data["status"].upper(), data["summary"]]
            evidence = {p["id"]: p for p in data["evidence"]}
            for claim in data["claims"]:
                lines.append("İnceleme durumu: " + claim["review_status"])
                lines.append(claim["text"])
                if claim.get("review_note"):
                    lines.append("Avukat notu: " + claim["review_note"])
                for eid in claim["evidence_ids"]:
                    p = evidence[eid]
                    lines.append(f"Kaynak: {p['document_name']} / {p['locator']} [{eid}]")
                    lines.append(
                        "Kaynak SHA-256: " + p.get("document_sha256", "Bu eski çalışma sürümünde kaydedilmedi")
                    )
                    if "excerpt_start" in p:
                        lines.append(f"Alıntı Unicode aralığı: [{p['excerpt_start']}, {p['excerpt_end']}) "
                                     f"/ {p['full_passage_length']}; özgün pasajı ayrıca inceleyin.")
            if data.get("context_pack"):
                lines.extend(context_export_lines(data["context_pack"]))
            for issue in data["issues"]:
                lines.append("İnceleme başlığı: " + issue["label"])
                lines.extend(issue["missing_facts"])
                lines.extend(issue["counterarguments"])
            lines.extend(
                [
                    "Kapsam ve eksikler",
                    *data["coverage"]["gaps"],
                    "Sürümler: " + json.dumps(data["snapshots"], ensure_ascii=False),
                ]
            )
            response = render_export(lines, product_id, format)
            with store.session() as session:
                require_child(session, product_id, "product", matter_id, user)
                # Rendering and auditing happen before the final guard exit.
                # Neither this record nor an HTTP response proves file delivery.
                audit(session, user, "product_export_prepared", product_id, matter_id)
                session.commit()

        return response

    @app.get("/api/v1/matters/{matter_id}/practice/drafts/{record_id}/export")
    def export_draft(
        matter_id: str,
        record_id: str,
        version_id: str | None = None,
        format: Literal["docx", "pdf"] = "docx",
        user=Depends(authenticate),
    ):
        store = app.state.store
        with store.session() as session:
            record = require_child(session, record_id, "practice_draft", matter_id, user)
            latest = store.decode(record)
            version = require_child(
                session, version_id or latest["latest_version_id"], "practice_version", matter_id, user
            )
            snapshot = store.decode(version)
            if snapshot["entity_id"] != record_id or snapshot["entity_kind"] != "practice_draft":
                raise HTTPException(404, "Taslak sürümü bulunamadı")
            content = snapshot["content"]
            lines = [
                content["title"],
                "GİZLİ — AVUKAT TARAFINDAN YAZILMIŞ TASLAK",
                "Bu metin doğrulanmış hukuki otorite veya otomatik hukuki sonuç değildir.",
                "Durum: " + content["status"],
                f"Sürüm: {snapshot['version']} / {version.id}",
                "Yazar kimliği: " + snapshot["authored_by"],
                "Oluşturulma: " + version.created_at,
                *content["text"].splitlines(),
                "İnceleme notu: " + content.get("review_note", ""),
                "Değişiklik gerekçesi: " + snapshot.get("change_note", ""),
            ]
            audit(session, user, "practice_draft_exported", version.id, matter_id)
            session.commit()
        return render_export(lines, version.id, format)

    @app.get("/api/v1/graphs/catalog")
    def catalog(user=Depends(authenticate)):
        return app.state.graph.catalog()

    @app.get("/api/v1/graphs/coverage")
    def coverage(user=Depends(authenticate)):
        return app.state.graph.coverage()

    @app.get("/api/v1/graphs/explore")
    def explore(
        query: str = "",
        graph: Literal["structure", "jurisprudence"] = "structure",
        as_of: str | None = None,
        limit: int = 30,
        user=Depends(authenticate),
    ):
        valid_date(as_of)
        try:
            return app.state.graph.explore(
                query=query[:200], graph=graph, as_of=as_of, limit=min(max(limit, 1), 100)
            )
        except (ValueError, httpx.HTTPError, GraphBackendError):
            raise HTTPException(422, "Graf sorgusu doğrulanamadı veya kaynak kullanılamıyor") from None

    @app.post("/api/v1/graphs/tools/{name}")
    def graph_tool(name: str, payload: dict, user=Depends(authenticate)):
        try:
            return app.state.graph.tool(name, payload)
        except (ValueError, httpx.HTTPError, GraphBackendError):
            raise HTTPException(422, "İzin verilen araç ve sınırlandırılmış parametreler kullanın") from None

    @app.post("/api/v1/matters/{matter_id}/gateway/evaluate")
    def evaluate_gateway(matter_id: str, body: GatewayInput, user=Depends(authenticate)):
        store = app.state.store
        verdict = evaluate(
            body.query, body.destination, body.query_type, settings.gateway_allowlist.split(",")
        )
        payload_hash = request_digest(body.query, body.destination, body.query_type, user.id, matter_id)
        with store.session() as session:
            require_matter(session, matter_id, user)
            rec = store.add(
                session,
                "gateway",
                user,
                {
                    **body.model_dump(),
                    **verdict,
                    "payload_digest": payload_hash,
                    "approved": False,
                    "consumed": False,
                    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                },
                matter_id,
            )
            session.commit()
            return {**verdict, "payload_digest": payload_hash, "request_id": rec.id}

    @app.post("/api/v1/matters/{matter_id}/gateway/approve")
    def approve_gateway(matter_id: str, body: GatewayReference, user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            rec = require_child(session, body.request_id, "gateway", matter_id, user)
            data = store.decode(rec)
            if (
                rec.owner_id != user.id
                or data["decision"] != "REQUIRE_APPROVAL"
                or data["consumed"]
                or datetime.fromisoformat(data["expires_at"]) <= datetime.now(timezone.utc)
            ):
                raise HTTPException(403, "Bu istek onaylanamaz")
            data.update(approved=True, approved_at=now())
            store.update(rec, data)
            audit(session, user, "gateway_approved", rec.id, matter_id)
            session.commit()
            return {"request_id": rec.id, "approved": True, "payload_digest": data["payload_digest"]}

    @app.post("/api/v1/matters/{matter_id}/gateway/execute")
    def execute_gateway(matter_id: str, body: GatewayReference, user=Depends(authenticate)):
        store = app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rec = session.scalar(select(Record).where(Record.id == body.request_id).with_for_update())
            if not rec or rec.kind != "gateway" or rec.matter_id != matter_id or rec.owner_id != user.id:
                raise HTTPException(404, "İstek bulunamadı")
            data = store.decode(rec)
            verdict = evaluate(
                data["query"], data["destination"], data["query_type"], settings.gateway_allowlist.split(",")
            )
            expected = request_digest(
                data["query"], data["destination"], data["query_type"], user.id, matter_id
            )
            if (
                data["consumed"]
                or data["payload_digest"] != expected
                or data["policy_version"] != POLICY_VERSION
                or datetime.fromisoformat(data["expires_at"]) <= datetime.now(timezone.utc)
                or verdict["decision"] == "DENY"
                or (verdict["decision"] == "REQUIRE_APPROVAL" and not data["approved"])
            ):
                raise HTTPException(403, "Geçersiz, süresi dolmuş veya kullanılmış dış istek")
            if not settings.gateway_enabled or not settings.gateway_url or not settings.gateway_token:
                raise HTTPException(503, "Dış kaynak geçidi yapılandırılmadı")
            data["consumed"] = True
            store.update(rec, data)
            audit(session, user, "gateway_dispatched", rec.id, matter_id)
            session.commit()
        try:
            fetch_deadline = time.monotonic() + 15
            with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "POST",
                    settings.gateway_url.rstrip("/") + "/fetch",
                    json={"query": data["query"], "destination": data["destination"]},
                    headers={
                        "Authorization": "Bearer " + settings.gateway_token,
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    response.raise_for_status()
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise ValueError("Compressed gateway envelope rejected")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        if time.monotonic() > fetch_deadline:
                            raise ValueError("Gateway time budget exceeded")
                        size += len(chunk)
                        if size > 800_000:
                            raise ValueError("Oversized gateway envelope")
                        chunks.append(chunk)
                    source = json.loads(b"".join(chunks))
            if (
                not isinstance(source, dict)
                or source.get("source_url") != data["destination"]
                or source.get("query") != data["query"]
            ):
                raise ValueError("Source does not match approved request")
            if source.get("media_type") not in ("text/plain", "text/html"):
                raise ValueError("Unsupported source media")
            raw = base64.b64decode(source["content_base64"], validate=True)
            if len(raw) > 512 * 1024 or digest(raw) != source["sha256"]:
                raise ValueError("Invalid source response")
            source = {
                key: source[key] for key in ("source_url", "query", "media_type", "sha256", "content_base64")
            }
            source.update(
                status="quarantined",
                rights_status="unverified",
                acquired_at=now(),
                policy_version=POLICY_VERSION,
                request_digest=expected,
                injection_check="pending",
                legal_review="pending",
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise HTTPException(502, "Kaynak güvenle alınamadı; istek yeniden kullanılmaz") from None
        with store.session() as session:
            require_matter(session, matter_id, user)
            saved = store.add(session, "quarantined_source", user, source, matter_id)
            session.commit()
        return {k: v for k, v in source.items() if k != "content_base64"} | {"id": saved.id}

    return app
