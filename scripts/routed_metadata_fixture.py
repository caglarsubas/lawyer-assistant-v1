"""Fixed synthetic HTTP behavior. No sockets, keys, inference or persisted settings."""
import httpx
from provider_binding_fixture import provider
from routed_metadata_diagnostics import diagnose

SENTINEL = "SYNTHETIC-PRIVATE-SENTINEL-MUST-NOT-ESCAPE"


class Fixture:
    def __init__(self, mode):
        self.mode, self.provider, self.requests = mode, provider(), []

    def serve(self, request):
        self.requests.append(request)
        payload = {"data": [{"id": self.provider.settings.provider_model, "backend": "ollama_http", "format": "ollama_http",
                             "max_model_len": 32768, "request_key_source": "local-inference"}]}
        mode = self.mode
        if mode == "relay_connection_closed":
            return httpx.Response(502, json={"code": "provider_connection_closed", "error": SENTINEL})
        if mode == "foreign_error_code":
            return httpx.Response(401, json={"code": SENTINEL, "error": SENTINEL})
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://invalid.example/" + SENTINEL}, text=SENTINEL)
        if mode == "read_timeout":
            raise httpx.ReadTimeout(SENTINEL)
        if mode == "invalid_json":
            return httpx.Response(200, content=SENTINEL)
        if mode == "foreign_route":
            payload["relay_transport"] = {"mode": SENTINEL}
        if mode == "absent_model":
            payload["data"] = []
        if mode == "small_context":
            payload["data"][0]["max_model_len"] = 128
        if mode == "oversized":
            return httpx.Response(200, content=b"x" * (1024 * 1024 + 1))
        if mode == "encoded":
            return httpx.Response(200, headers={"content-encoding": "custom"}, content=SENTINEL)
        if mode == "changed_config":
            self.provider.settings.provider_key_id = "changed-synthetic-key-id"
        return httpx.Response(200, json=payload)

    def client(self, **options):
        return httpx.Client(transport=httpx.MockTransport(self.serve), **options)

    def run(self):
        return diagnose(self.provider, client=self.client)
