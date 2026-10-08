"""Synthetic comparisons of frozen findings, never a legal qualification."""

import copy
import io
from uuid import uuid4

import pytest
from docx import Document
from pypdf import PdfReader
from sqlalchemy import select
from test_analysis_authorities import mutate, payload
from test_authority_findings import count, saved
from test_authority_findings import setup as findings_setup
from test_authority_findings import workbench as workbench_fixture

from app import analysis_authorities as authorities
from app import authority_comparisons as comparisons
from app import authority_findings as findings
from app.db import Audit, Membership, Record, User

workbench = workbench_fixture


def revise(workbench, analysis, *, change=True):
    _, client, base, original, *_ = workbench
    body = copy.deepcopy(original)
    if change:
        body["applications"][0]["rationale"] = (
            "SYNTHETIC revised application; applicability and adverse law remain unresolved."
        )
    response = client.post(
        base + "/analyses/" + analysis["id"] + "/versions",
        json={
            **body,
            "expected_revision": analysis["revision"],
            "change_note": "SYNTHETIC explicit revision",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def setup(workbench, monkeypatch, *, change=True):
    reviews, context, analysis, reader, permit = findings_setup(workbench, monkeypatch)
    review, _ = saved(workbench[1], reviews)
    candidate = revise(workbench, analysis, change=change)
    return reviews + "/" + review["id"] + "/comparisons", context, review, candidate, reader, permit


def request(client, endpoint, *, outcome="unresolved"):
    response = client.get(endpoint + "/context")
    assert response.status_code == 200, response.text
    value = response.json()
    frozen = value["comparison"]["authority_review_snapshot"]
    body = {
        "candidate_version_id": value["comparison"]["candidate_version_id"],
        "expected_basis_sha256": value["basis_sha256"],
        "expected_comparison_id": value["expected_comparison_id"],
        "request_id": uuid4().hex,
        "note": "SYNTHETIC human comparison, not repair or legal approval.",
        "review_seconds": None,
        "dispositions": [
            {
                "source_index": index,
                "dimension": obs["dimension"],
                "outcome": outcome,
                "note": "SYNTHETIC original uncertainty remains.",
                "after_target_ids": source["target_ids"],
                "private_source_refs": ["after:synthetic-clause"],
            }
            for index, source in enumerate(frozen["assessment"]["sources"])
            for obs in source["observations"]
        ],
    }
    return body, value


def saved_comparison(client, endpoint, body=None):
    body = body or request(client, endpoint)[0]
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_new_version_is_expected_staleness_original_findings_remain_exact_no_model_or_promotion(
    workbench, monkeypatch
):
    app, client, base, *_ = workbench
    endpoint, context, review, candidate, *_ = setup(workbench, monkeypatch)
    frozen_review = payload(app, review["id"])
    before_context = payload(app, context["id"])
    body, capture = request(client, endpoint)
    assert capture["freshness"]["status"] == "current" and capture["can_record"]
    assert (
        client.get(endpoint.rsplit("/" + review["id"], 1)[0] + "/" + review["id"]).json()["freshness"][
            "status"
        ]
        == "stale"
    )
    value, _ = saved_comparison(client, endpoint, body)
    data = value["snapshot"]
    assert value["freshness"]["status"] == "current" and value["is_latest_comparison"]
    comp = data["comparison_snapshot"]
    assert comp["authority_review_snapshot"] == review["snapshot"]
    assert comp["base_version"] == 1 and comp["candidate_version"] == 2
    assert comp["candidate_version_id"] == candidate["latest_version_id"]
    assert comp["changes"][0]["target_id"] == "application:a1"
    assert {item["source_ref"] for item in comp["private_sources"]} == {
        "before:synthetic-clause",
        "after:synthetic-clause",
    }
    assert data["assessment"]["review_seconds"] is None and data["model_use"] == "none"
    assert not data["qualification_granted"] and data["legal_approval"] == "not_granted"
    assert payload(app, review["id"]) == frozen_review and payload(app, context["id"]) == before_context
    current = client.get(base + "/analyses").json()[0]
    assert (
        current["latest_version_id"] == candidate["latest_version_id"]
        and current["checks"] == candidate["checks"]
    )
    assert "SYNTHETIC" not in payload(app, value["id"])


@pytest.mark.parametrize(
    "bad",
    [
        "missing",
        "duplicate",
        "unknown_dimension",
        "wrong_source",
        "bad_target",
        "bad_ref",
        "empty_note",
        "time_bool",
        "time_fraction",
        "quote_override",
    ],
)
def test_exact_full_findings_validated_and_no_partial_record(workbench, monkeypatch, bad):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    if bad == "missing":
        body["dispositions"].pop()
    if bad == "duplicate":
        body["dispositions"][-1] = copy.deepcopy(body["dispositions"][0])
    if bad == "unknown_dimension":
        body["dispositions"][0]["dimension"] = "invented"
    if bad == "wrong_source":
        body["dispositions"][0]["source_index"] = 1
    if bad == "bad_target":
        body["dispositions"][0]["after_target_ids"] = ["rule:invented"]
    if bad == "bad_ref":
        body["dispositions"][0]["private_source_refs"] = ["after:foreign-document"]
    if bad == "empty_note":
        body["dispositions"][0]["note"] = "   "
    if bad == "time_bool":
        body["review_seconds"] = True
    if bad == "time_fraction":
        body["review_seconds"] = 1.5
    if bad == "quote_override":
        body["dispositions"][0]["text"] = "fabricated source"
    assert client.post(endpoint, json=body).status_code == 422
    assert (
        count(app, comparisons.KIND) == count(app, comparisons.HEAD) == count(app, comparisons.ADMISSION) == 0
    )


def test_addressed_requires_real_changed_after_target_and_current_private_quote_no_clearance(
    workbench, monkeypatch
):
    _, client, base, *_ = workbench
    workbench[3]["rules"][0]["kind"] = "legal_norm"
    endpoint, _, _, candidate, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint, outcome="addressed")
    body["dispositions"][0]["after_target_ids"] = ["rule:r1"]
    assert client.post(endpoint, json=body).status_code == 422
    body["dispositions"][0]["after_target_ids"] = ["application:a1"]
    body["dispositions"][0]["private_source_refs"] = ["before:synthetic-clause"]
    assert client.post(endpoint, json=body).status_code == 422
    body["dispositions"][0]["private_source_refs"] = ["after:synthetic-clause"]
    value, _ = saved_comparison(client, endpoint, body)
    assert {item["outcome"] for item in value["snapshot"]["assessment"]["dispositions"]} == {"addressed"}
    assert candidate["checks"]["critical_count"] > 0
    assert client.get(base + "/analyses").json()[0]["checks"] == candidate["checks"]
    assert value["legal_approval"] == "not_granted"


def test_retained_requires_all_original_targets_unchanged_and_removed_is_not_a_silent_mapping(
    workbench, monkeypatch
):
    _, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch, change=False)
    body, _ = request(client, endpoint, outcome="retained")
    body["dispositions"][0]["after_target_ids"] = ["rule:r1"]
    assert client.post(endpoint, json=body).status_code == 422
    body["dispositions"][0]["after_target_ids"] = ["rule:r1", "application:a1"]
    saved_comparison(client, endpoint, body)
    next_body, _ = request(client, endpoint, outcome="removed")
    for item in next_body["dispositions"]:
        item["after_target_ids"] = []
    assert client.post(endpoint, json=next_body).status_code == 422


def test_retry_head_conflict_and_history_preserve_immutable_disagreement(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    value, body = saved_comparison(client, endpoint)
    ciphertext = payload(app, value["id"])
    assert client.post(endpoint, json=body).json() == value
    assert client.post(endpoint, json={**body, "note": "SYNTHETIC contradictory judgment"}).status_code == 409
    assert client.post(endpoint, json={**body, "request_id": uuid4().hex}).status_code == 409
    next_body, _ = request(client, endpoint, outcome="not_assessed")
    second, _ = saved_comparison(client, endpoint, next_body)
    assert second["sequence"] == 2 and second["snapshot"]["previous_comparison_id"] == value["id"]
    old = client.get(endpoint + "/" + value["id"]).json()
    assert old["freshness"]["reasons"] == ["newer_comparison_exists"] and old["snapshot"] == value["snapshot"]
    assert (
        payload(app, value["id"]) == ciphertext
        and client.get(endpoint + "/" + value["id"] + "/export").status_code == 409
    )
    assert [item["sequence"] for item in client.get(endpoint).json()] == [2, 1]


@pytest.mark.parametrize(
    "change",
    [
        "new_version",
        "fact",
        "document",
        "research",
        "review_recipe",
        "context_recipe",
        "comparison_recipe",
        "dimensions",
        "reviewer_role",
        "live_content",
    ],
)
def test_dependency_changes_require_rereview_preserving_frozen_comparison(workbench, monkeypatch, change):
    app, client, base, _, fact, document, *_ = workbench
    endpoint, context, review, candidate, *_ = setup(workbench, monkeypatch)
    value, _ = saved_comparison(client, endpoint)
    ciphertext = payload(app, value["id"])
    if change == "live_content":
        mutate(app, candidate["id"], lambda data: data.update(title="SYNTHETIC altered live content"))
    if change == "new_version":
        revise(workbench, candidate)
    if change == "fact":
        mutate(app, fact["id"], lambda data: data.update(text="SYNTHETIC changed fact"))
    if change == "document":
        mutate(app, document, lambda data: data["passages"][0].update(text="SYNTHETIC changed text"))
    if change == "research":
        mutate(
            app,
            context["manifest"]["product_id"],
            lambda data: data.update(title="SYNTHETIC changed research"),
        )
    if change == "review_recipe":
        monkeypatch.setattr(findings, "RECIPE", "future-review")
    if change == "context_recipe":
        monkeypatch.setattr(authorities, "RECIPE", "future-context")
    if change == "comparison_recipe":
        monkeypatch.setattr(comparisons, "RECIPE", "future-comparison")
    if change == "dimensions":
        monkeypatch.setattr(
            findings, "DIMENSIONS", {**findings.DIMENSIONS, "history": "Changed history rubric"}
        )
    if change == "reviewer_role":
        with app.state.store.session() as session:
            session.get(User, review["reviewer_id"]).role = "reader"
            session.commit()
    shown = client.get(endpoint + "/" + value["id"])
    assert shown.status_code == 200, shown.text
    assert shown.json()["freshness"]["status"] == "stale" and shown.json()["snapshot"] == value["snapshot"]
    assert client.get(endpoint + "/" + value["id"] + "/export").status_code == 409
    assert payload(app, value["id"]) == ciphertext


@pytest.mark.parametrize("change", ["revoke", "exit", "pin", "missing_review", "pending_review"])
def test_public_denial_withholds_original_and_new_free_text(workbench, monkeypatch, change):
    app, client, *_ = workbench
    endpoint, _, review, _, reader, permit = setup(workbench, monkeypatch)
    value, _ = saved_comparison(client, endpoint)
    if change == "revoke":
        permit.active = False
    if change == "exit":
        permit.fail_exit = True
    if change == "pin":
        reader.info["pointer"]["sequence"] += 1
    if change == "missing_review":
        with app.state.store.session() as session:
            session.delete(session.get(Record, review["id"]))
            session.commit()
    if change == "pending_review":
        mutate(
            app,
            findings._admission_id(review["id"]),
            lambda data: data.update(publication_guard_completed=False),
        )
    shown = client.get(endpoint + "/" + value["id"])
    assert shown.status_code == 200 and shown.json()["snapshot"] is None
    assert shown.json()["freshness"]["status"] == "withheld" and "SYNTHETIC" not in shown.text
    assert client.get(endpoint + "/" + value["id"] + "/export").status_code == 409


@pytest.mark.parametrize("format", ["json", "docx", "pdf"])
def test_private_export_includes_original_findings_public_quote_changes_and_private_quotes(
    workbench, monkeypatch, format
):
    _, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    value, _ = saved_comparison(client, endpoint)
    response = client.get(endpoint + "/" + value["id"] + "/export?format=" + format)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert (
        "attachment" in response.headers["content-disposition"]
        and response.headers["x-content-type-options"] == "nosniff"
    )
    text = (
        response.text
        if format == "json"
        else "\n".join(p.text for p in Document(io.BytesIO(response.content)).paragraphs)
        if format == "docx"
        else "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(response.content)).pages)
    )
    comp = value["snapshot"]["comparison_snapshot"]
    assert value["comparison_sha256"] in text and comp["authority_review_sha256"] in text
    assert "application:a1" in text and "not_assessed" in text and "unresolved" in text
    quote = comp["authority_review_snapshot"]["context_snapshot"]["manifest"]["sources"][0]["evidence"][
        "text"
    ]
    assert quote in text and "after:synthetic-clause" in text


@pytest.mark.parametrize("change", ["fact", "permission", "head"])
def test_render_time_change_discards_bytes(workbench, monkeypatch, change):
    app, client, _, _, fact, *_ = workbench
    endpoint, *_, permit = setup(workbench, monkeypatch)
    value, _ = saved_comparison(client, endpoint)
    render = comparisons.render_export

    def late(*args):
        response = render(*args)
        if change == "fact":
            mutate(app, fact["id"], lambda data: data.update(text="SYNTHETIC late fact"))
        if change == "permission":
            permit.active = False
        if change == "head":
            saved_comparison(client, endpoint)
        return response

    monkeypatch.setattr(comparisons, "render_export", late)
    response = client.get(endpoint + "/" + value["id"] + "/export?format=docx")
    assert response.status_code == 409 and not response.content.startswith(b"PK")


def test_late_unflushed_dependency_change_rolls_back_record_head_receipt_audit(workbench, monkeypatch):
    app, client, _, _, fact, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    before = payload(app, fact["id"])
    audit = comparisons._audit

    def late(session, *args):
        audit(session, *args)
        row = session.get(Record, fact["id"])
        data = app.state.store.decode(row)
        data["text"] = "SYNTHETIC late fact"
        app.state.store.update(row, data)

    monkeypatch.setattr(comparisons, "_audit", late)
    assert client.post(endpoint, json=body).status_code == 409
    assert (
        count(app, comparisons.KIND) == count(app, comparisons.HEAD) == count(app, comparisons.ADMISSION) == 0
    )
    assert payload(app, fact["id"]) == before
    with app.state.store.session() as session:
        assert not session.scalar(select(Audit).where(Audit.action == "authority_revision_compared"))


def test_postcommit_failure_is_truthful_and_pending_is_not_reopened_by_retry(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    monkeypatch.setattr(
        comparisons, "_finalize", lambda *_: (_ for _ in ()).throw(RuntimeError("private completion failure"))
    )
    response = client.post(endpoint, json=body)
    assert response.status_code == 409 and response.json()["outcome"] == "committed_needs_revalidation"
    ident = response.json()["id"]
    assert "SYNTHETIC" not in response.text
    shown = client.get(endpoint + "/" + ident).json()
    assert shown["snapshot"] is None and shown["freshness"]["reasons"] == [
        "post_commit_authorization_pending"
    ]
    assert client.post(endpoint, json=body).json()["snapshot"] is None
    assert client.get(endpoint + "/" + ident + "/export").status_code == 409


def test_scope_role_csrf_archive_bounds_and_integrity(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, _, _, candidate, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post(endpoint, json=body).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.get(endpoint + "?limit=21").status_code == 422
    assert client.post(endpoint, json={**body, "candidate_version_id": "foreign"}).status_code == 404
    monkeypatch.setattr(comparisons, "MAX_BYTES", 300)
    assert client.post(endpoint, json=body).status_code == 409 and count(app, comparisons.KIND) == 0
    monkeypatch.setattr(comparisons, "MAX_BYTES", 4 * 1024 * 1024)
    value, _ = saved_comparison(client, endpoint, body)
    mutate(app, base.split("/")[-1], lambda data: data.update(status="archived"))
    assert not client.get(endpoint + "/context").json()["can_record"]
    assert client.post(endpoint, json={**body, "request_id": uuid4().hex}).status_code == 409
    mutate(app, value["id"], lambda data: data.update(sequence=999))
    assert client.get(endpoint + "/" + value["id"]).status_code == 409
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        session.delete(session.get(Membership, (base.split("/")[-1], user.id)))
        session.commit()
    assert (
        client.get(endpoint).status_code == 404
        and client.get(endpoint + "/" + value["id"]).status_code == 404
    )


def test_removed_targets_and_explicit_replacement_mapping_are_retained_without_inferred_equivalence(workbench, monkeypatch):
    _, client, base, original, *_ = workbench
    reviews, _, analysis, *_ = findings_setup(workbench, monkeypatch)
    review, _ = saved(client, reviews)
    draft = copy.deepcopy(original)
    draft['rules'][0]['id'] = 'r2'
    draft['applications'][0].update(id='a2', rule_id='r2')
    draft['conclusion']['application_ids'] = ['a2']
    response = client.post(base + '/analyses/' + analysis['id'] + '/versions', json={**draft,
        'expected_revision': analysis['revision'], 'change_note': 'SYNTHETIC explicit replacement'})
    assert response.status_code == 201, response.text
    endpoint = reviews + '/' + review['id'] + '/comparisons'
    body, capture = request(client, endpoint, outcome='removed')
    assert {'rule:r1', 'application:a1'} <= {item['target_id'] for item in capture['comparison']['changes'] if item['after'] is None}
    for item in body['dispositions']:
        item['after_target_ids'] = []
    value, _ = saved_comparison(client, endpoint, body)
    assert value['snapshot']['assessment']['dispositions'][0]['outcome'] == 'removed'
    replacement, _ = request(client, endpoint, outcome='addressed')
    for item in replacement['dispositions']:
        item['after_target_ids'] = ['rule:r2', 'application:a2']
    mapped, _ = saved_comparison(client, endpoint, replacement)
    assert mapped['snapshot']['assessment']['dispositions'][0]['after_target_ids'] == ['rule:r2', 'application:a2']
    assert not mapped['qualification_granted']


def test_actual_signed_source_remains_exact_and_revocation_withholds_comparison_notes(workbench, monkeypatch, tmp_path):
    from test_analysis_authorities import freeze
    from test_analysis_authority_release import signed_source

    _, client, base, *_ = workbench
    contexts, spec, _, permission, prepared = signed_source(workbench, monkeypatch, tmp_path / 'signed-comparison')
    context, _ = freeze(client, contexts, spec)
    reviews = contexts + '/' + context['id'] + '/reviews'
    review, _ = saved(client, reviews)
    analysis = client.get(base + '/analyses').json()[0]
    revise(workbench, analysis)
    endpoint = reviews + '/' + review['id'] + '/comparisons'
    value, _ = saved_comparison(client, endpoint)
    source = value['snapshot']['comparison_snapshot']['authority_review_snapshot']['context_snapshot']['manifest']['sources'][0]
    evidence = source['evidence']
    assert evidence['text'] == prepared['snapshot']['package'].text[evidence['start_offset']:evidence['end_offset']]
    assert source['temporal_alignment']['target_version_within_interval'] is False
    permission.active = False
    shown = client.get(endpoint + '/' + value['id'])
    assert shown.status_code == 200 and shown.json()['snapshot'] is None and 'SYNTHETIC' not in shown.text
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409


@pytest.mark.parametrize('phase', ['save', 'export'])
def test_current_membership_loss_prevents_partial_content_or_save(workbench, monkeypatch, phase):
    app, client, base, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    value, _ = saved_comparison(client, endpoint)
    def revoke(session):
        session.query(Membership).filter(Membership.matter_id == base.split('/')[-1]).delete()
        session.flush()
    if phase == 'save':
        body, _ = request(client, endpoint)
        audit = comparisons._audit
        def late(session, *args):
            audit(session, *args)
            revoke(session)
        monkeypatch.setattr(comparisons, '_audit', late)
        response = client.post(endpoint, json=body)
        assert response.status_code == 404 and 'SYNTHETIC' not in response.text
        assert count(app, comparisons.KIND) == 1
    else:
        def render(*_):
            with app.state.store.session() as session:
                revoke(session)
                session.commit()
            from fastapi import Response
            return Response(b'PRIVATE PARTIAL ATTACHMENT')
        monkeypatch.setattr(comparisons, 'render_export', render)
        response = client.get(endpoint + '/' + value['id'] + '/export?format=docx')
        assert response.status_code == 404 and 'PRIVATE PARTIAL' not in response.text
