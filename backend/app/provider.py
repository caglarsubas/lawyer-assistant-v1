import hashlib
import ipaddress
import json
import re
import time
from urllib.parse import urlsplit

import httpx

from .evidence_prompt import measure_prompt, quote_messages

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
))
MAX_RESPONSE_BYTES = 1024 * 1024
RESPONSE_BUDGET_SECONDS = 120
TUNNEL_RELAY_BASE = 'http://172.30.240.2:8083/v1'
ROUTE_DOMAIN = 'lawyer-assistant:provider-tunnel:v1\0'
DNS_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')


class ProviderError(Exception):
    pass


class TunnelConfigurationError(ProviderError):
    pass


class Provider:
    def __init__(self, settings):
        self.settings = settings

    @property
    def configured(self):
        s = self.settings
        return bool(s.provider_base_url and s.provider_api_key and s.provider_model)

    @property
    def transport_mode(self):
        s = self.settings
        return ('approved_laptop_tunnel' if (getattr(s, 'provider_tunnel_url', '')
                or getattr(s, 'provider_tunnel_approved', False)
                or getattr(s, 'provider_tunnel_approved_host', '')) else 'private_network')

    def transport_metadata(self):
        public = self.transport_mode == 'approved_laptop_tunnel'
        result = {'mode': self.transport_mode, 'uses_public_network': public}
        if public:
            result['air_gapped'] = False
        return result

    def _tunnel_contract(self):
        if self.transport_mode == 'private_network':
            return None
        s = self.settings
        host = getattr(s, 'provider_tunnel_approved_host', '')
        target = getattr(s, 'provider_tunnel_url', '')
        try:
            if (getattr(s, 'provider_tunnel_approved', False) is not True
                    or not isinstance(host, str) or not 1 <= len(host) <= 253
                    or host != host.lower() or len(host.split('.')) < 2
                    or any(not DNS_LABEL.fullmatch(label) for label in host.split('.'))):
                raise ValueError('Incomplete tunnel approval')
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError('A tunnel requires an exact approved DNS hostname')
            if (target not in {f'https://{host}/v1', f'https://{host}:443/v1'}
                    or s.provider_base_url != TUNNEL_RELAY_BASE):
                raise ValueError('Tunnel URL or private relay differs from the approved route')
        except (TypeError, ValueError):
            raise TunnelConfigurationError('The approved tunnel configuration is incomplete or invalid') from None
        canonical = f'https://{host}/v1'
        return {'mode': 'approved_laptop_tunnel', 'upstream_origin': f'https://{host}',
                'route_sha256': hashlib.sha256((ROUTE_DOMAIN + canonical).encode('utf-8')).hexdigest()}

    def _route_headers(self):
        route = self._tunnel_contract()
        return {'X-Provider-Route': route['route_sha256']} if route else {}

    def _verify_transport(self, payload):
        if not isinstance(payload, dict):
            raise ProviderError('Provider transport metadata is invalid')
        expected = self._tunnel_contract()
        observed = payload.get('relay_transport')
        if expected is not None:
            if observed != expected:
                raise ProviderError('The response did not use the approved tunnel route')
        elif observed is not None and observed != {'mode': 'native_private', 'upstream_origin': None}:
            raise ProviderError('An unapproved provider transport was rejected')

    def configuration_issues(self):
        """Static diagnostics only: never connect or reflect configuration values."""
        s = self.settings
        issues = []
        required = (
            (s.provider_base_url, "provider_url_missing", "Yerel sağlayıcı adresi eksik."),
            (s.provider_api_key, "provider_key_missing", "Sağlayıcı API anahtarı eksik."),
            (s.provider_model, "provider_model_missing", "Kullanılacak yerel model seçilmedi."),
        )
        for value, code, message in required:
            if not value or not value.strip():
                issues.append({"code": code, "message": message})
        if (s.provider_base_url and s.provider_base_url.strip()) or self.transport_mode != 'private_network':
            try:
                self.validate_origin()
            except TunnelConfigurationError:
                issues.append({
                    'code': 'provider_tunnel_configuration_invalid',
                    'message': 'Tünel istisnası için tam hedef, açık onay ve sabit özel aktarıcı eşleşmelidir.',
                })
            except ProviderError:
                issues.append({
                    "code": "provider_origin_prohibited",
                    "message": "Sağlayıcı adresi izin verilen yerel bağlantı kurallarına uymuyor. "
                    "Onaylı özel IP adresi ve uygun aktarım ayarı gerekir.",
                })
        if not s.provider_identity_verified:
            issues.append({
                "code": "provider_identity_unverified",
                "message": "API anahtarının beklenen kiracı, kuruluş ve anahtar kimliğiyle eşleştiği doğrulanmadı.",
            })
        if not getattr(s, "provider_cloud_fallback_disabled", False):
            issues.append({
                "code": "provider_cloud_fallback_unverified",
                "message": "Sağlayıcının bulut yedeklemesine kapalı olduğu doğrulanmadı.",
            })
        if s.provider_context_limit <= 0:
            issues.append({
                "code": "provider_context_invalid",
                "message": "Sağlayıcı bağlam sınırı pozitif bir değer olmalıdır.",
            })
        return issues

    def readiness(self):
        """A valid configuration is not runtime authentication or model qualification."""
        issues = self.configuration_issues()
        return {"configuration_ready": not issues, "verification_scope": "configuration_only", "issues": issues,
                'transport': self.transport_metadata()}

    def _base(self):
        base = self.settings.provider_base_url.rstrip("/")
        return base if base.endswith("/v1") else base + "/v1"

    def probe(self):
        """Bounded live authentication/model discovery, never an inference call.

        Tenant binding and absence of cloud fallback remain operator attestations;
        the engine's model listing cannot independently establish either fact.
        """
        issues = self.configuration_issues()
        result = {"ready": False, "verification_scope": "authenticated_model_metadata", "issues": issues,
                  "checks": {"configuration": not issues, "connection": False, "model": False},
                  'transport': self.transport_metadata()}
        if issues:
            return result
        try:
            with httpx.Client(timeout=httpx.Timeout(5, connect=3), follow_redirects=False, trust_env=False) as client:
                with client.stream("GET", self._base() + "/models", headers={
                    "Authorization": f"Bearer {self.settings.provider_api_key}", "Accept-Encoding": "identity",
                    **self._route_headers(),
                }) as response:
                    if response.status_code != 200:
                        code = "provider_authentication_failed" if response.status_code in (401, 403) else "provider_unavailable"
                        result["issues"] = [{"code": code, "message": "Yerel sağlayıcı doğrulaması tamamlanamadı."}]
                        return result
                    result["checks"]["connection"] = True
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ValueError("compressed metadata")
                    body = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_bytes():
                        if time.monotonic() - started > 10 or len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ValueError("metadata budget exceeded")
                        body.extend(chunk)
            payload = json.loads(body)
            try:
                self._verify_transport(payload)
            except ProviderError:
                result['issues'] = [{'code': 'provider_transport_mismatch',
                                     'message': 'Sağlayıcı aktarım yolu beklenen onaylı yapılandırmayla eşleşmedi.'}]
                return result
            models = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(models, list):
                raise ValueError("invalid model listing")
            matches = [item for item in models if isinstance(item, dict) and item.get("id") == self.settings.provider_model]
            if len(matches) != 1:
                result["issues"] = [{"code": "provider_model_unavailable", "message": "Seçilen model sağlayıcıda bulunamadı."}]
                return result
            model = matches[0]
            # Only adapters whose execution is local are admitted. A local HTTP
            # engine can advertise remote OpenRouter and vLLM upstreams too.
            if (model.get("request_key_source") != "local-inference"
                    or model.get("backend") not in {"llama_cpp", "ollama_http", "mlx"}
                    or model.get("format") not in {"gguf", "ollama_http", "mlx"}):
                result["issues"] = [{"code": "provider_model_not_local", "message": "Seçilen model yerel çıkarım koşullarını karşılamıyor."}]
                return result
            context = model.get("max_model_len")
            if type(context) is not int or context <= 0 or self.settings.provider_context_limit > context:
                result["issues"] = [{"code": "provider_context_unverified", "message": "Yapılandırılan bağlam sınırı sağlayıcı kapasitesiyle doğrulanamadı."}]
                return result
            result.update(ready=True, model={"id": model["id"], "backend": model["backend"], "context_limit": context})
            result["checks"]["model"] = True
            return result
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            result["issues"] = [{"code": "provider_probe_failed", "message": "Yerel sağlayıcı yanıtı güvenle doğrulanamadı."}]
            return result

    def validate_origin(self):
        s = self.settings
        self._tunnel_contract()
        try:
            url = urlsplit(s.provider_base_url)
            port = url.port
            address = ipaddress.ip_address(url.hostname or "")
        except ValueError as exc:
            raise ProviderError("Provider must use a vetted private IP literal and valid port") from exc
        if (url.scheme not in ("http", "https") or url.username or url.password or url.query or url.fragment
                or port == 0 or url.path.rstrip("/") not in ("", "/v1")
                or s.provider_base_url != s.provider_base_url.strip()
                or any(ord(char) < 32 or ord(char) == 127 for char in s.provider_base_url)
                or "\\" in s.provider_base_url or "%" in (url.hostname or "")):
            raise ProviderError("Invalid internal provider URL")
        if url.scheme == "http" and not s.provider_allow_plain_http:
            raise ProviderError("Plain HTTP requires explicit private-network configuration")
        # A DNS preflight followed by httpx hostname resolution is vulnerable to
        # rebinding. This first adapter accepts IP literals only; hostname/SNI
        # support needs a transport that pins the actual checked connection.
        private = address.is_loopback or any(address in network for network in PRIVATE_NETWORKS)
        if (not private or address.is_link_local or address.is_unspecified or address.is_multicast
                or (address.is_reserved and not address.is_loopback)
                or getattr(address, "ipv4_mapped", None) is not None):
            raise ProviderError("External inference destinations are prohibited")

    def generate(self, question, passages):
        try:
            messages = quote_messages(question, passages)
            measured = measure_prompt(question, passages)
        except (ValueError, TypeError):
            raise ProviderError("Invalid private quotation context") from None
        return self._complete(messages, 1000, measured["total_upper_bound_units"])

    def suggest_analysis(self, content, *, repair=False, budget_seconds=120, review_feedback=None):
        from .analysis_proposals import COMPLETION_TOKENS, prompt_measurement, proposal_messages
        try:
            messages = proposal_messages(content, repair=repair, review_feedback=review_feedback)
            measured = prompt_measurement(messages)
        except (ValueError, TypeError, KeyError):
            raise ProviderError("Invalid private analysis context") from None
        if not 0 < budget_seconds <= RESPONSE_BUDGET_SECONDS:
            raise ProviderError("Invalid analysis inference time budget")
        return self._complete(messages, COMPLETION_TOKENS, measured["total_upper_bound_units"],
                              budget_seconds=budget_seconds, response_bytes=65536)

    def _complete(self, messages, completion_tokens, context_units, *,
                  budget_seconds=RESPONSE_BUDGET_SECONDS, response_bytes=MAX_RESPONSE_BYTES):
        s = self.settings
        if not self.configured:
            raise ProviderError("Provider is not configured")
        if not s.provider_identity_verified:
            raise ProviderError("Provider tenant binding has not been attested")
        if not getattr(s, "provider_cloud_fallback_disabled", False):
            raise ProviderError("Provider cloud fallback isolation has not been attested")
        self.validate_origin()
        # High-level workflows construct and measure their fixed envelope. Source
        # metadata and retained private manifests never become arbitrary messages.
        if context_units > s.provider_context_limit:
            raise ProviderError("Context budget exceeded; reduce selected evidence")
        started = time.monotonic()
        if not self.probe()["ready"]:
            raise ProviderError("Provider authentication and local model readiness could not be verified")
        headers = {"Authorization": f"Bearer {s.provider_api_key}", "x-engine-model-substitution": "off",
                   "Accept-Encoding": "identity", **self._route_headers()}
        base = self._base()
        deadline = started + budget_seconds
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("Provider readiness exceeded the total time budget")
        try:
            with httpx.Client(timeout=httpx.Timeout(min(90, remaining), connect=min(5, remaining)), follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", base + "/chat/completions", headers=headers, json={
                    "model": s.provider_model, "messages": messages, "temperature": 0,
                    "max_completion_tokens": completion_tokens, "stream": False, "response_format": {"type": "json_object"},
                }) as response:
                    if response.status_code != 200:
                        raise ProviderError(f"Provider returned HTTP {response.status_code}")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ProviderError("Compressed provider responses are not admitted")
                    payload = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise ProviderError("Provider response exceeded the total time budget")
                        if len(payload) + len(chunk) > response_bytes:
                            raise ProviderError("Provider response exceeded the bounded response size")
                        payload.extend(chunk)
            if time.monotonic() >= deadline:
                raise ProviderError("Provider response exceeded the total time budget")
            result = json.loads(payload)
            if not isinstance(result, dict):
                raise ProviderError("Provider response must be an object")
            self._verify_transport(result)
            if result.get("model") != s.provider_model:
                raise ProviderError("Served model identity did not match configured model")
            if (any(result.get(key) for key in ("fallback_from_model", "fallback_reason", "substitution_reason"))
                    or result.get("request_key_source", "local-inference") != "local-inference"):
                raise ProviderError("Provider fallback or external inference result was rejected")
            choices = result.get("choices")
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise ProviderError("Provider must return exactly one completion")
            choice = choices[0]
            if choice.get("finish_reason") != "stop" or not isinstance(choice.get("message"), dict):
                raise ProviderError("Provider output was incomplete")
            content = choice["message"].get("content")
            if not isinstance(content, str) or not content.strip() or choice["message"].get("tool_calls"):
                raise ProviderError("Provider returned an unsupported content shape")
            return content
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError, RecursionError) as exc:
            raise ProviderError("Provider response could not be safely consumed") from exc
