"""The only Internet-facing process; bounded HTTPS GET, pinned DNS, no redirects."""

import base64
import hashlib
import hmac
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import quote_plus, urlsplit

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .config import load_settings
from .policy import evaluate

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class FetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(max_length=500)
    destination: str = Field(max_length=500)


@app.post("/fetch")
def fetch(body: FetchRequest, authorization: str = Header(default="")):
    settings = load_settings()
    if not settings.gateway_token or not hmac.compare_digest(
        authorization, "Bearer " + settings.gateway_token
    ):
        raise HTTPException(401, "Unauthorized")
    if not settings.gateway_enabled:
        raise HTTPException(503, "External acquisition disabled")
    verdict = evaluate(body.query, body.destination, "public", settings.gateway_allowlist.split(","))
    if verdict["decision"] != "ALLOW":
        raise HTTPException(403, "Request denied")
    url = urlsplit(body.destination)
    try:
        addresses = socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("Nonpublic destination")
        address = addresses[0]
        raw = socket.socket(address[0], socket.SOCK_STREAM)
        raw.settimeout(10)
        raw.connect(address[4])
        with ssl.create_default_context().wrap_socket(raw, server_hostname=url.hostname) as stream:
            path = (url.path or "/") + "?q=" + quote_plus(body.query)
            request = f"GET {path} HTTP/1.1\r\nHost: {url.hostname}\r\nUser-Agent: LawyerAssistant/0.1\r\nAccept: text/html,text/plain\r\nConnection: close\r\n\r\n"
            stream.sendall(request.encode("ascii"))
            response = http.client.HTTPResponse(stream)
            response.begin()
            if response.status != 200:
                raise ValueError("Redirects, challenges and non-success responses are not followed")
            media_type = response.getheader("Content-Type", "").split(";")[0]
            if media_type not in ("text/html", "text/plain"):
                raise ValueError("Unsupported public media type")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("Compressed sources require a separate qualified decoder")
            content = bytearray()
            deadline = time.monotonic() + 12
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("Acquisition time budget exceeded")
                stream.settimeout(min(5, remaining))
                chunk = response.read1(8192)
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > 512 * 1024:
                    raise ValueError("Response too large")
        return {
            "source_url": body.destination,
            "query": body.query,
            "media_type": media_type,
                "sha256": hashlib.sha256(content).hexdigest(),
            "content_base64": base64.b64encode(content).decode(),
            "status": "quarantined",
            "rights_status": "unverified",
        }
    except (OSError, ValueError, http.client.HTTPException):
        raise HTTPException(502, "Source could not be safely acquired") from None


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, access_log=False)
