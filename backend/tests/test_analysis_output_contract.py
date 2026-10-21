"""Invented responses only; no operator provider, account or matter access."""

import copy
import json

import httpx
import pytest
from test_provider_runtime import relay, settings, transport

from app.analysis_output_contract import (
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


@pytest.mark.parametrize("finish,raw,code", [
    ("length", json.dumps(output()), "provider_output_incomplete"),
    ("stop", '{"synthetic":"wrong contract"}', "provider_output_contract_invalid"),
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
