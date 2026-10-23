"""Owner-only staged issuer and independent public-trust enrollment. No activation."""

import argparse
import base64
import json
import os
import secrets
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from signed_provider_contract import decode, encode, label, sha, stamp


def directory(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Owner-only stage directory required")
    if path.absolute() != path.resolve():
        raise ValueError("Stage directory must not traverse symlinks")
    return path


def read(path, cap=65536):
    path = Path(path)
    directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or not 0 < info.st_size <= cap
        ):
            raise ValueError("Owner-only bounded regular stage file required")
        raw = stream.read(cap + 1)
        if len(raw) > cap:
            raise ValueError("Stage file exceeds bounds")
        return raw


def write(path, raw):
    path = Path(path)
    directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def fingerprint(public_key):
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("Ed25519 public key required")
    return sha(public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def public_record(raw):
    value = decode(raw)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "version",
            "issuer_key_id",
            "public_key_base64",
            "fingerprint",
            "created_at",
            "production_activation",
        }
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["production_activation"] is not False
    ):
        raise ValueError("Invalid staged public record")
    label(value["issuer_key_id"])
    stamp(value["created_at"])
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(value["public_key_base64"], validate=True))
    except (ValueError, TypeError):
        raise ValueError("Invalid staged public key") from None
    if fingerprint(key) != value["fingerprint"]:
        raise ValueError("Public-key fingerprint mismatch")
    return value, key


def create_issuer(path, issuer_key_id, *, now):
    path = Path(path)
    label(issuer_key_id)
    stamp(now)
    directory(path.parent)
    path.mkdir(mode=0o700)
    directory(path)
    key = Ed25519PrivateKey.generate()
    password = base64.urlsafe_b64encode(secrets.token_bytes(32))
    public = key.public_key()
    record = {
        "version": 1,
        "issuer_key_id": issuer_key_id,
        "public_key_base64": base64.b64encode(
            public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ).decode(),
        "fingerprint": fingerprint(public),
        "created_at": now,
        "production_activation": False,
    }
    write(path / "signer-password", password)
    write(
        path / "signer.encrypted.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password),
        ),
    )
    # Written last: partial provisioning never becomes a usable issuer.
    write(path / "public-candidate.json", encode(record))
    return {
        "issuer_key_id": issuer_key_id,
        "public_fingerprint": record["fingerprint"],
        "staged": True,
        "independent_consumer_approval": False,
        "production_activation": False,
    }


def load_signer(path, expected_fingerprint):
    path = directory(path)
    record, public = public_record(read(path / "public-candidate.json"))
    if expected_fingerprint != fingerprint(public):
        raise ValueError("Explicit expected public fingerprint required")
    try:
        key = serialization.load_pem_private_key(
            read(path / "signer.encrypted.pem"), read(path / "signer-password", 128)
        )
    except Exception:
        raise ValueError("Staged encrypted signer unavailable") from None
    if not isinstance(key, Ed25519PrivateKey) or fingerprint(key.public_key()) != record["fingerprint"]:
        raise ValueError("Staged signer/public key mismatch")
    return key


def import_candidate(public_bytes, destination):
    # Only the public export crosses this boundary. Never copy issuer secrets.
    record, _ = public_record(public_bytes)
    destination = Path(destination)
    directory(destination.parent)
    destination.mkdir(mode=0o700)
    write(destination / "candidate.json", encode(record))
    return {"candidate_staged": True, "independent_consumer_approval": False, "production_activation": False}


def confirm_key(path, expected_fingerprint, reviewer, *, now):
    path = directory(path)
    label(reviewer)
    stamp(now)
    record, key = public_record(read(path / "candidate.json"))
    if (
        expected_fingerprint != fingerprint(key)
        or now < record["created_at"]
        or os.path.lexists(path / "revoked.json")
    ):
        raise ValueError("Independent key confirmation rejected")
    write(
        path / "key-confirmation.json",
        encode(
            {
                "issuer_key_id": record["issuer_key_id"],
                "fingerprint": expected_fingerprint,
                "reviewer": reviewer,
                "confirmed_at": now,
                "expires_at": now + 86400,
                "production_activation": False,
            }
        ),
    )


def revoke_key(path, reviewer, *, now):
    path = directory(path)
    label(reviewer)
    stamp(now)
    record, _ = public_record(read(path / "candidate.json"))
    write(
        path / "revoked.json",
        encode({"fingerprint": record["fingerprint"], "reviewer": reviewer, "revoked_at": now}),
    )


def trusted_key(path, expected_fingerprint, *, now):
    path = directory(path)
    stamp(now)
    record, key = public_record(read(path / "candidate.json"))
    if os.path.lexists(path / "revoked.json"):
        # Any revocation marker blocks, even if its contents are damaged.
        raise ValueError("Staged trust is revoked")
    decision = decode(read(path / "key-confirmation.json"))
    if (
        not isinstance(decision, dict)
        or set(decision)
        != {"issuer_key_id", "fingerprint", "reviewer", "confirmed_at", "expires_at", "production_activation"}
        or decision["fingerprint"] != expected_fingerprint
        or expected_fingerprint != fingerprint(key)
        or decision["issuer_key_id"] != record["issuer_key_id"]
        or decision["production_activation"] is not False
        or stamp(decision["confirmed_at"]) > now
        or stamp(decision["expires_at"]) <= now
        or decision["expires_at"] - decision["confirmed_at"] != 86400
    ):
        raise ValueError("Independent staged trust confirmation required")
    label(decision["reviewer"])
    return key


def main():
    parser = argparse.ArgumentParser(
        description="Stage a dedicated encrypted issuer; never activates trust or inference"
    )
    parser.add_argument("destination")
    parser.add_argument("--issuer-key-id", required=True)
    args = parser.parse_args()
    import time

    try:
        print(json.dumps(create_issuer(args.destination, args.issuer_key_id, now=int(time.time()))))
    except Exception:
        raise SystemExit("Staged issuer provisioning rejected; inspect protected files locally") from None


if __name__ == "__main__":
    main()
