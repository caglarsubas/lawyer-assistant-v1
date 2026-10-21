"""Invented responses only; no operator provider, account or matter access."""

import copy
import json

import httpx
import pytest
from test_provider_runtime import relay, settings, transport

from app.analysis_output_contract import (
    PROSE_LIMIT,
    ProseValidationError,
    admitted_response_format,
    analysis_response_format,
    validate_analysis_output,
)
from app.analysis_proposals import FRAMING_RESERVE, prompt_measurement
from app.provider import Provider, ProviderError


def output():
    return {"application_updates": [{"id": "a1", "rationale": "SYNTHETIC: review the original.", "assessments": []}],
            "conclusion_update": None, "review_notes": []}


@pytest.mark.parametrize("review,authority", [(False, False), (True, False), (False, True), (True, True)])
def test_only_four_finite_local_contracts_are_admitted(review, authority):
    form = analysis_response_format(review, authority)
    assert admitted_response_format(form)
    body = {"model": "local-model", "messages": [{"role": "user", "content": "SYNTHETIC"}],
            "temperature": 0, "max_completion_tokens": 1000, "stream": False, "response_format": form}
    assert relay.valid_completion(body, "local-model")
    result = output()
    if review:
        result["feedback_responses"] = []
    if authority:
        result["authority_responses"] = []
    validate_analysis_output(json.dumps(result), form)
    for mutate in (lambda v: v["json_schema"].update(strict=1),
                   lambda v: v["json_schema"]["schema"].update(additionalProperties=True),
                   lambda v: v["json_schema"]["schema"].update({"$ref": "https://external.invalid/schema"}),
                   lambda v: v["json_schema"]["schema"]["$defs"]["t"].pop("pattern"),
                   lambda v: v["json_schema"].update(name="private_analysis_v1"),
                   lambda v: v["json_schema"]["schema"]["$defs"]["t"].update(maxLength=100000)):
        changed = copy.deepcopy(form)
        mutate(changed)
        assert not admitted_response_format(changed)
        assert not relay.valid_completion({**body, "response_format": changed}, "local-model")


@pytest.mark.parametrize("raw", [
    '{"application_updates":[],',
    '{"application_updates":[],"conclusion_update":null,"review_notes":[],"invented":true}',
    '{"application_updates":[],"application_updates":[],"conclusion_update":null,"review_notes":[]}',
    json.dumps({**output(), "review_notes": [{"target_id": "a1", "text": "x" * 401, "evidence_ids": []}]}),
    json.dumps({**output(), "application_updates": [{"id": "a1", "rationale": "ok", "assessments": [
        {"condition_id": "c1", "status": True, "premise_ids": []}]}]}),
    json.dumps({**output(), "application_updates": output()["application_updates"] * 13}),
])
def test_upstream_claim_of_structured_output_does_not_bypass_independent_validation(raw):
    with pytest.raises(ValueError):
        validate_analysis_output(raw, analysis_response_format())


def test_exact_contract_is_in_the_context_budget_and_fingerprint():
    messages = [{"role": "system", "content": "SYNTHETIC"}, {"role": "user", "content": '{"draft":{}}'}]
    measured = prompt_measurement(messages)
    contract = json.dumps(analysis_response_format(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert measured["response_contract_utf8_bytes"] == len(contract)
    assert measured["total_upper_bound_units"] == measured["utf8_bytes"] + len(contract) + FRAMING_RESERVE + 1000
    with_review = copy.deepcopy(messages)
    with_review[-1]["content"] = '{"draft":{},"selected_review_findings":[{"finding_id":"finding:0"}]}'
    assert prompt_measurement(with_review)["response_contract_sha256"] != measured["response_contract_sha256"]


@pytest.mark.parametrize("prose", [
    "Madde 73 bu koşulu kanıtlar.", "Sayfa 24 bağımsız bir kuraldır.",
    "The decision applies Article IV.", "IV. madde koşulu karşılar.",
    "Sözleşmenin ５ maddesi uygulanır.", "المادة ٧ تثبت الشرط.",
    "Article Ⅳ is decisive.", "Dayanak ² olarak belirtilmiştir.", "...", "Kabul...", " İnceleyin.",
    "**Kaynakları inceleyin.**", "Kaynakları inceleyin\nve karşılaştırın.",
    "Asıl belgeler doğrulanmadan ancak", "Asıl belgeler doğrulanmadan ancak.",
    "The evidence is needed because.",
    "İlk cümle tamamlandı. İkinci cümle yarım",
    "Kaynak incelendi; koşul bilinmiyor.", "m.NUM incelenmelidir.", "ev.ABC kaynak olarak gösterildi.",
    "x" * (PROSE_LIMIT - 1) + ".",
])
def test_prose_never_introduces_numbered_locators_or_accepts_clipped_fields(prose):
    value = output()
    value["application_updates"][0]["rationale"] = prose
    with pytest.raises(ProseValidationError):
        validate_analysis_output(json.dumps(value), analysis_response_format())


@pytest.mark.parametrize("field", ["rationale", "conclusion", "uncertainty", "next_step", "note", "feedback", "authority"])
def test_prose_guard_covers_every_editable_text_surface_and_never_edits_the_response(field):
    form = analysis_response_format(review=True, authority=True)
    value = {**output(), "feedback_responses": [], "authority_responses": []}
    broken = "SYNTHETIC — Ancak"
    conclusion = {"text": "Belirsizlik sürüyor.", "uncertainty": [], "next_step": "Asıl belgeyi inceleyin."}
    if field == "rationale":
        value["application_updates"][0]["rationale"] = broken
    elif field in {"conclusion", "uncertainty", "next_step"}:
        value["conclusion_update"] = conclusion
        conclusion[{"conclusion": "text", "uncertainty": "uncertainty", "next_step": "next_step"}[field]] = (
            [broken] if field == "uncertainty" else broken)
    elif field == "note":
        value["review_notes"] = [{"target_id": "a1", "text": broken, "evidence_ids": ["source-73"]}]
    else:
        key = "feedback_responses" if field == "feedback" else "authority_responses"
        value[key] = [{"finding_id": "finding:0" if field == "feedback" else "authority:0:certainty",
                       "outcome": "unresolved", "edited_targets": [], "text": broken,
                       "evidence_ids" if field == "feedback" else "authority_ids": ["source-73"]}]
    raw = json.dumps(value, ensure_ascii=False)
    with pytest.raises(ProseValidationError):
        validate_analysis_output(raw, form)
    assert raw == json.dumps(value, ensure_ascii=False) and broken in raw


def test_identifiers_remain_separate_from_generated_prose():
    result = output()
    result["application_updates"][0]["rationale"] = None
    result["review_notes"] = [{"target_id": "conclusion", "text": "Özgün kaynak ve taraf bağı ayrıca doğrulanmalıdır.",
                               "evidence_ids": ["source-73-page-24"]}]
    validate_analysis_output(json.dumps(result), analysis_response_format())


def test_a_complete_sentence_keeps_its_qualified_reference_punctuation():
    result = output()
    result['application_updates'][0]['rationale'] = 'm.73 ve s.24 birlikte incelenmelidir.'
    validate_analysis_output(json.dumps(result), analysis_response_format())


@pytest.mark.parametrize("finish,raw,code", [
    ("length", json.dumps(output()), "provider_output_incomplete"),
    ("stop", '{"synthetic":"wrong contract"}', "provider_output_contract_invalid"),
    ("stop", json.dumps({**output(), "review_notes": [
        {"target_id": "a1", "text": "Yanıt tamamlanmadan ancak", "evidence_ids": []}]}), "provider_output_prose_boundary"),
])
def test_incomplete_or_wrong_contract_response_is_never_accepted(monkeypatch, finish, raw, code):
    monkeypatch.setattr(Provider, "probe", lambda self: {"ready": True})
    seen = transport(monkeypatch, httpx.Response(200, json={"model": "local-model", "choices": [
        {"finish_reason": finish, "message": {"content": raw}}]}))
    with pytest.raises(ProviderError) as caught:
        Provider(settings())._complete([{"role": "user", "content": "SYNTHETIC"}], 1000, 4000,
                                       response_format=analysis_response_format())
    assert caught.value.code == code and len(seen) == 1
    assert "wrong contract" not in str(caught.value)


@pytest.mark.parametrize("text,reason", [
    ("Madde 73 uygulanır.", "reference"),
    ("İlk cümle bitti. İkincisi yarım", "boundary"),
    ("x" * (PROSE_LIMIT - 1) + ".", "limit"),
    ("**Aslı incelenmelidir.**", "style"),
])
def test_prose_diagnostics_are_finite_categories_without_output_or_identifiers(text, reason):
    value = output()
    value["application_updates"][0]["rationale"] = text
    with pytest.raises(ProseValidationError) as caught:
        validate_analysis_output(json.dumps(value), analysis_response_format())
    assert caught.value.reason == reason and text not in str(caught.value)
    assert "73" not in str(caught.value)


@pytest.mark.parametrize('usage,code', [
    ({'completion_tokens': 1001, 'total_tokens': 2000}, 'provider_reported_budget_exceeded'),
    ({'completion_tokens': 200, 'total_tokens': 999999}, 'provider_reported_budget_exceeded'),
    ({'completion_tokens': True}, 'provider_usage_invalid'),
    ({'completion_tokens': -1}, 'provider_usage_invalid'),
])
def test_reported_usage_overrun_or_invalid_accounting_cannot_publish_a_candidate(monkeypatch, usage, code):
    monkeypatch.setattr(Provider, 'probe', lambda self: {'ready': True})
    seen = transport(monkeypatch, httpx.Response(200, json={'model': 'local-model', 'usage': usage, 'choices': [
        {'finish_reason': 'stop', 'message': {'content': json.dumps(output())}}]}))
    with pytest.raises(ProviderError) as caught:
        Provider(settings())._complete([{'role': 'user', 'content': 'SYNTHETIC'}], 1000, 4000,
                                       response_format=analysis_response_format())
    assert caught.value.code == code and len(seen) == 1
