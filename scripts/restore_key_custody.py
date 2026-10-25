"""Pinned disposable key enrollment; no key generation, export, rotation or HSM claim."""

from pathlib import Path

import operator_enrollment_evidence as e
from cryptography.fernet import Fernet
from operator_review_journal import reject

SCHEMA = "disposable-review-key-custody-v1"


def file_id(path):
    path = e.directory(path)
    info = path.stat()
    return {"device": info.st_dev, "inode": info.st_ino, "owner": info.st_uid}


class KeyCustody:
    def __init__(self, key_path, enrollment_path, approved_sha256, scope):
        self.key_path, self.enrollment = Path(key_path), Path(enrollment_path)
        self.approved = e.token(approved_sha256)
        self.scope_sha = e.sha(e.encode(scope))
        self.check(0)

    def check(self, now):
        raw = e.read(self.enrollment)
        value = e.decode(raw)
        fields = {"schema", "key_id", "scope_sha256", "fingerprint_sha256", "key_file", "purpose", "created_at", "expires_at", *e.FLAGS}
        if (e.sha(raw) != self.approved or set(value) != fields or value["schema"] != SCHEMA or value["scope_sha256"] != self.scope_sha
                or value["purpose"] != "review_history_backup_restore" or any(value[k] is not False for k in e.FLAGS)):
            reject()
        e.token(value["key_id"], 32)
        if not e.stamp(value["created_at"]) < e.stamp(value["expires_at"]) or (now and not value["created_at"] <= e.stamp(now) < value["expires_at"]):
            reject()
        key = e.read(self.key_path)
        info = self.key_path.stat()
        if (value["key_file"] != {"device": info.st_dev, "inode": info.st_ino, "owner": info.st_uid}
                or e.sha(key) != value["fingerprint_sha256"]):
            reject()
        Fernet(key)
        return value
