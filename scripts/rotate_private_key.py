#!/usr/bin/env python3
"""Offline private-record rotation. Writers stopped + authenticated backup required."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import json  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402

from app.runtime_key_rotation import recover, rotate  # noqa: E402
from app.runtime_secrets import read_secret_file  # noqa: E402


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid offline rotation arguments; use --help.\n")


def main():
    p = Parser(description=__doc__)
    p.add_argument("operation", choices=["rotate", "recover"])
    p.add_argument("--database-url-file", required=True, type=Path)
    p.add_argument("--old-key-file", required=True, type=Path)
    p.add_argument("--new-key-file", required=True, type=Path)
    p.add_argument("--data-dir", required=True, type=Path)
    p.add_argument("--writers-stopped", required=True, action="store_true")
    p.add_argument("--authenticated-backup-verified", required=True, action="store_true")
    a = p.parse_args()
    if not a.writers_stopped or not a.authenticated_backup_verified:
        raise ValueError("Missing prerequisites")
    engine = create_engine(read_secret_file(a.database_url_file), hide_parameters=True,
                           connect_args={"connect_timeout": 5})
    try:
        operation = rotate if a.operation == "rotate" else recover
        result = operation(engine, a.data_dir, read_secret_file(a.old_key_file).encode(),
                           read_secret_file(a.new_key_file).encode())
        print(json.dumps(result, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit("Offline rotation stopped. Keep writers stopped; retain the journal and authenticated backup. No secret values emitted.")
