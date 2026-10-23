"""Public interface extract; no provider config, registry file or runtime import.

Engine commit 13962b3; actual source SHA-256 is retained in the qualification report.
Only the current key record and its expiry logic are exercised with invented data.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class _KeyRecord:
    key: str
    tenant: str
    org_id: str | None = None
    key_id: str | None = None
    not_before: datetime | None = None
    expires_at: datetime | None = None

    def active_at(self, now: datetime) -> bool:
        if self.not_before is not None and now < self.not_before:
            return False
        return self.expires_at is None or now < self.expires_at

    @property
    def safe_key_id(self) -> str:
        return self.key_id or _redact(self.key)

    @property
    def status_key_id(self) -> str:
        if self.key_id is not None:
            return self.key_id
        fingerprint = hashlib.sha256(self.key.encode("utf-8")).hexdigest()[:16]
        return f"legacy-sha256:{fingerprint}"


def _redact(key: str) -> str:
    """Return a short, safe-to-log identifier for a key."""
    if len(key) <= 12:
        return key[:3] + "***"
    return f"{key[:6]}...{key[-4:]}"
