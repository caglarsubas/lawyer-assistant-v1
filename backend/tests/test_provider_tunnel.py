"""Explicit tunnel exception tests; synthetic secrets, no DNS or live provider."""

import hashlib
import json
import socket
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.provider import Provider, ProviderError

HOST = 'fixture-tunnel.example'
URL = f'https://{HOST}/v1'
BASE = 'http://172.30.240.2:8083/v1'
ROUTE = {'mode': 'approved_laptop_tunnel', 'upstream_origin': f'https://{HOST}',
         'route_sha256': hashlib.sha256(('lawyer-assistant:provider-tunnel:v1\0' + URL).encode()).hexdigest()}
CLIENT = httpx.Client


def settings(**changes):
    values = dict(provider_base_url=BASE, provider_api_key='SYNTHETIC-NOT-A-REAL-KEY',
                  provider_model='test-local-model', provider_context_limit=8192,
                  provider_identity_verified=True, provider_cloud_fallback_disabled=True,
                  provider_allow_plain_http=True, provider_tunnel_url=URL,
                  provider_tunnel_approved=True, provider_tunnel_approved_host=HOST)
    return SimpleNamespace(**{**values, **changes})


def model(**changes):
    return {'id': 'test-local-model', 'backend': 'ollama_http', 'format': 'ollama_http',
            'request_key_source': 'local-inference', 'max_model_len': 32768, **changes}


def output(**changes):
    return {'model': 'test-local-model', 'choices': [{'finish_reason': 'stop',
            'message': {'content': '{"claims":[]}'}}], 'relay_transport': ROUTE, **changes}


def transport(monkeypatch, models=None, completion=None):
    seen = []
    def respond(request):
        seen.append(request)
        payload = (models if models is not None else {'data': [model()], 'relay_transport': ROUTE}) if request.method == 'GET' else (completion if completion is not None else output())
        return httpx.Response(200, json=payload)
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return CLIENT(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(httpx, 'Client', client)
    return seen


def forbid(*args, **kwargs):
    raise AssertionError('Invalid configuration must not resolve or connect')


def test_tunnel_exception_is_disabled_by_default_and_aliases_are_explicit(monkeypatch):
    for name in ('LLM_PROVIDER_TUNNEL_URL', 'LLM_PROVIDER_TUNNEL_APPROVED', 'LLM_PROVIDER_TUNNEL_APPROVED_HOST'):
        monkeypatch.delenv(name, raising=False)
    default = Settings(_env_file=None)
    assert default.provider_tunnel_url == default.provider_tunnel_approved_host == ''
    assert default.provider_tunnel_approved is False
    configured = Settings(_env_file=None, LLM_PROVIDER_TUNNEL_URL=URL,
                          LLM_PROVIDER_TUNNEL_APPROVED=True, LLM_PROVIDER_TUNNEL_APPROVED_HOST=HOST)
    assert configured.provider_tunnel_url == URL and configured.provider_tunnel_approved
    assert configured.provider_tunnel_approved_host == HOST


@pytest.mark.parametrize('url', [URL, f'https://{HOST}:443/v1'])
def test_exact_approved_route_uses_private_relay_and_canonical_fingerprint_without_dns(monkeypatch, url):
    monkeypatch.setattr(socket, 'getaddrinfo', forbid)
    monkeypatch.setattr(httpx, 'Client', forbid)
    provider = Provider(settings(provider_tunnel_url=url))
    provider.validate_origin()
    assert provider._tunnel_contract() == ROUTE
    readiness = provider.readiness()
    assert readiness['configuration_ready']
    assert readiness['transport'] == {'mode': 'approved_laptop_tunnel', 'uses_public_network': True,
                                     'air_gapped': False}
    assert HOST not in str(readiness) and ROUTE['route_sha256'] not in str(readiness)


@pytest.mark.parametrize('changes', [
    {'provider_tunnel_url': ''}, {'provider_tunnel_approved': False}, {'provider_tunnel_approved': 'true'},
    {'provider_tunnel_approved_host': ''}, {'provider_tunnel_approved_host': HOST.upper()},
    {'provider_tunnel_approved_host': HOST + '.'}, {'provider_tunnel_approved_host': ' localhost'},
    {'provider_tunnel_approved_host': 'localhost'}, {'provider_tunnel_approved_host': 'bad_host.example'},
    {'provider_tunnel_approved_host': '1.2.3.4', 'provider_tunnel_url': 'https://1.2.3.4/v1'},
    {'provider_tunnel_approved_host': 'a' * 64 + '.example'},
    {'provider_tunnel_url': 'http://' + HOST + '/v1'},
    {'provider_tunnel_url': 'https://' + HOST + ':8443/v1'},
    {'provider_tunnel_url': URL + '/'}, {'provider_tunnel_url': URL + '?secret=PRIVATE'},
    {'provider_tunnel_url': URL + '#PRIVATE'}, {'provider_tunnel_url': URL + '/chat/completions'},
    {'provider_tunnel_url': 'https://' + HOST + '/x/../v1'},
    {'provider_tunnel_url': 'https://' + HOST + '/%76%31'},
    {'provider_tunnel_url': 'https://' + HOST + '\\v1'},
    {'provider_tunnel_url': 'https://user:PRIVATE@' + HOST + '/v1'},
    {'provider_tunnel_url': 'https://' + HOST + '.attacker.example/v1'},
    {'provider_tunnel_url': ' ' + URL}, {'provider_tunnel_url': URL + '\r\nPRIVATE'},
    {'provider_base_url': URL}, {'provider_base_url': BASE + '/'},
    {'provider_base_url': 'http://10.20.0.8:8083/v1'},
    {'provider_base_url': 'https://172.30.240.2:8083/v1'},
    {'provider_allow_plain_http': False},
])
def test_partial_ambiguous_or_unbound_exception_fails_before_network(monkeypatch, changes):
    monkeypatch.setattr(socket, 'getaddrinfo', forbid)
    monkeypatch.setattr(httpx, 'Client', forbid)
    provider = Provider(settings(**changes))
    assert not provider.probe()['ready']
    with pytest.raises(ProviderError):
        provider.generate('SYNTHETIC DOCUMENT', [])
    assert 'PRIVATE' not in json.dumps(provider.readiness())


@pytest.mark.parametrize('url', ['https://8.8.8.8/v1', 'https://other.example/v1', URL])
@pytest.mark.parametrize('approved', [False, True])
def test_tunnel_exception_never_grants_direct_external_url_access(monkeypatch, url, approved):
    monkeypatch.setattr(httpx, 'Client', forbid)
    monkeypatch.setattr(socket, 'getaddrinfo', forbid)
    provider = Provider(settings(provider_base_url=url, **({} if approved else {
        'provider_tunnel_url': '', 'provider_tunnel_approved': False, 'provider_tunnel_approved_host': ''})))
    assert not provider.probe()['ready']
    with pytest.raises(ProviderError):
        provider.generate('SYNTHETIC DOCUMENT', [])


def test_route_binding_is_sent_on_models_and_completion_and_is_not_public_metadata(monkeypatch):
    seen = transport(monkeypatch)
    provider = Provider(settings())
    assert provider.generate('SYNTHETIC DOCUMENT', []) == '{"claims":[]}'
    assert [request.url.path for request in seen] == ['/v1/models', '/v1/chat/completions']
    assert all(request.url.host == '172.30.240.2' and request.url.port == 8083 for request in seen)
    assert all(request.headers['X-Provider-Route'] == ROUTE['route_sha256'] for request in seen)
    assert seen[1].headers['x-engine-model-substitution'] == 'off'


@pytest.mark.parametrize('observed', [None, {}, {'mode': 'native_private', 'upstream_origin': None},
    {**ROUTE, 'upstream_origin': 'https://different.example'}, {**ROUTE, 'route_sha256': '0' * 64},
    {**ROUTE, 'private_extra': 'PRIVATE-DETAIL'}])
def test_response_route_mismatch_blocks_probe_and_completion(monkeypatch, observed):
    seen = transport(monkeypatch, models={'data': [model()], 'relay_transport': observed})
    provider = Provider(settings())
    result = provider.probe()
    assert not result['ready'] and result['issues'][0]['code'] == 'provider_transport_mismatch'
    assert 'PRIVATE' not in json.dumps(result)
    assert all(request.method == 'GET' for request in seen)
    transport(monkeypatch, completion=output(relay_transport=observed))
    with pytest.raises(ProviderError, match='approved tunnel'):
        provider.generate('SYNTHETIC DOCUMENT', [])


@pytest.mark.parametrize('native_metadata', [None, {'mode': 'native_private', 'upstream_origin': None}])
def test_native_route_remains_compatible_without_tunnel_headers(monkeypatch, native_metadata):
    seen = transport(monkeypatch, models={'data': [model()], 'relay_transport': native_metadata},
                     completion=output(relay_transport=native_metadata))
    provider = Provider(settings(provider_tunnel_url='', provider_tunnel_approved=False, provider_tunnel_approved_host=''))
    assert provider.generate('SYNTHETIC DOCUMENT', []) == '{"claims":[]}'
    assert all('X-Provider-Route' not in request.headers for request in seen)
    assert provider.transport_mode == 'private_network'


def test_unconfigured_tunnel_advertisement_cannot_become_a_silent_exception(monkeypatch):
    transport(monkeypatch)
    provider = Provider(settings(provider_tunnel_url='', provider_tunnel_approved=False, provider_tunnel_approved_host=''))
    assert provider.probe()['issues'][0]['code'] == 'provider_transport_mismatch'
    with pytest.raises(ProviderError):
        provider.generate('SYNTHETIC DOCUMENT', [])


@pytest.mark.parametrize('change', [{'backend': 'openrouter', 'format': 'openrouter'},
                                  {'request_key_source': 'openrouter-api-key'}, {'max_model_len': 4096}])
def test_tunnel_does_not_relax_local_model_or_context_controls(monkeypatch, change):
    seen = transport(monkeypatch, models={'data': [model(**change)], 'relay_transport': ROUTE})
    provider = Provider(settings())
    assert not provider.probe()['ready']
    with pytest.raises(ProviderError):
        provider.generate('SYNTHETIC DOCUMENT', [])
    assert all(request.method == 'GET' for request in seen)


@pytest.mark.parametrize('field', ['provider_identity_verified', 'provider_cloud_fallback_disabled'])
def test_tunnel_keeps_tenant_and_no_fallback_attestation_required(monkeypatch, field):
    monkeypatch.setattr(httpx, 'Client', forbid)
    provider = Provider(settings(**{field: False}))
    assert not provider.probe()['ready']
    with pytest.raises(ProviderError):
        provider.generate('SYNTHETIC DOCUMENT', [])
