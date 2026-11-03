"""Explicit trusted-host binding. No imports from an unverified export or new login."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

from controller_stage_manifest import hex_digest
from operator_preview_manifest import inspect_host, inspect_package


@dataclass(frozen=True, kw_only=True)
class HostBinding:
    adapter: object = field(repr=False)
    source_id: str = field(repr=False)
    handoff_sha256: str = field(repr=False)
    binding_sha256: str = field(repr=False)
    profile_id: str = field(repr=False)
    preparer_id: str = field(repr=False)
    reviewer_id: str = field(repr=False)
    origin: str = field(repr=False)

    def validate(self):
        # No dynamically selected module, store, path, principal or auth replacement.
        h = sys.modules["operator_checksum_handoff"]
        auth = sys.modules["operator_review_auth"]
        origin = urlsplit(self.origin)
        if (origin.scheme not in {"http", "https"} or not origin.hostname or origin.username or origin.password
                or origin.path or origin.query or origin.fragment or self.origin != origin.scheme + "://" + origin.netloc
                or not self.origin.isascii() or origin.netloc != origin.netloc.lower()):
            raise ValueError("Canonical trusted origin required")
        if type(self.adapter) is not h.OperatorChecksumAdapter:
            raise ValueError("Exact host adapter required")
        source = self.adapter.sources.get(self.source_id)
        if source is None or source.sha256 != hex_digest(self.handoff_sha256):
            raise ValueError("Host-selected preparation differs")
        p = self.adapter.service.reconciler.disposition.planner
        if (type(p.authority) is not auth.SessionAuthority or p.authority.profile_id != self.profile_id
                or source.profile_id != self.profile_id or source.binding_sha256 != hex_digest(self.binding_sha256)
                or (p.preparer, p.reviewer) != (self.preparer_id, self.reviewer_id)
                or self.preparer_id == self.reviewer_id
                or p.authority.app.state.settings.origins != (self.origin,)):
            raise ValueError("Exact disposable host binding required")
        p.authority.validate_profile()
        h.validate(self.adapter.service, source, p.clock())
        return p, source


@dataclass(frozen=True, kw_only=True)
class BoundPreview:
    preview: object = field(repr=False)
    origin: str = field(repr=False)

    async def __call__(self, scope, receive, send):
        origin = urlsplit(self.origin)
        headers = scope.get("headers", [])
        hosts = [v for k, v in headers if k.lower() == b"host"]
        if (scope.get("type") != "http" or scope.get("scheme") != origin.scheme or scope.get("root_path", "")
                or len(headers) > 64 or sum(len(k) + len(v) for k, v in headers) > 16384
                or hosts != [origin.netloc.encode("ascii")]
                or any(k.lower() == b"forwarded" or k.lower().startswith(b"x-forwarded-") for k, _ in headers)):
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"cache-control", b"no-store"), (b"content-type", b"application/json"),
                                    (b"x-content-type-options", b"nosniff")]})
            return await send({"type": "http.response.body", "body": b'{"state":"denied"}'})
        return await self.preview(scope, receive, send)


def bind_preview(root, approved_manifest_sha256, *, host_root, binding, require_readonly=True):
    """Verify a separately pinned export and exact compatible host before execution.

    False readonly is ONLY an explicit disposable test policy. Successful binding
    returns an unregistered ASGI callable, never installs or starts a listener.
    """
    if type(binding) is not HostBinding or sys.version_info < (3, 12):
        raise ValueError("Typed host binding and Python 3.12+ required")
    manifest, assets = inspect_package(root, approved_manifest_sha256, require_readonly=require_readonly)
    inspect_host(host_root, manifest, require_readonly=require_readonly)
    p, source = binding.validate()
    # Execute the captured, already checked bytes. The exact original source reads
    # its adjacent HTML; require the same bytes after construction before release.
    module = ModuleType("lawyer_operator_preview_stage")
    module.__file__ = str(Path(root).absolute() / "operator_inspection_preview.py")
    exec(compile(assets["operator_inspection_preview.py"], module.__file__, "exec"), module.__dict__)  # noqa: S102 - independently pinned source, captured after inspection.
    preview = module.OperatorInspectionPreview(adapter=binding.adapter, source_id=binding.source_id,
                                               expected_handoff_sha256=binding.handoff_sha256)
    if module.HTML != assets["operator_inspection_preview.html"]:
        raise ValueError("Preview page changed during binding")
    final_manifest, final_assets = inspect_package(root, approved_manifest_sha256, require_readonly=require_readonly)
    inspect_host(host_root, final_manifest, require_readonly=require_readonly)
    binding.validate()
    finished = p.clock()
    if (assets != final_assets or manifest != final_manifest
            or not source.created_at <= finished <= source.created_at + sys.modules["operator_checksum_handoff"].LIFETIME):
        raise ValueError("Preview binding expired or changed")
    return BoundPreview(preview=preview, origin=binding.origin)
