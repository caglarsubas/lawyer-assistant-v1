import re
from contextlib import contextmanager

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from .auth import require_matter
from .db import Record, User, now, uid
from .graph import GraphBackendError
from .policy import POLICY_VERSION
from .provider import ProviderError
from .research_jobs import JobStopped, checkpoint, ensure_active, finish_run


class GeneratedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=6000)
    claims: list[GeneratedClaim] = Field(max_length=20)


def _product_graph_pin(data):
    """Legacy document-only work has no public-corpus authorization dependency."""
    snapshots = data.get('snapshots', {})
    pin = snapshots.get('graph_release_pin')
    public_results = bool(data.get('authority_candidates', {}).get('hits')) or any(
        path.get('mode') == 'fuseki' or path.get('snapshot', {}).get('release_id')
        for path in data.get('graph_paths', []))
    public_results = public_results or any(
        snapshot.get('mode') == 'fuseki' or snapshot.get('release_id')
        for snapshot in snapshots.get('graphs', []))
    if not public_results and (not isinstance(pin, dict) or pin.get('status') != 'verified'):
        return None
    if (not isinstance(pin, dict) or pin.get('status') != 'verified'
            or set(pin) != {'status', 'release_id', 'serving_sha256', 'activation_sequence'}):
        raise GraphBackendError('The retained public-corpus dependency cannot be verified')
    references = [path.get('snapshot', {}).get('release_id') for path in data.get('graph_paths', [])
                  if path.get('mode') == 'fuseki']
    if data.get('authority_candidates', {}).get('hits'):
        references.append(data.get('authority_candidates', {}).get('snapshot', {}).get('release_id'))
    if any(reference != pin['release_id'] for reference in references):
        raise GraphBackendError('The retained public-corpus dependency does not match its release')
    return pin


@contextmanager
def guard_product_graph(data, graph):
    if data.get('authorization_revalidation'):
        raise GraphBackendError('A committed product requires publication revalidation')
    pin = _product_graph_pin(data)
    if pin is None:
        yield
        return
    try:
        with graph.release.current_guard() as info:
            current = {'status': 'verified', 'release_id': info['release_id'],
                       'serving_sha256': info['serving_sha256'],
                       'activation_sequence': info['pointer']['sequence']}
            if pin != current:
                raise ValueError('Retained release changed')
            yield
    except ValueError:
        raise GraphBackendError('Current authorization for the retained graph release is unavailable') from None


def mark_authorization_pending(data, operation):
    if _product_graph_pin(data) is not None:
        data['authorization_revalidation'] = {'status': 'pending', 'operation': operation}


def finalize_product_authorization(store, product_id, expected_revision):
    """Clear only this committed revision after its external guard exited cleanly.

    The marker is committed first so a process crash or post-commit guard failure
    leaves the retained work stale, even if the external failure is transient.
    A later independent edit must never be cleared by this completion callback.
    """
    with store.session() as session:
        record = session.get(Record, product_id)
        if not record or record.kind != 'product' or record.revision != expected_revision:
            raise GraphBackendError('The committed product changed before authorization completion')
        data = store.decode(record)
        if data.get('authorization_revalidation'):
            data.pop('authorization_revalidation')
            store.update(record, data)
            session.commit()
        return store.view(record)


def effective_product(data, graph):
    """Project stale eligibility without modifying the retained work or its history."""
    try:
        with guard_product_graph(data, graph):
            pass
    except GraphBackendError:
        return {**data, 'stored_status': data['status'], 'status': 'stale',
                'stale_reason': 'Graf sürümünün güncel yayın izni doğrulanamadı; yeniden araştırma ve inceleme gerekli.'}
    return data


def select_passages(question, passages, byte_budget=4000):
    def terms(text):
        return set(re.findall(r"\w+", text.replace("I", "ı").replace("İ", "i").casefold()))

    query_terms = terms(question) - {"ve", "ile", "için", "bir", "bu", "ne"}
    ranked = sorted(passages, key=lambda p: len(query_terms & terms(p["text"])), reverse=True)
    selected, used = [], 0
    for original in ranked:
        text = original["text"]
        start = 0
        if len(text.encode()) > 1800:
            match = next((m for m in re.finditer(r"\w+", text) if terms(m.group()) & query_terms), None)
            start = max(0, match.start() - 150) if match else 0
        end = min(len(text), start + 1500)
        while len(text[start:end].encode()) > 1800:
            end -= 1
        fragment = text[start:end]
        size = len(fragment.encode())
        if fragment and used + size <= byte_budget:
            selected.append(
                {
                    **original,
                    "text": fragment,
                    "excerpt_start": start,
                    "excerpt_end": end,
                    "full_passage_length": len(text),
                }
            )
            used += size
        if len(selected) >= 8:
            break
    return selected


def run_research(app, run_id):
    try:
        _run_research(app, run_id)
    except JobStopped as exc:
        finish_run(app.state.store, run_id, exc.outcome)
    except Exception as exc:
        finish_run(app.state.store, run_id, error_code=type(exc).__name__)


def publish_product(app, run_id, product, matter_version):
    """Commit output and completion together, serialized against cancellation.

    Matter-before-run matches archive's lock order. SQLite relies on the Record
    revision CAS to roll back the entire transaction if cancellation wins.
    The caller holds the graph publication authorization guard.
    """
    app.state.research_owner()
    store = app.state.store
    with store.session() as session:
        run = session.get(Record, run_id)
        user = session.get(User, run.owner_id)
        if not user or not user.active:
            raise ValueError("Research access revoked")
        matter = require_matter(session, run.matter_id, user)
        session.refresh(matter, with_for_update=True)
        require_matter(session, run.matter_id, user)
        session.refresh(run, with_for_update=True)
        state = store.decode(run)
        ensure_active(state)
        if matter.revision != matter_version:
            product["status"] = "stale"
        product["version"] = 1 + session.scalar(
            select(func.count()).select_from(Record)
            .where(Record.kind == "product", Record.matter_id == matter.id)
        )
        record = store.add(session, "product", user, product, run.matter_id)
        state.update(status="completed", product_id=record.id, phase="finished", finished_at=now())
        store.update(run, state)
        session.commit()
        return record.id, record.revision


def _run_research(app, run_id):
    app.state.research_owner()
    store, provider = app.state.store, app.state.provider
    with store.session() as session:
        run = session.get(Record, run_id, with_for_update=True)
        if run is None:
            return
        state = store.decode(run)
        if state["status"] in {"cancelling", "queued"}:
            ensure_active(state)
        if state["status"] != "queued":
            return
        state.update(status="running", phase="evidence", started_at=now())
        store.update(run, state)
        user = session.get(User, run.owner_id)
        if not user or not user.active:
            raise ValueError("Research access revoked")
        matter = require_matter(session, run.matter_id, user)
        matter_version = matter.revision
        brief = store.decode(matter)
        documents = session.scalars(
            select(Record).where(Record.matter_id == matter.id, Record.kind == "document")
        ).all()
        facts = session.scalars(
            select(Record).where(Record.matter_id == matter.id, Record.kind == "fact")
        ).all()
        passages, gaps, versions = [], [], {}
        for doc in documents:
            data = store.decode(doc)
            versions[doc.id] = doc.revision
            if data["status"] not in ("ready", "needs_review"):
                gaps.append(f"İşlenemeyen belge: {data['name']}")
            for passage in data.get("passages", []):
                passages.append(
                    {
                        **passage,
                        "document_id": doc.id,
                        "document_name": data["name"],
                        "document_sha256": data["sha256"],
                        "document_revision": doc.revision,
                    }
                )
            gaps.extend(data.get("extraction_warnings", []))
        for fact in facts:
            versions[fact.id] = fact.revision
        practice_versions = {
            row.id: {
                "revision": row.revision,
                "version_id": store.decode(row).get("latest_version_id")
                or store.decode(row).get("version_id"),
                "kind": row.kind,
            }
            for row in session.scalars(
                select(Record).where(
                    Record.matter_id == matter.id,
                    Record.kind.in_(
                        [
                            "practice_scenario",
                            "practice_contradiction",
                            "practice_argument",
                            "practice_draft",
                            "practice_playbook",
                        ]
                    ),
                )
            )
        }
        if practice_versions:
            gaps.append(
                "Avukat çalışma kayıtlarının sürümleri kaydedildi; varsayımlar belge olgusuna dönüştürülmedi. Çalışma notlarını ayrıca inceleyin."
            )
        session.commit()
    question = state["question"]
    graph_pin = state.get("graph_release_pin") or app.state.graph.release_pin()
    selected = select_passages(question, passages)
    if len(selected) != len(passages):
        gaps.append(
            f"Bağlama {len(selected)}/{len(passages)} metin bölümü alındı; tam dosya analizi yapılmadı."
        )
    if any(p["excerpt_start"] or p["excerpt_end"] < p["full_passage_length"] for p in selected):
        gaps.append(
            "Uzun metin bölümlerinden sınırlı alıntı pencereleri seçildi; özgün pasajın tamamını inceleyin."
        )
    gaps.append(
        "Hukuken incelenmiş kamu içtihat/mevzuat korpusu henüz yayımlanmadı; hukuki sonuç üretilmedi."
    )
    claims = []
    summary = "Belge hazırlık özeti: aşağıdaki alıntılar kaynak incelemesi için seçildi. Hukuki değerlendirme tamamlanmadı."
    provider_mode = "extractive"
    committed_product = None
    try:
        if app.state.graph.release_pin() != graph_pin:
            raise GraphBackendError("Graph publication changed after task submission")
        # Graph retrieval is additive and stays local. A missing path cannot remove document evidence.
        graph_paths = []
        for family in ("structure", "jurisprudence"):
            checkpoint(app, run_id, "graph_" + family)
            try:
                located = app.state.graph.tool(
                    "locate_issues",
                    {
                        "query": {"contracts": "sözleşme", "commercial": "ticaret", "employment": "iş"}[
                            brief["domain"]
                        ],
                        "graph": family,
                        "as_of": state.get("as_of"),
                        "limit": 20,
                    },
                )
                graph_paths.append(located)
            except (GraphBackendError, ValueError):
                gaps.append(f"{family}: graf kaynağı okunamadı; belge araması korundu.")
        checkpoint(app, run_id, "public_search")
        public_candidates = app.state.search.search(question, as_of=state.get("as_of"), limit=20)
        if public_candidates["coverage"]["status"] != "available":
            gaps.append("Kamu kaynak araması tamamlanmadı veya nitelikli korpus yapılandırılmadı.")
        checkpoint(app, run_id, "synthesis")
        if provider.configured and selected:
            response = provider.generate(question, selected)
            checkpoint(app, run_id, "verification")
            answer = GeneratedAnswer.model_validate_json(response)
            available = {p["id"]: p for p in selected}
            for candidate in answer.claims:
                if any(e not in available for e in candidate.evidence_ids):
                    raise ProviderError("Unknown evidence reference")
                if not all(candidate.text in available[e]["text"] for e in candidate.evidence_ids):
                    raise ProviderError("Generated claim does not match its quoted evidence")
                claims.append(
                    {
                        "id": uid(),
                        **candidate.model_dump(),
                        "kind": "document_quote",
                        "review_status": "pending",
                    }
                )
            # Free prose is not released as factual synthesis merely because a model returned it.
            provider_mode = ("approved-laptop-tunnel-validated-quotes"
                             if provider.transport_mode == 'approved_laptop_tunnel'
                             else "local-provider-validated-quotes")
        else:
            for p in selected[:6]:
                claims.append(
                    {
                        "id": uid(),
                        "text": p["text"][:1200],
                        "evidence_ids": [p["id"]],
                        "kind": "document_quote",
                        "review_status": "pending",
                    }
                )
            gaps.append("LLM yapılandırılmadı; yalnızca deterministik belge alıntıları gösteriliyor.")
        if not selected:
            summary = "Bu soruyu yanıtlamak için yeterli işlenmiş belge ve doğrulanmış hukuki kaynak yok."
        domain_issues = {
            "contracts": ["Taraflar ve temsil yetkisi", "Yükümlülükler ve ifa", "Fesih ve uyuşmazlık çözümü"],
            "employment": [
                "Çalışma ilişkisi ve tarihler",
                "Fesih gerekçesi ve bildirim",
                "Talepler ve dayanak belgeler",
            ],
            "commercial": ["Talep ve savunmalar", "İspat ve belgeler", "Usul ve görev incelemesi"],
        }
        product = {
            "title": question[:100],
            "version": 1,
            "status": "needs_review",
            "summary": summary,
            "claims": claims,
            "issues": [
                {"label": item, "missing_facts": ["Avukat incelemesi gerekli"], "counterarguments": []}
                for item in domain_issues[brief["domain"]]
            ],
            "coverage": {
                "searched": [
                    "Yetkili dosyanın çıkarılmış belge bölümleri",
                    "Ulusal ontoloji katalog kapsamı",
                ],
                "gaps": list(dict.fromkeys(gaps)),
            },
            "critical_gaps": ["legal_corpus_unqualified"],
            "snapshots": {
                "ontology": app.state.graph.ontology_version,
                "graphs": [g["snapshot"] for g in graph_paths],
                "graph_release_pin": graph_pin,
                "provider": provider_mode,
                "model": app.state.settings.provider_model or None,
                "sources": versions,
                "matter_revision": matter_version,
                "practice_versions": practice_versions,
                "policy": POLICY_VERSION,
                "corpus": public_candidates["snapshot"],
            },
            "evidence": selected,
            "graph_paths": graph_paths,
            "authority_candidates": public_candidates,
            "generated_at": now(),
        }
        if app.state.graph.release_pin() != graph_pin:
            raise GraphBackendError("Graph publication changed during research")
        checkpoint(app, run_id, "publication")
        with guard_product_graph(product, app.state.graph):
            mark_authorization_pending(product, 'research')
            committed_product = publish_product(app, run_id, product, matter_version)
        finalize_product_authorization(store, *committed_product)
    except Exception:
        if committed_product is None:
            raise
        with store.session() as session:
            run = session.get(Record, run_id, with_for_update=True)
            state = store.decode(run)
            state.pop('error', None)
            state.pop('error_code', None)
            state.update(status='completed', product_id=committed_product[0],
                         product_revision=committed_product[1],
                         outcome='committed_needs_revalidation', needs_revalidation=True,
                         warning='Çıktı kaydedildi; son yayın izni kontrolü tamamlanamadı. Kaydedilen sürümü inceleyip yeni araştırma başlatın.')
            store.update(run, state)
            session.commit()
