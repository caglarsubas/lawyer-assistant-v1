"""Host-owned continuity for committed observations across process restarts."""

import fcntl
import os
import re
import secrets
import stat
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from operator_enrollment_evidence import decode, directory, encode, stamp, token

SCHEMA = "host-reconciliation-continuity-v1"
MAX_BYTES = 4096


def _reject():
    raise ValueError("Host trust continuity unavailable") from None


@dataclass(frozen=True, kw_only=True)
class HeadFence:
    sequence: int
    registry_sha256: str
    state_sha256: str | None = None
    retired: bool = False

    def __post_init__(self):
        if stamp(self.sequence) == 0 or type(self.retired) is not bool:
            _reject()
        token(self.registry_sha256)
        if self.state_sha256 is not None:
            token(self.state_sha256)

    def covers(self, previous):
        if previous.retired and not self.retired:
            return False
        return self.sequence > previous.sequence or (
            self.sequence == previous.sequence and self.registry_sha256 == previous.registry_sha256
            and (previous.state_sha256 is None or self.state_sha256 == previous.state_sha256)
        )

    def observe(self, observed, *, epoch_matches):
        if self.retired:
            return self, False
        if not epoch_matches:
            return replace(self, retired=True), False
        if observed.sequence < self.sequence:
            return self, False
        if not observed.covers(self):
            return replace(self, retired=True), False
        return observed, True


class TrustContinuityStore:
    """A single private record for one independently configured resolver.

    Writers share the directory lock and synchronize replacement to disk. The
    configured host owns the directory, store ID, and binding digest.
    """

    def __init__(self, path, *, store_id, binding_sha256):
        path = Path(path).absolute()
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", path.name) is None:
            _reject()
        self._path = path
        self._store_id = token(store_id, 32)
        self._binding = token(binding_sha256)
        info = directory(path.parent).stat()
        self._directory_identity = info.st_dev, info.st_ino

    @property
    def binding_sha256(self):
        return self._binding

    @classmethod
    def create(cls, path, *, store_id, binding_sha256):
        """Initialize a new store only during explicit host setup."""
        store = cls(path, store_id=store_id, binding_sha256=binding_sha256)
        with store._locked(time.monotonic() + 2) as fd:
            store._write_file(fd, store._path.name, store._record(None))
            os.fsync(fd)
        return store

    @contextmanager
    def _locked(self, deadline):
        parent = directory(self._path.parent)
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if ((info.st_dev, info.st_ino) != self._directory_identity
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
                _reject()
            until = min(deadline, time.monotonic() + 2)
            while time.monotonic() < until:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(min(0.01, max(0, until - time.monotonic())))
            if time.monotonic() >= until:
                _reject()
            yield fd
        finally:
            os.close(fd)

    def _record(self, fence):
        return {"schema": SCHEMA, "store_id": self._store_id, "binding_sha256": self._binding,
                "head": asdict(fence) if fence is not None else None}

    def _load(self, fd, minimum, previous):
        handle = os.open(self._path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
        with os.fdopen(handle, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= MAX_BYTES):
                _reject()
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) != info.st_size:
            _reject()
        record = decode(raw)
        if (type(record) is not dict or record.keys() != self._record(None).keys()
                or record["schema"] != SCHEMA or record["store_id"] != self._store_id
                or record["binding_sha256"] != self._binding or raw != encode(record)):
            _reject()
        head = record["head"]
        if head is None:
            current = minimum
        else:
            if type(head) is not dict or head.keys() != asdict(minimum).keys():
                _reject()
            current = HeadFence(**head)
            if current.state_sha256 is None and current != replace(minimum, retired=True):
                _reject()
        if not current.covers(minimum) or not current.covers(previous):
            _reject()
        return current

    @staticmethod
    def _write_file(fd, name, record):
        handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
        try:
            with os.fdopen(handle, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(encode(record))
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            os.unlink(name, dir_fd=fd)
            raise

    def read(self, minimum, previous, deadline):
        with self._locked(deadline) as fd:
            return self._load(fd, minimum, previous)

    def observe(self, minimum, previous, observed, *, epoch_matches, deadline):
        with self._locked(deadline) as fd:
            current = self._load(fd, minimum, previous)
            updated, admitted = current.observe(observed, epoch_matches=epoch_matches)
            if updated != current:
                if time.monotonic() >= deadline:
                    _reject()
                temporary = ".host-trust-" + secrets.token_hex(16)
                self._write_file(fd, temporary, self._record(updated))
                try:
                    os.replace(temporary, self._path.name, src_dir_fd=fd, dst_dir_fd=fd)
                    os.fsync(fd)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=fd)
                    except FileNotFoundError:
                        pass
            return updated, admitted
