"""Unregistered staged ASGI route. No server startup, live keys or activation."""

import asyncio
import base64

from signed_provider_contract import (
    CONTRACT,
    EXPECT_FIELDS,
    Issuer,
    decode,
    encode,
    identity,
    lifetime,
    nonce,
    request,
    sha,
)

IDENTITY_PATH = "/staged/v2/identity"
COMPLETION_PATH = "/staged/v2/completions"


class StagedSignedRoute:
    def __init__(self, key, issuer_key_id, *, resolve_identity, hook, receipts, clock):
        self.clock, self.resolve_identity, self.hook, self.receipts = (
            clock,
            resolve_identity,
            hook,
            receipts,
        )
        self.issuer = Issuer(
            key,
            issuer_key_id,
            resolve_identity=resolve_identity,
            resolve_execution=lambda h: receipts.consume(h, now=clock()),
        )
        self.lock = asyncio.Lock()

    async def completion(self, credential, value):
        if not isinstance(value, dict) or set(value) != {
            "request_base64",
            "identity_proof",
            "expectation",
        }:
            raise ValueError("Exact staged completion envelope required")
        raw = base64.b64decode(value["request_base64"], validate=True)
        if base64.b64encode(raw).decode() != value["request_base64"]:
            raise ValueError("Canonical request wire encoding required")
        now = self.clock()
        certificate = identity(
            value["identity_proof"],
            self.issuer.key.public_key(),
            self.issuer.key_id,
            now,
        )
        actual = self.resolve_identity(
            credential,
            certificate["pin"]["model_id"],
            certificate["pin"]["route_sha256"],
        )
        request(raw, actual)
        e = value["expectation"]
        if not isinstance(e, dict) or set(e) != EXPECT_FIELDS:
            raise ValueError("Exact response expectation required")
        lifetime(e, now, 120)
        nonce(e["nonce"])
        if (
            e["contract"] != CONTRACT
            or e["kind"] != "completion"
            or e["issuer_key_id"] != self.issuer.key_id
            or e["identity_sha256"] != sha(encode(certificate))
            or e["pin_sha256"] != sha(encode(actual))
            or e["request_sha256"] != sha(raw)
            or actual != certificate["pin"]
            or e["expires_at"] > certificate["expires_at"]
        ):
            raise ValueError("Unrelated identity, request or expectation")
        # Reserve nonce durably before dispatch. Failure/cancellation cannot replay.
        handle = self.receipts.begin(actual, raw, e, now=now)
        response, reference = await self.hook.execute(
            raw, actual, expires_at=e["expires_at"]
        )
        current = self.resolve_identity(
            credential, actual["model_id"], actual["route_sha256"]
        )
        if current != actual:
            raise ValueError("Runtime changed during execution")
        self.receipts.complete(
            handle, response, current, reference, attempts=1, now=self.clock()
        )
        return self.issuer.bind_response(
            credential,
            raw,
            response,
            e,
            value["identity_proof"],
            handle,
            now=self.clock(),
        )

    async def __call__(self, scope, receive, send):
        status, result, acquired = 400, {"error": "staged_request_rejected"}, False
        try:
            if (
                scope.get("type") != "http"
                or scope.get("method") != "POST"
                or scope.get("path") not in {IDENTITY_PATH, COMPLETION_PATH}
                or scope.get("query_string", b"")
                or scope.get("root_path", "")
                or scope.get("raw_path", scope["path"].encode())
                != scope["path"].encode()
            ):
                raise ValueError("Unsupported staged route")
            headers = scope.get("headers", [])
            auth = [v for k, v in headers if k.lower() == b"authorization"]
            types = [v for k, v in headers if k.lower() == b"content-type"]
            if (
                len(auth) != 1
                or types != [b"application/json"]
                or not auth[0].startswith(b"Bearer ")
            ):
                raise ValueError("Exact authentication headers required")
            credential = auth[0][7:].decode("ascii")
            parts, length = [], 0
            async with asyncio.timeout(2):
                for _ in range(32):
                    message = await receive()
                    if message.get("type") != "http.request" or not isinstance(
                        message.get("body", b""), bytes
                    ):
                        raise ValueError("Disconnected staged request")
                    part = message.get("body", b"")
                    length += len(part)
                    if length > 384 * 1024:
                        raise ValueError("Staged request exceeds bounds")
                    parts.append(part)
                    if not message.get("more_body", False):
                        break
                else:
                    raise ValueError("Too many staged request fragments")
            value = decode(b"".join(parts), 384 * 1024)
            if scope["path"] == IDENTITY_PATH:
                if not isinstance(value, dict) or set(value) != {
                    "model",
                    "route_sha256",
                    "challenge",
                }:
                    raise ValueError("Exact staged identity envelope required")
                result = decode(
                    self.issuer.issue_identity(
                        credential,
                        value["model"],
                        value["route_sha256"],
                        value["challenge"],
                        now=self.clock(),
                    )
                )
            else:
                try:
                    await asyncio.wait_for(self.lock.acquire(), timeout=0.05)
                    acquired = True
                except TimeoutError:
                    status, result = 503, {"error": "staged_capacity_unavailable"}
                    raise ValueError("Staged route busy") from None
                result = decode(await self.completion(credential, value))
            status = 200
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # No request, credential, native error, traceback or document logging.
        finally:
            if acquired:
                self.lock.release()
        body = encode(result)
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
