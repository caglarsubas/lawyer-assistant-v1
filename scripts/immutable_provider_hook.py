"""Staged single-attempt digest dispatch. No startup, provider import or activation."""

import asyncio
import hashlib
import os
import re
import stat
from pathlib import Path

import httpx
from provider_trust_stage import directory, read
from signed_provider_contract import completion, decode, encode, pin, request, sha

ENDPOINT = "http://127.0.0.1:11434"
LAYER_TYPES = {
    "application/vnd.ollama.image.model",
    "application/vnd.ollama.image.template",
    "application/vnd.ollama.image.system",
    "application/vnd.ollama.image.params",
    "application/vnd.ollama.image.license",
}


class HookRejected(ValueError):
    pass


class ManifestSnapshot:
    """Verify an independently staged, local, single-model blob snapshot.

    Hashes identify bytes, not hardware execution. Future installation requires
    an isolated read-only model store and a qualified backend build. This class
    never imports, copies, mutates or traverses the live Ollama store.
    """

    def __init__(self, root, runtime_pin):
        self.root = directory(Path(root))
        self.pin = encode(pin(runtime_pin))
        self.verify()

    def blob(self, digest, size, *, metadata=False):
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or type(size) is not int
            or not 0 < size <= (65536 if metadata else 32 * 1024**3)
        ):
            raise HookRejected("Staged blob descriptor rejected")
        directory(self.root)
        path = self.root / digest.replace(":", "-")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size != size
            ):
                raise HookRejected("Staged blob ownership or size rejected")
            h, chunks, count = hashlib.sha256(), [], 0
            while chunk := stream.read(1024 * 1024):
                count += len(chunk)
                if count > size:
                    raise HookRejected("Staged blob changed")
                h.update(chunk)
                if metadata:
                    chunks.append(chunk)
            if count != size or h.hexdigest() != digest[7:]:
                raise HookRejected("Staged blob digest differs")
            return b"".join(chunks)

    def verify(self):
        p = decode(self.pin)
        reference = "sha256:" + p["model_digest_sha256"]
        raw = read(self.root / reference.replace(":", "-"))
        if sha(raw) != p["model_digest_sha256"]:
            raise HookRejected("Staged manifest digest differs")
        manifest = decode(raw, 65536)
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {"schemaVersion", "mediaType", "config", "layers"}
            or type(manifest["schemaVersion"]) is not int
            or manifest["schemaVersion"] != 2
            or manifest["mediaType"]
            != "application/vnd.docker.distribution.manifest.v2+json"
            or not isinstance(manifest["layers"], list)
            or not 1 <= len(manifest["layers"]) <= 16
        ):
            raise HookRejected("Single staged manifest required")
        entries = [manifest["config"], *manifest["layers"]]
        if any(
            not isinstance(v, dict) or set(v) != {"mediaType", "digest", "size"}
            for v in entries
        ):
            raise HookRejected("Exact staged descriptors required")
        if (
            manifest["config"]["mediaType"]
            != "application/vnd.docker.container.image.v1+json"
        ):
            raise HookRejected("Staged model configuration rejected")
        config = decode(
            self.blob(
                manifest["config"]["digest"], manifest["config"]["size"], metadata=True
            )
        )
        allowed = {
            "model_format",
            "model_family",
            "model_families",
            "model_type",
            "file_type",
            "architecture",
            "os",
            "rootfs",
            "remote_host",
            "remote_model",
        }
        if (
            not isinstance(config, dict)
            or set(config) - allowed
            or config.get("model_format") != "gguf"
            or config.get("remote_host", "") != ""
            or config.get("remote_model", "") != ""
        ):
            raise HookRejected("Explicit local GGUF configuration required")
        if (
            sum(
                v["mediaType"] == "application/vnd.ollama.image.model"
                for v in manifest["layers"]
            )
            != 1
        ):
            raise HookRejected("One local text model required")
        for layer in manifest["layers"]:
            if layer["mediaType"] not in LAYER_TYPES:
                raise HookRejected("Unsupported staged model layer")
            self.blob(layer["digest"], layer["size"])
        return reference


class ImmutableExecutionHook:
    """Owns dispatch/reference/attempt count; accepts none from request JSON.

    Native compatibility and executed weights remain unqualified until a separate
    approved isolated trial. Injected transports are for invented offline tests.
    """

    def __init__(self, snapshot, *, clock, transport=None):
        self.snapshot, self.clock, self.transport = snapshot, clock, transport

    async def execute(self, request_bytes, runtime_pin, *, expires_at):
        expected = pin(runtime_pin)
        if encode(expected) != self.snapshot.pin:
            raise HookRejected("Runtime differs from staged artifact")
        value = request(request_bytes, expected)
        # Conservative staging admission, not a model tokenizer/truncation proof.
        if (
            sum(len(v["content"].encode()) for v in value["messages"])
            + value["max_completion_tokens"]
            + 512
            > expected["application_context_units"]
        ):
            raise HookRejected("Staged request exceeds conservative context admission")
        reference = self.snapshot.verify()
        body = encode(
            {
                "model": reference,
                "messages": value["messages"],
                "stream": False,
                "think": False,
                "options": {
                    "num_ctx": expected["model_context_units"],
                    "num_predict": value["max_completion_tokens"],
                    "temperature": 0,
                },
            }
        )
        remaining = expires_at - self.clock()
        if not 0 < remaining <= 120:
            raise HookRejected("Staged execution deadline rejected")
        transport = (
            self.transport
            if self.transport is not None
            else httpx.AsyncHTTPTransport(retries=0)
        )
        try:
            async with asyncio.timeout(min(30, remaining)):
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(30, connect=2),
                    http2=False,
                ) as client:
                    # Exactly one send. No alternate endpoint/tag, repair or retry path.
                    async with client.stream(
                        "POST",
                        ENDPOINT + "/api/chat",
                        content=body,
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        if (
                            response.status_code != 200
                            or response.headers.get("content-type", "").split(";")[0]
                            != "application/json"
                            or response.headers.get("content-encoding", "identity")
                            != "identity"
                        ):
                            raise HookRejected("Staged backend response rejected")
                        chunks, length = [], 0
                        async for chunk in response.aiter_raw():
                            length += len(chunk)
                            if length > 8192:
                                raise HookRejected(
                                    "Staged backend response exceeds bounds"
                                )
                            chunks.append(chunk)
            native = decode(b"".join(chunks), 8192)
            allowed = {
                "model",
                "created_at",
                "message",
                "done",
                "done_reason",
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
            }
            if (
                not isinstance(native, dict)
                or set(native) - allowed
                or native.get("model") != reference
                or native.get("done") is not True
                or native.get("done_reason") != "stop"
                or not isinstance(native.get("message"), dict)
                or set(native["message"]) != {"role", "content"}
                or native["message"]["role"] != "assistant"
            ):
                raise HookRejected("Incomplete or substituted staged response")
            usage = {
                "prompt_tokens": native.get("prompt_eval_count"),
                "completion_tokens": native.get("eval_count"),
            }
            if any(type(v) is not int or v < 0 for v in usage.values()):
                raise HookRejected("Complete integer usage required")
            usage["total_tokens"] = sum(usage.values())
            result = encode(
                {
                    "model": expected["model_id"],
                    "request_key_source": "local-inference",
                    "choices": [
                        {"finish_reason": "stop", "message": native["message"]}
                    ],
                    "usage": usage,
                }
            )
            completion(result, expected, value["max_completion_tokens"])
            if self.clock() >= expires_at or self.snapshot.verify() != reference:
                raise HookRejected("Staged execution expired or artifact changed")
            return result, reference
        except asyncio.CancelledError:
            raise
        except Exception:
            # Native errors and original/model text never become diagnostic output.
            raise HookRejected(
                "Staged execution rejected; no retry or fallback"
            ) from None
