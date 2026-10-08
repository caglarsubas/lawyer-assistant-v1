"""Synthetic separate-account observations; no real legal or independence qualification."""

import copy
import io
from uuid import uuid4

import pytest
from docx import Document
from pypdf import PdfReader
from sqlalchemy import select
from test_analysis_authorities import mutate, payload
from test_analysis_comparisons import login
from test_authority_comparisons import revise, saved_comparison
from test_authority_comparisons import setup as comparison_setup
from test_authority_findings import count
from test_authority_findings import workbench as workbench_fixture

from app import authority_adjudications as adjudications
from app import authority_comparisons as comparisons
from app.auth import hash_password
from app.db import Membership, Record, User

workbench = workbench_fixture


def reviewer(workbench, username="reviewer"):
    app, client, base, *_ = workbench
    with app.state.store.session() as session:
        owner = session.scalar(select(User).where(User.username == "demo"))
        user = User(
            username=username,
            name="Test " + username,
            firm_id=owner.firm_id,
            role="lawyer",
            password_hash=hash_password("SYNTHETIC-review-only"),
        )
        session.add(user)
        session.flush()
        session.add(Membership(matter_id=base.split("/")[-1], user_id=user.id))
        session.commit()
        ident = user.id
    login(client, username)
    return ident


def setup(workbench, monkeypatch):
    endpoint, context, original, candidate, reader, permit = comparison_setup(workbench, monkeypatch)
    comp, _ = saved_comparison(workbench[1], endpoint)
    reviewer(workbench)
    return endpoint + "/" + comp["id"] + "/adjudications", comp, original, candidate, reader, permit


def request(client, endpoint, *, supported=False):
    response = client.get(endpoint + "/context")
    assert response.status_code == 200, response.text
    value = response.json()
    links = {
        "target_refs": ["after:application:a1"],
        "private_source_refs": ["after:synthetic-clause"],
        "public_source_indices": [0],
    }
    body = {
        "expected_basis_sha256": value["basis_sha256"],
        "expected_adjudication_id": value["expected_adjudication_id"],
        "request_id": uuid4().hex,
        "note": "SYNTHETIC independent account only, not legal approval.",
        "review_seconds": None,
        "adverse_scope": {
            "status": "selected_sources_inspected" if supported else "not_searched",
            "inspected_source_indices": [0] if supported else [],
            "limitations": "SYNTHETIC corpus gaps unknown.",
        },
        "observations": [
            {
                "dimension": dimension,
                "outcome": "supported" if supported else "not_assessed",
                "note": "SYNTHETIC semantic observation.",
                **(links if supported else {}),
            }
            for dimension in value["basis"]["dimensions"]
        ],
        "judgments": [
            {
                "source_index": item["source_index"],
                "dimension": item["dimension"],
                "outcome": "agree" if supported else "unresolved",
                "note": "SYNTHETIC disposition remains human judgment.",
                **(links if supported else {}),
            }
            for item in value["basis"]["comparison"]["assessment"]["dispositions"]
        ],
    }
    return body, value


def saved(client, endpoint, body=None):
    body = body or request(client, endpoint)[0]
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_separate_account_scoped_counts_unknowns_exact_sources_and_no_promotion(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, comp, original, candidate, *_ = setup(workbench, monkeypatch)
    ciphertext = payload(app, comp["id"])
    body, capture = request(client, endpoint)
    assert capture["can_record"] and capture["independent_account"]
    value, _ = saved(client, endpoint, body)
    data = value["snapshot"]
    assert value["freshness"]["status"] == "current" and value["is_latest_for_reviewer"]
    assert data["basis"]["comparison"] == comp["snapshot"] and data["basis"]["account_separation_only"]
    assert data["reviewer_id"] != original["reviewer_id"]
    assert data["coverage"] == {
        "semantic": {"total": 6, "assessed": 0},
        "findings": {"total": 6, "assessed": 0},
        "adverse_scope": "selected_sources_only",
        "corpus_completeness": "unknown",
        "adverse_recall": None,
    }
    assert data["assessment"]["review_seconds"] is None and data["model_use"] == "none"
    assert not data["qualification_granted"] and data["legal_approval"] == "not_granted"
    assert payload(app, comp["id"]) == ciphertext
    assert client.get(base + "/analyses").json()[0]["checks"] == candidate["checks"]
    assert "SYNTHETIC" not in payload(app, value["id"])


def test_authors_cannot_adjudicate_but_can_read_and_supported_is_no_approval(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint, supported=True)
    login(client)
    inputs = client.get(endpoint + "/context").json()
    assert not inputs["independent_account"] and not inputs["can_record"]
    assert client.post(endpoint, json=body).status_code == 403
    login(client, "reviewer")
    value, _ = saved(client, endpoint, body)
    assert value["snapshot"]["coverage"]["semantic"]["assessed"] == 6
    assert value["snapshot"]["coverage"]["adverse_recall"] is None
    login(client)
    assert client.get(endpoint + "/" + value["id"]).json()["snapshot"] == value["snapshot"]


@pytest.mark.parametrize(
    "bad",
    [
        "missing",
        "duplicate",
        "source",
        "private",
        "target",
        "whitespace",
        "bool",
        "time",
        "fake_quote",
        "semantic",
        "semantic_duplicate",
        "adverse",
        "coverage",
        "links",
    ],
)
def test_malformed_or_foreign_coverage_no_partial_save(workbench, monkeypatch, bad):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint, supported=True)
    if bad == "missing":
        body["judgments"].pop()
    if bad == "duplicate":
        body["judgments"][-1] = copy.deepcopy(body["judgments"][0])
    if bad == "source":
        body["judgments"][0]["public_source_indices"] = [1]
    if bad == "private":
        body["observations"][0]["private_source_refs"] = ["after:foreign"]
    if bad == "target":
        body["observations"][0]["target_refs"] = ["after:foreign"]
    if bad == "whitespace":
        body["note"] = "   "
    if bad == "bool":
        body["judgments"][0]["source_index"] = True
    if bad == "time":
        body["review_seconds"] = 1.5
    if bad == "fake_quote":
        body["observations"][0]["text"] = "fabricated"
    if bad == "semantic":
        body["observations"].pop()
    if bad == "semantic_duplicate":
        body["observations"][-1] = body["observations"][0]
    if bad == "adverse":
        body["adverse_scope"]["status"] = "not_searched"
    if bad == "coverage":
        body["adverse_scope"]["inspected_source_indices"] = [7]
    if bad == "links":
        body["observations"][0]["target_refs"] = []
    assert client.post(endpoint, json=body).status_code == 422
    assert (
        count(app, adjudications.KIND)
        == count(app, adjudications.HEAD)
        == count(app, adjudications.ADMISSION)
        == 0
    )


def test_preserve_disagreement_per_account_heads_idempotency_and_no_consensus(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    first, body = saved(client, endpoint)
    assert client.post(endpoint, json=body).json() == first
    assert client.post(endpoint, json={**body, "note": "SYNTHETIC altered"}).status_code == 409
    assert client.post(endpoint, json={**body, "request_id": uuid4().hex}).status_code == 409
    frozen = payload(app, first["id"])
    reviewer(workbench, "second")
    second_body, _ = request(client, endpoint, supported=True)
    second_body["judgments"][0]["outcome"] = "disagree"
    second, _ = saved(client, endpoint, second_body)
    assert (
        second["sequence"] == 1
        and client.get(endpoint + "/" + first["id"]).json()["freshness"]["status"] == "current"
    )
    login(client, "reviewer")
    own, _ = request(client, endpoint)
    third, _ = saved(client, endpoint, own)
    assert third["sequence"] == 2 and third["snapshot"]["previous_adjudication_id"] == first["id"]
    assert client.get(endpoint + "/" + first["id"]).json()["freshness"]["status"] == "stale"
    assert client.get(endpoint + "/" + second["id"]).json()["freshness"]["status"] == "current"
    assert payload(app, first["id"]) == frozen and len(client.get(endpoint).json()) == 3


@pytest.mark.parametrize("change", ["draft", "private", "comparison", "recipe", "role"])
def test_changed_dependencies_stale_without_rewriting_judgments(workbench, monkeypatch, change):
    app, client, _, _, fact, *_ = workbench
    endpoint, comp, _, candidate, *_ = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)
    frozen = payload(app, value["id"])
    if change == "draft":
        revise(workbench, candidate)
    if change == "private":
        mutate(app, fact["id"], lambda data: data.update(text="SYNTHETIC altered fact"))
    if change == "comparison":
        login(client)
        saved_comparison(client, endpoint.rsplit("/" + comp["id"], 1)[0])
    if change == "recipe":
        monkeypatch.setattr(adjudications, "RECIPE", "future-adjudication")
    if change == "role":
        with app.state.store.session() as session:
            session.get(User, value["reviewer_id"]).role = "reader"
            session.commit()
    shown = client.get(endpoint + "/" + value["id"]).json()
    assert shown["freshness"]["status"] == "stale" and shown["snapshot"] == value["snapshot"]
    assert client.get(endpoint + "/" + value["id"] + "/export").status_code == 409
    assert payload(app, value["id"]) == frozen


@pytest.mark.parametrize("change", ["revoked", "exit", "pin", "pending_comparison"])
def test_denied_sources_withhold_all_notes_and_cached_content(workbench, monkeypatch, change):
    app, client, *_ = workbench
    endpoint, comp, _, _, reader, permit = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)
    if change == "revoked":
        permit.active = False
    if change == "exit":
        permit.fail_exit = True
    if change == "pin":
        reader.info["pointer"]["sequence"] += 1
    if change == "pending_comparison":
        mutate(
            app,
            comparisons._admission_id(comp["id"]),
            lambda data: data.update(publication_guard_completed=False),
        )
    shown = client.get(endpoint + "/" + value["id"])
    assert shown.status_code == 200 and shown.json()["snapshot"] is None and "SYNTHETIC" not in shown.text
    assert client.get(endpoint + "/" + value["id"] + "/export").status_code == 409


@pytest.mark.parametrize("format", ["json", "docx", "pdf"])
def test_private_exports_include_exact_comparison_quotes_and_unknown_coverage(workbench, monkeypatch, format):
    _, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)
    response = client.get(endpoint + "/" + value["id"] + "/export?format=" + format)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    text = (
        response.text
        if format == "json"
        else "\n".join(p.text for p in Document(io.BytesIO(response.content)).paragraphs)
        if format == "docx"
        else "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    )
    assert (
        "SYNTHETIC" in text
        and value["adjudication_sha256"] in "".join(text.split())
        and "corpus_completeness" in "".join(text.split())
    )


def test_postcommit_failure_retains_pending_without_quotes_or_retry_admission(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    audit = adjudications._audit

    def late(*args):
        audit(*args)
        monkeypatch.setattr(
            adjudications,
            "_finalize",
            lambda *_: (_ for _ in ()).throw(RuntimeError("synthetic late failure")),
        )

    monkeypatch.setattr(adjudications, "_audit", late)
    response = client.post(endpoint, json=body)
    assert response.status_code == 409 and response.json()["outcome"] == "committed_needs_revalidation"
    assert "SYNTHETIC" not in response.text and count(app, adjudications.KIND) == 1
    ident = response.json()["id"]
    retry = client.post(endpoint, json=body)
    assert retry.status_code == 201 and retry.json()["snapshot"] is None
    assert client.get(endpoint + "/" + ident + "/export").status_code == 409


@pytest.mark.parametrize("change", ["dependency", "membership", "guard_exit"])
def test_rendering_time_changes_discard_all_attachment_bytes(workbench, monkeypatch, change):
    app, client, base, _, fact, *_ = workbench
    endpoint, _, _, _, _, permit = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)

    def render(*_):
        if change == "dependency":
            mutate(app, fact["id"], lambda data: data.update(text="SYNTHETIC late mutation"))
        if change == "membership":
            with app.state.store.session() as session:
                session.query(Membership).filter(Membership.matter_id == base.split("/")[-1]).delete()
                session.commit()
        if change == "guard_exit":
            permit.fail_exit = True
        from fastapi import Response

        return Response(b"PRIVATE PARTIAL ATTACHMENT")

    monkeypatch.setattr(adjudications, "render_export", render)
    response = client.get(endpoint + "/" + value["id"] + "/export?format=docx")
    assert response.status_code in {404, 409} and "PRIVATE PARTIAL" not in response.text


@pytest.mark.parametrize(
    "failure", ["tamper", "wrong_route", "head", "read_only", "foreign_firm", "draft_author"]
)
def test_exact_routes_seals_roles_and_draft_author_separation(workbench, monkeypatch, failure):
    app, client, *_ = workbench
    endpoint, _, _, candidate, *_ = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)
    body, _ = request(client, endpoint)
    if failure == "tamper":
        mutate(
            app, value["id"], lambda data: data["assessment"].update(note="SYNTHETIC altered sealed record")
        )
        assert client.get(endpoint + "/" + value["id"]).status_code == 409
    if failure == "wrong_route":
        wrong = endpoint.replace("/analyses/" + candidate["id"], "/analyses/foreign-analysis")
        assert client.get(wrong + "/" + value["id"]).status_code == 404
    if failure == "head":
        route = (
            endpoint.split("/matters/")[1].split("/")[0],
            candidate["id"],
            value["snapshot"]["basis"]["comparison"]["context_id"],
            value["snapshot"]["basis"]["comparison"]["review_id"],
            value["snapshot"]["comparison_id"],
        )
        mutate(
            app,
            adjudications._head_id(route[-1], value["reviewer_id"]),
            lambda data: data.update(sequence=999),
        )
        assert client.get(endpoint + "/" + value["id"]).json()["snapshot"] is None
    if failure in {"read_only", "foreign_firm", "draft_author"}:
        with app.state.store.session() as session:
            user = session.get(User, value["reviewer_id"])
            if failure == "read_only":
                user.role = "reader"
            if failure == "foreign_firm":
                user.firm_id = "other-firm"
            if failure == "draft_author":
                session.get(Record, candidate["latest_version_id"]).owner_id = user.id
            session.commit()
        if failure == "draft_author":
            assert not client.get(endpoint + "/context").json()["independent_account"]
        assert client.post(endpoint, json=body).status_code == (404 if failure == "foreign_firm" else 403)


def test_actual_signed_bytes_adjudication_and_rights_revocation(workbench, monkeypatch, tmp_path):
    from test_analysis_authorities import freeze
    from test_analysis_authority_release import signed_source
    from test_authority_findings import saved as save_findings

    _, client, base, *_ = workbench
    contexts, spec, _, permission, prepared = signed_source(
        workbench, monkeypatch, tmp_path / "signed-adjudication"
    )
    context, _ = freeze(client, contexts, spec)
    reviews = contexts + "/" + context["id"] + "/reviews"
    original, _ = save_findings(client, reviews)
    revise(workbench, client.get(base + "/analyses").json()[0])
    endpoint = reviews + "/" + original["id"] + "/comparisons"
    comp, _ = saved_comparison(client, endpoint)
    reviewer(workbench)
    endpoint += "/" + comp["id"] + "/adjudications"
    value, _ = saved(client, endpoint)
    source = value["snapshot"]["basis"]["comparison"]["comparison_snapshot"]["authority_review_snapshot"][
        "context_snapshot"
    ]["manifest"]["sources"][0]
    evidence = source["evidence"]
    assert (
        evidence["text"]
        == prepared["snapshot"]["package"].text[evidence["start_offset"] : evidence["end_offset"]]
    )
    permission.active = False
    assert client.get(endpoint + "/" + value["id"]).json()["snapshot"] is None
    assert client.get(endpoint + "/" + value["id"] + "/export").status_code == 409
