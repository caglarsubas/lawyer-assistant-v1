"""Offline-only public source quarantine. No qualification, retrieval or publication side effects."""

import hashlib
import ipaddress
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from .auth import authenticate

SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_RAW = 20 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
MAX_METADATA = 64 * 1024
MAX_PACKAGES = 10_000
FILES = {"raw.bin": MAX_RAW, "text.txt": MAX_TEXT, "locators.json": MAX_JSON,
         "source.json": MAX_METADATA, "rights-review.json": MAX_METADATA,
         "identity-review.json": MAX_METADATA}
LIMITATIONS = [
    "Bu kayıtlar karantinadadır; yayımlanmış hukuk külliyatına veya araştırma sonuçlarına dahil değildir.",
    "Herkese açık URL kullanım izni değildir. Haklar, kaynak kimliği ve hukuki uygunluk ayrı inceleme gerektirir.",
    "Aktarım beyanları ve inceleme belgeleri operatör tarafından sağlanmıştır; aktarım bunları onaylamaz.",
]


class PublicSourceError(ValueError):
    """Safe message only: never include source contents, credentials or local paths."""


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceMetadata(Input):
    schema_version: Literal["public-source-v1"]
    title: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2000)
    source_version_id: str = Field(min_length=1, max_length=200)
    domain: Literal["contracts", "commercial", "employment"]
    acquired_at: str | None
    published_on: str | None
    effective_from: str | None
    effective_until: str | None
    data_classification: Literal["public"]
    origin: Literal["public_legal_source"]
    contains_private_matter_data: StrictBool
    synthetic: StrictBool
    raw_media_type: Literal["application/pdf", "text/plain", "text/html", "application/xhtml+xml",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]

    @field_validator("title", "source_version_id")
    @classmethod
    def clean_label(cls, value):
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid label")
        return value

    @field_validator("contains_private_matter_data", "synthetic")
    @classmethod
    def public_only(cls, value):
        if value:
            raise ValueError("Private and synthetic sources cannot enter the public corpus")
        return value

    @field_validator("source_url")
    @classmethod
    def public_url(cls, value):
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.port not in (None, 443) or len(host) > 253
                or any(ord(c) < 33 or ord(c) > 126 for c in value)
                or not re.fullmatch(r"[a-zA-Z0-9.-]+", host) or "." not in host
                or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test", ".example"))
                or host in {"localhost", "example.com", "example.org", "example.net"}
                or any(part in {"", ".", ".."} for part in host.split("."))):
            raise ValueError("A credential-free public HTTPS source URL is required")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return value
        raise ValueError("IP address URLs are not admitted")

    @field_validator("acquired_at")
    @classmethod
    def timestamp(cls, value):
        if value is None:
            return value
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None or parsed > datetime.now(timezone.utc):
            raise ValueError("Acquisition must have an explicit timezone and cannot be in the future")
        return value

    @field_validator("published_on", "effective_from", "effective_until")
    @classmethod
    def calendar_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Dates must use YYYY-MM-DD or null for unknown")
        return value


class Passage(Input):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: str = Field(min_length=1, max_length=300)

    @field_validator("locator")
    @classmethod
    def printable_locator(cls, value):
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid locator")
        return value


class LocatorMap(Input):
    schema_version: Literal["public-locators-v1"]
    offset_unit: Literal["unicode_code_points"]
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    passages: list[Passage] = Field(min_length=1, max_length=5000)


class ReviewEvidence(Input):
    schema_version: Literal["public-review-evidence-v1"]
    kind: Literal["rights", "source_identity"]
    source_url: str
    source_version_id: str
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_id: str = Field(min_length=1, max_length=200)
    reviewed_at: str
    assessment: Literal["pending", "permitted", "restricted", "denied", "verified", "disputed"]
    evidence_reference: str = Field(min_length=1, max_length=1000)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=1, max_length=4000)

    @field_validator("reviewed_at")
    @classmethod
    def timestamp(cls, value):
        return SourceMetadata.timestamp(value)


@dataclass(frozen=True)
class VerifiedPublicSource:
    """One bounded, verified read; inspection never reopens an unverified artifact."""

    detail: dict
    metadata: SourceMetadata
    locators: LocatorMap
    artifacts: dict[str, bytes]
    text: str

    @property
    def raw(self) -> bytes:
        return self.artifacts["raw.bin"]


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PublicSourceError("Duplicate JSON keys are not admitted")
            result[key] = value
        return result
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, RecursionError):
        raise PublicSourceError("Invalid UTF-8 JSON input") from None


def _regular_bytes(path, limit):
    path = Path(path).absolute()
    # Reject symlinks in every supplied component, including the parent directory.
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise PublicSourceError("Symlinks are not admitted")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
                raise PublicSourceError("Input must be a nonempty regular file within its size limit")
            content = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if len(content) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise PublicSourceError("Input changed during validation or exceeded its size limit")
            return content
    except OSError:
        raise PublicSourceError("Source artifact is missing or unreadable") from None


def _validate(artifacts):
    try:
        metadata = SourceMetadata.model_validate(_json(artifacts["source.json"]))
        if (metadata.effective_from and metadata.effective_until
                and metadata.effective_until < metadata.effective_from):
            raise PublicSourceError("Effective date interval is reversed")
        text = artifacts["text.txt"].decode("utf-8")
        if not text.strip() or text.startswith("\ufeff") or any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise PublicSourceError("Extracted text must be nonempty UTF-8 without control characters or BOM")
        locators = LocatorMap.model_validate(_json(artifacts["locators.json"]))
        if locators.raw_sha256 != _hash(artifacts["raw.bin"]) or locators.text_sha256 != _hash(artifacts["text.txt"]):
            raise PublicSourceError("Locator map does not match the exact raw and text artifacts")
        ids, previous_end = set(), 0
        for passage in locators.passages:
            if (passage.id in ids or passage.start < previous_end or not passage.start < passage.end <= len(text)
                    or passage.end - passage.start > 20_000
                    or passage.text_sha256 != _hash(text[passage.start:passage.end].encode("utf-8"))):
                raise PublicSourceError("Passage identifiers, ordering, Unicode spans or hashes are invalid")
            ids.add(passage.id)
            previous_end = passage.end
        for name, kind in (("rights-review.json", "rights"), ("identity-review.json", "source_identity")):
            if name not in artifacts:
                continue
            evidence = ReviewEvidence.model_validate(_json(artifacts[name]))
            assessments = {"pending", "permitted", "restricted", "denied"} if kind == "rights" else {"pending", "verified", "disputed"}
            if (evidence.kind != kind or evidence.assessment not in assessments
                    or evidence.source_url != metadata.source_url
                    or evidence.source_version_id != metadata.source_version_id
                    or evidence.raw_sha256 != locators.raw_sha256):
                raise PublicSourceError("Independent review evidence does not identify this source version")
        return metadata.model_dump(), locators, text
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        if isinstance(error, PublicSourceError):
            raise
        raise PublicSourceError("Source metadata, review evidence or locator map failed validation") from None


def _hints(text):
    # Flags are untrusted triage hints, never instructions, findings of safety or execution triggers.
    patterns = {"instruction_override": r"ignore\s+(all\s+)?(previous|prior)\s+instructions|önceki\s+talimatları\s+(yok say|unut)",
                "role_markup": r"<\|(?:system|assistant|im_start)\|>|<system>|\[INST\]",
                "credential_request": r"(?:api[ _-]?key|password|parola|şifre).{0,30}(?:send|reveal|gönder|paylaş)"}
    return [name for name, pattern in patterns.items() if re.search(pattern, text, re.IGNORECASE)]


class PublicSourceStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        if any(part.is_symlink() for part in (self.root, *self.root.parents)):
            raise PublicSourceError("Public source store cannot use symlinks")

    def import_package(self, *, metadata_path, raw_path, text_path, locators_path,
                       rights_review_path=None, identity_review_path=None):
        paths = {"source.json": metadata_path, "raw.bin": raw_path,
                 "text.txt": text_path, "locators.json": locators_path}
        if rights_review_path:
            paths["rights-review.json"] = rights_review_path
        if identity_review_path:
            paths["identity-review.json"] = identity_review_path
        if len({Path(path).absolute() for path in paths.values()}) != len(paths):
            raise PublicSourceError("Source artifacts and independent review documents must be separate files")
        if any(Path(path).name.startswith(".env") or Path(path).suffix == ".enc" for path in paths.values()):
            raise PublicSourceError("Credential and encrypted private matter artifacts are prohibited")
        artifacts = {name: _regular_bytes(path, FILES[name]) for name, path in paths.items()}
        metadata, locators, text = _validate(artifacts)
        manifest = {"schema_version": "public-source-package-v1", "metadata": metadata,
                    "artifacts": {name: {"sha256": _hash(content), "bytes": len(content)}
                                  for name, content in artifacts.items()},
                    "passage_count": len(locators.passages), "rights_status": "rights_pending",
                    "review_status": "legal_review_pending", "publication_status": "staged",
                    "injection_risk_hints": _hints(text), "review_evidence_trust": "operator_supplied_unverified"}
        manifest_bytes = _canonical(manifest)
        identifier = _hash(manifest_bytes)
        if self.root.exists() and any(not SHA256.fullmatch(p.name) and not p.name.startswith(".incoming-")
                                      for p in self.root.iterdir()):
            raise PublicSourceError("Use a dedicated public staging directory, separate from private matter storage")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = self.root / identifier
        if destination.exists() or destination.is_symlink():
            self.detail(identifier)  # Idempotence requires all existing artifacts to remain intact.
            return self._summary(identifier, manifest)
        if sum(1 for _ in self.root.iterdir()) >= MAX_PACKAGES:
            raise PublicSourceError("Public staging capacity reached; operator maintenance required")
        temporary = Path(tempfile.mkdtemp(prefix=".incoming-", dir=self.root))
        try:
            for name, content in {**artifacts, "manifest.json": manifest_bytes}.items():
                with (temporary / name).open("xb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                (temporary / name).chmod(0o400)
            try:
                os.rename(temporary, destination)
            except OSError:
                if destination.exists():
                    self.detail(identifier)
                else:
                    raise PublicSourceError("Atomic staging failed") from None
            destination.chmod(0o500)
            return self._summary(identifier, manifest)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _manifest(self, identifier):
        if not SHA256.fullmatch(identifier):
            raise PublicSourceError("Invalid public source identifier")
        package = self.root / identifier
        if package.is_symlink() or not package.is_dir():
            raise PublicSourceError("Public source package unavailable")
        data = _regular_bytes(package / "manifest.json", MAX_METADATA)
        if _hash(data) != identifier:
            raise PublicSourceError("Public source manifest integrity failed")
        manifest = _json(data)
        expected = {"schema_version", "metadata", "artifacts", "passage_count", "rights_status", "review_status",
                    "publication_status", "injection_risk_hints", "review_evidence_trust"}
        try:
            if (set(manifest) != expected or data != _canonical(manifest)
                    or manifest["schema_version"] != "public-source-package-v1"
                    or manifest["rights_status"] != "rights_pending"
                    or manifest["review_status"] != "legal_review_pending"
                    or manifest["publication_status"] != "staged"
                    or manifest["review_evidence_trust"] != "operator_supplied_unverified"
                    or type(manifest["passage_count"]) is not int or not 1 <= manifest["passage_count"] <= 5000
                    or not isinstance(manifest["injection_risk_hints"], list)
                    or not set(manifest["injection_risk_hints"]).issubset(
                        {"instruction_override", "role_markup", "credential_request"})):
                raise PublicSourceError("Invalid public source package manifest")
            SourceMetadata.model_validate(manifest["metadata"])
            entries = manifest["artifacts"]
            if (not {"raw.bin", "text.txt", "locators.json", "source.json"} <= set(entries) <= set(FILES)
                    or set(path.name for path in package.iterdir()) != {*entries, "manifest.json"}):
                raise PublicSourceError("Unexpected or missing source artifacts")
            for name, entry in entries.items():
                if (set(entry) != {"sha256", "bytes"} or not SHA256.fullmatch(entry["sha256"])
                        or type(entry["bytes"]) is not int or not 0 < entry["bytes"] <= FILES[name]):
                    raise PublicSourceError("Invalid source artifact digest or size")
            return manifest
        except (TypeError, ValueError, KeyError, OSError):
            raise PublicSourceError("Invalid public source package manifest") from None

    @staticmethod
    def _summary(identifier, manifest):
        metadata = manifest["metadata"]
        return {"id": identifier, **{key: metadata[key] for key in (
            "title", "source_url", "source_version_id", "domain", "acquired_at")},
            **{key: manifest[key] for key in ("rights_status", "review_status", "passage_count", "publication_status")}}

    def list_packages(self, *, limit=50, after=None):
        if type(limit) is not int or not 1 <= limit <= 100 or (after is not None and not SHA256.fullmatch(after)):
            raise PublicSourceError("Invalid public source page bounds")
        if not self.root.exists():
            return {"items": [], "limitations": LIMITATIONS, "next_cursor": None,
                    "integrity_scope": "manifest_only"}
        names = []
        for index, path in enumerate(self.root.iterdir()):
            if index >= MAX_PACKAGES:
                raise PublicSourceError("Public staging capacity exceeded")
            if SHA256.fullmatch(path.name) and (after is None or path.name > after):
                names.append(path.name)
        names.sort()
        selected = names[:limit]
        return {"items": [self._summary(name, self._manifest(name)) for name in selected],
                "limitations": LIMITATIONS, "next_cursor": selected[-1] if len(names) > limit else None,
                "integrity_scope": "manifest_only"}

    def verified_package(self, identifier) -> VerifiedPublicSource:
        manifest = self._manifest(identifier)
        artifacts = {name: _regular_bytes(self.root / identifier / name, FILES[name])
                     for name in manifest["artifacts"]}
        for name, content in artifacts.items():
            if {"sha256": _hash(content), "bytes": len(content)} != manifest["artifacts"][name]:
                raise PublicSourceError("Public source artifact integrity failed")
        metadata, locators, text = _validate(artifacts)
        if (metadata != manifest["metadata"] or len(locators.passages) != manifest["passage_count"]
                or _hints(text) != manifest["injection_risk_hints"]):
            raise PublicSourceError("Public source package consistency failed")
        detail = {**self._summary(identifier, manifest),
                "dates": {key: metadata[key] for key in ("published_on", "effective_from", "effective_until")},
                "artifacts": manifest["artifacts"], "integrity_scope": "all_artifacts_verified",
                "review_evidence": {"rights_supplied": "rights-review.json" in artifacts,
                                    "identity_supplied": "identity-review.json" in artifacts,
                                    "trust": "operator_supplied_unverified"},
                "injection_risk_hints": manifest["injection_risk_hints"], "limitations": LIMITATIONS}
        return VerifiedPublicSource(detail=detail, metadata=SourceMetadata.model_validate(metadata),
                                    locators=locators, artifacts=artifacts, text=text)

    def detail(self, identifier):
        return self.verified_package(identifier).detail

    def passages(self, identifier, *, offset=0, limit=20):
        if type(offset) is not int or not 0 <= offset <= 5000 or type(limit) is not int or not 1 <= limit <= 20:
            raise PublicSourceError("Invalid public source passage page bounds")
        package = self.verified_package(identifier)
        passages = package.locators.passages
        items = [{**passage.model_dump(), "text": package.text[passage.start:passage.end]}
                 for passage in passages[offset:offset + limit]]
        next_offset = offset + len(items)
        return {"source_id": identifier, "source_version_id": package.metadata.source_version_id,
                "raw_sha256": package.locators.raw_sha256, "text_sha256": package.locators.text_sha256,
                "offset_unit": "unicode_code_points", "items": items, "total": len(passages),
                "next_offset": next_offset if next_offset < len(passages) else None,
                "integrity_scope": "all_artifacts_verified"}


def public_sources_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["public-source-staging"])

    def authorize(request: Request):
        user = authenticate(request)
        if user.role not in {"admin", "curator"}:
            raise HTTPException(403, "Kaynak hazırlama kayıtları için küratör yetkisi gerekiyor")
        return user

    def reauthorize(request, user):
        current = authorize(request)
        if current.id != user.id or current.firm_id != user.firm_id:
            raise HTTPException(403, "Kaynak inceleme yetkisi değişti; yeniden oturum açmanız gerekiyor")

    def store(request):
        try:
            return PublicSourceStore(request.app.state.settings.public_source_dir)
        except PublicSourceError:
            raise HTTPException(503, "Herkese açık kaynak hazırlama deposu kullanılamıyor") from None

    @router.get("")
    def listing(request: Request, limit: int = Query(default=50, ge=1, le=100),
                after: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"), user=Depends(authorize)):
        try:
            result = store(request).list_packages(limit=limit, after=after)
        except (PublicSourceError, OSError):
            raise HTTPException(503, "Kaynak hazırlama bütünlük denetimi başarısız") from None
        reauthorize(request, user)
        return result

    @router.get("/{identifier}")
    def detail(identifier: str, request: Request, user=Depends(authorize)):
        if not SHA256.fullmatch(identifier):
            raise HTTPException(404, "Kaynak hazırlama kaydı bulunamadı")
        try:
            result = store(request).detail(identifier)
        except (PublicSourceError, OSError):
            raise HTTPException(409, "Kaynak paketi yok veya bütünlük denetimi başarısız") from None
        reauthorize(request, user)
        return result

    @router.get("/{identifier}/passages")
    def passages(identifier: str, request: Request, offset: int = Query(default=0, ge=0, le=5000),
                 limit: int = Query(default=20, ge=1, le=20), user=Depends(authorize)):
        if not SHA256.fullmatch(identifier):
            raise HTTPException(404, "Kaynak hazırlama kaydı bulunamadı")
        try:
            result = store(request).passages(identifier, offset=offset, limit=limit)
        except (PublicSourceError, OSError):
            raise HTTPException(409, "Kaynak paketi yok veya bütünlük denetimi başarısız") from None
        reauthorize(request, user)
        return result

    @router.get("/{identifier}/original")
    def original(identifier: str, request: Request, user=Depends(authorize)):
        if not SHA256.fullmatch(identifier):
            raise HTTPException(404, "Kaynak hazırlama kaydı bulunamadı")
        try:
            package = store(request).verified_package(identifier)
        except (PublicSourceError, OSError):
            raise HTTPException(409, "Kaynak paketi yok veya bütünlük denetimi başarısız") from None
        reauthorize(request, user)
        return Response(content=package.raw, media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="public-source-{identifier[:16]}.bin"',
            "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
            "Content-Security-Policy": "sandbox; default-src 'none'; frame-ancestors 'none'",
        })

    return router
