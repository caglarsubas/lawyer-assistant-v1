#!/usr/bin/env python3
"""Create a NEW private secret directory; never activates or rotates existing data."""

import argparse
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from cryptography.fernet import Fernet  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402

from app.runtime_secrets import read_secret_file  # noqa: E402


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid secret provisioning arguments; use --help.\n")


def main():
    p = Parser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--provider-key-file", type=Path)
    p.add_argument("--database-host", default="postgres")
    p.add_argument("--database-user", default="lawyer")
    p.add_argument("--database-name", default="lawyer")
    a = p.parse_args()
    if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", x)
           for x in [a.database_host, a.database_user, a.database_name]):
        raise ValueError("Unsupported database identity")
    parent = a.directory.parent.resolve(strict=True)
    target = parent / a.directory.name
    if target.exists() or target.is_symlink():
        raise ValueError("Destination must be new")
    values = {name: secrets.token_urlsafe(36) for name in
              ["postgres_password", "bootstrap_password", "extraction_token", "gateway_token"]}
    values["encryption_key"] = Fernet.generate_key().decode()
    values["provider_api_key"] = read_secret_file(a.provider_key_file, allow_empty=True) if a.provider_key_file else ""
    values["database_url"] = URL.create("postgresql+psycopg", username=a.database_user,
        password=values["postgres_password"], host=a.database_host, port=5432,
        database=a.database_name).render_as_string(hide_password=False)
    target.mkdir(mode=0o700)
    for name, value in values.items():
        fd = os.open(target / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(value.encode() + b"\n")
            out.flush()
            os.fsync(out.fileno())
    print("Created seven owner-only secret files. Existing data/configuration were not changed.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit("Secret provisioning failed; no secret values emitted. Inspect the private destination before retrying.")
