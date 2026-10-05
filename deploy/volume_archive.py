"""Offline encrypted volume transfer, executed only inside the API image.

Restore accepts regular files/directories only, verifies a complete encrypted
archive before writing, and never replaces a nonempty volume. Keys are mounted
separately; application secrets are deliberately not part of this archive.
"""

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOTS = {
    "documents": Path("/data"),
    "postgres": Path("/var/lib/postgresql/data"),
    "opensearch": Path("/usr/share/opensearch/data"),
    "graphs": Path("/fuseki"),
    "public_sources": Path("/public-sources"),
}
MANIFEST = "manifest.json"


def safe_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Unsafe archive path")
    if path.parts[0] not in ROOTS and member.name != MANIFEST:
        raise ValueError("Unexpected archive root")
    if not (member.isfile() or member.isdir()):
        raise ValueError("Links, devices and special files are not supported")
    if member.name == MANIFEST and (not member.isfile() or member.size > 65536):
        raise ValueError("Invalid backup manifest")


def require_empty() -> None:
    for name, root in ROOTS.items():
        if not root.is_dir() or root.is_symlink():
            raise ValueError("Restore requires five existing, empty target volumes")
        entries = list(root.iterdir())
        if name == "graphs":
            # A fresh Fuseki image seeds only its empty publication scaffolding.
            # No release, pointer, old database or nonempty lock may be overwritten.
            entries = [p for p in entries if not (
                not p.is_symlink() and ((p.name in {'publication.lock', '.install.lock'} and p.is_file() and p.stat().st_size == 0)
                                        or (p.name == 'releases' and p.is_dir() and not any(p.iterdir()))))]
        if entries:
            raise ValueError("Restore requires five existing, empty target volumes")


def export_archive() -> None:
    manifest = {
        "format": "lawyer-assistant-cold-volumes-v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "images": json.loads(os.environ["LA_ARCHIVE_IMAGES"]),
        "roots": list(ROOTS),
        "secrets_included": False,
    }
    recipient = Path("/run/secrets/backup-recipients")
    with subprocess.Popen(
        ["age", "--recipients-file", str(recipient)], stdin=subprocess.PIPE, stdout=sys.stdout.buffer
    ) as age:
        assert age.stdin is not None
        try:
            with tarfile.open(fileobj=age.stdin, mode="w|gz") as archive:
                data = json.dumps(manifest).encode()
                info = tarfile.TarInfo(MANIFEST)
                info.size = len(data)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(data))
                for name, path in ROOTS.items():
                    archive.add(path, arcname=name, recursive=True, filter=_export_filter)
        finally:
            age.stdin.close()
        if age.wait() != 0:
            raise RuntimeError("Backup encryption failed")


def _export_filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
    safe_member(member)
    return member


def read_archive(*, extract: bool = False) -> dict:
    """Read the entire age stream, including authentication at its end."""
    manifest = None
    seen = set()
    roots = set()
    expected = json.loads(os.environ["LA_ARCHIVE_IMAGES"])
    with subprocess.Popen(
        ["age", "--decrypt", "--identity", "/run/secrets/backup-identity", "/backup/archive.age"],
        stdout=subprocess.PIPE,
    ) as age:
        assert age.stdout is not None
        try:
            with tarfile.open(fileobj=age.stdout, mode="r|gz") as archive:
                for member in archive:
                    safe_member(member)
                    if member.name in seen:
                        raise ValueError("Duplicate archive member")
                    seen.add(member.name)
                    if member.name == MANIFEST:
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise ValueError("Missing backup manifest")
                        manifest = json.load(stream)
                        if manifest.get("format") != "lawyer-assistant-cold-volumes-v2":
                            raise ValueError("Unsupported backup format")
                        if manifest.get("images") != expected:
                            raise ValueError("Restore requires the exact source container images")
                        if set(manifest.get("roots", [])) != set(ROOTS):
                            raise ValueError("Incomplete backup volume set")
                        continue
                    if manifest is None:
                        raise ValueError("Manifest must precede volume data")
                    path = PurePosixPath(member.name)
                    roots.add(path.parts[0])
                    if extract:
                        # safe_member rejected traversal, links and special files.
                        # Preserve numeric ownership required by the database images.
                        root = ROOTS[path.parts[0]]
                        relative = PurePosixPath(*path.parts[1:])
                        member.name = str(relative)
                        archive.extract(member, path=root, set_attrs=True, numeric_owner=True,
                                        filter="fully_trusted")
            # tar's end marker is before the end of the encryption stream.
            # Drain it so truncation or authentication failure is never missed.
            while age.stdout.read(1024 * 1024):
                pass
        except BaseException:
            age.kill()
            age.wait()
            raise
        if age.wait() != 0:
            raise ValueError("Backup authentication/decryption failed")
    if manifest is None or roots != set(ROOTS):
        raise ValueError("Incomplete backup")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore"])
    args = parser.parse_args()
    try:
        if args.action == "backup":
            export_archive()
        else:
            require_empty()
            read_archive()  # Full authenticated preflight, with no writes.
            require_empty()
            try:
                read_archive(extract=True)
            finally:
                invalidate_restored_publication()
    except (ValueError, RuntimeError, OSError, tarfile.TarError) as error:
        print(f"Volume transfer failed: {error}", file=sys.stderr)
        return 1
    return 0


def invalidate_restored_publication() -> None:
    """A restored historical review ledger cannot revive publication permission.

    Keep the signed records for review, but remove their old epoch even following
    interrupted extraction. The trusted operator must initialize a fresh epoch
    and obtain new independent authorizations before retrieval can resume.
    """
    epoch = ROOTS["documents"] / "publication-epoch"
    if epoch.exists() or epoch.is_symlink():
        if epoch.is_symlink() or not epoch.is_file():
            raise ValueError("Invalid restored publication policy")
        epoch.unlink()
        descriptor = os.open(epoch.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
