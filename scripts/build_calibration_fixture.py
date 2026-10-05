#!/usr/bin/env python3
"""Generate one private synthetic calibration package using the actual local TXT parser.

Only the invented content below is parsed. The destination must be new under an
existing non-symlink parent. This command never reads user documents, application
settings, .env, provider accounts or review ledgers. Success tests a synthetic
extraction contract; it is not real-corpus or legal qualification.
"""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# These literal paragraphs and their expected locators are authored independently
# of parser output. Never replace this oracle with output-derived transcription.
GOLD_PASSAGES = (
    ("Paragraf 1", ("SENTETİK TEKNİK ÖRNEK — Türkçe karakterler: ı İ ş Ş ğ Ğ ü Ü ö Ö ç Ç. "
                    "Bu metin hukuk kuralı değildir.")),
    ("Paragraf 2", "Deneme kaydı: 14.06.2020 tarihinde 1.234,56 TL tutarında bir değer yazıldı; ödeme yapılmadı."),
    ("Paragraf 3", "Tamamı uydurma test verisidir. Belge kimliği TEST-KAYIT-0042; taraf veya gerçek dava içermez."),
)
RAW_BYTES = ("\n\n".join(text for _, text in GOLD_PASSAGES) + "\n").encode("utf-8")
CRITICAL_TEXT = {1: (("14.06.2020", "date"), ("1.234,56 TL", "amount"), ("ödeme yapılmadı", "negation")),
                 2: (("TEST-KAYIT-0042", "identifier"),)}
FIXED_FILES = ("sample.json", "raw.bin", "extraction.json", "reference.json")


class FixtureError(ValueError):
    """Fixed diagnostic; caller must never append parser or filesystem details."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid synthetic-fixture arguments; use --help.\n")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _extractor_version():
    # Pin the subprocess implementation and its bounded launcher, not an API model
    # name or an unverified installed-service version. No credentials are read.
    files = {name: _sha256((ROOT / "backend" / "app" / name).read_bytes())
             for name in ("extract.py", "extraction_worker.py", "extraction_client.py")}
    return "sha256-" + _sha256(_json_bytes(files))


def _parse_known_text():
    from app.extraction_client import ExtractionError
    from app.extraction_worker import parse_document

    try:
        return parse_document(RAW_BYTES, ".txt")
    except ExtractionError:
        raise FixtureError("synthetic_parser_failed") from None


def _prepare_package():
    from app.extraction_calibration import CalibrationSample, evaluate_calibration

    version = _extractor_version()
    start = time.perf_counter()
    extraction = _parse_known_text()
    elapsed = time.perf_counter() - start
    if _extractor_version() != version:
        raise FixtureError("extractor_changed_during_generation")
    expected = {"passages": [{"locator": locator, "text": text} for locator, text in GOLD_PASSAGES],
                "warnings": [], "page_count": None, "passage_count": len(GOLD_PASSAGES)}
    if extraction != expected:
        raise FixtureError("synthetic_extraction_differs_from_independent_reference")
    reference_passages = []
    for ordinal, (locator, text) in enumerate(GOLD_PASSAGES):
        spans = []
        for literal, category in CRITICAL_TEXT.get(ordinal, ()):
            position = text.index(literal)
            spans.append({"start": position, "end": position + len(literal), "category": category})
        reference_passages.append({"ordinal": ordinal, "locator": locator, "text": text, "critical_spans": spans})
    reference = {"schema_version": "reference-transcription-v1", "raw_sha256": _sha256(RAW_BYTES),
                 "coverage": "complete", "reference_status": "unreviewed", "passages": reference_passages}
    extraction_bytes, reference_bytes = _json_bytes(extraction), _json_bytes(reference)
    sample = {
        "schema_version": "extraction-calibration-sample-v1", "sample_kind": "synthetic",
        "data_classification": "synthetic_fixture", "practice": "contracts", "recorded_on": "2026-10-05",
        "source_suffix": ".txt", "raw_sha256": _sha256(RAW_BYTES),
        "extraction_sha256": _sha256(extraction_bytes), "reference_sha256": _sha256(reference_bytes),
        "extractor_id": "isolated-extractor", "extractor_version": version,
        "extraction_elapsed_seconds": elapsed,
    }
    report = evaluate_calibration(CalibrationSample.model_validate(sample), RAW_BYTES,
                                  extraction_bytes, reference_bytes)
    if not (report["comparison"]["all_declared_checks_passed"]
            and report["comparison"]["full_reference_comparison_passed"]):
        raise FixtureError("synthetic_comparison_did_not_pass")
    files = {"sample.json": _json_bytes(sample), "raw.bin": RAW_BYTES,
             "extraction.json": extraction_bytes, "reference.json": reference_bytes}
    return files, elapsed


def _open_parent(destination):
    target = Path(destination).absolute()
    if not target.name or ".." in target.parts:
        raise FixtureError("destination_must_be_new")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(target.anchor, flags)
    try:
        for part in target.parts[1:-1]:
            child = os.open(part, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return parent_fd, target.name
        raise FixtureError("destination_must_be_new")
    except BaseException:
        os.close(parent_fd)
        raise


def _identity(info):
    return info.st_dev, info.st_ino


def _write_new_file(directory_fd, name, content):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    identity = _identity(os.fstat(fd))
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return identity
    except BaseException:
        try:
            if _identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) == identity:
                os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
        raise


def _create_private_directory(parent_fd, name):
    """Adopt only a fresh empty private directory, without changing its permissions.

    mkdir does not return an inode handle. These checks detect ordinary replacement
    and refuse existing contents; they cannot authenticate creation against a
    privileged or malicious same-UID process controlling the destination tree.
    """
    os.mkdir(name, 0o700, dir_fd=parent_fd)
    created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (not stat.S_ISDIR(created.st_mode) or stat.S_IMODE(created.st_mode) != 0o700
            or created.st_uid != os.geteuid()):
        raise FixtureError("destination_changed_during_generation")
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent_fd)
    try:
        opened = os.fstat(descriptor)
        if (_identity(opened) != _identity(created) or not stat.S_ISDIR(opened.st_mode)
                or stat.S_IMODE(opened.st_mode) != 0o700 or opened.st_uid != os.geteuid()):
            raise FixtureError("destination_changed_during_generation")
        with os.scandir(descriptor) as entries:
            if next(entries, None) is not None:
                raise FixtureError("destination_changed_during_generation")
        _check_binding(parent_fd, name, descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _check_binding(parent_fd, name, descriptor):
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(linked.st_mode) or _identity(linked) != _identity(os.fstat(descriptor)):
        raise FixtureError("destination_changed_during_generation")


def build_fixture(destination: Path) -> dict:
    """Create a new fixture directory; no arbitrary input or overwrite option exists."""
    parent_fd, name = _open_parent(destination)
    directory_fd = None
    directory_identity = None
    written = {}
    created = False
    try:
        files, elapsed = _prepare_package()
        # mkdirat is exclusive: a destination created during parsing is preserved.
        directory_fd = _create_private_directory(parent_fd, name)
        created = True
        directory_identity = _identity(os.fstat(directory_fd))
        for filename in FIXED_FILES:
            written[filename] = _write_new_file(directory_fd, filename, files[filename])
        os.fsync(directory_fd)
        if _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != directory_identity:
            raise FixtureError("destination_changed_during_generation")
        os.fsync(parent_fd)
        return {
            "status": "synthetic_fixture_created", "sample_kind": "synthetic",
            "data_classification": "synthetic_fixture", "file_count": len(FIXED_FILES),
            "passage_count": len(GOLD_PASSAGES), "raw_bytes": len(RAW_BYTES),
            "extraction_elapsed_seconds": elapsed,
            "timing_scope": "generated_fixture_parser_call_wall_time_including_startup",
            "reference_status": "unreviewed", "real_corpus_measurements": 0,
            "independent_literal_reference_matched": True,
            "runtime_authorization": "none", "production_qualified": False,
        }
    except BaseException:
        if directory_fd is not None:
            for filename, identity in written.items():
                try:
                    info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode) and _identity(info) == identity:
                        os.unlink(filename, dir_fd=directory_fd)
                except OSError:
                    pass
        if created and directory_identity is not None:
            try:
                if _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) == directory_identity:
                    os.rmdir(name, dir_fd=parent_fd)
            except OSError:
                pass  # Never remove unrelated files to force cleanup.
        raise
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent_fd)


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("destination", type=Path, help="New output directory under an existing parent")
    args = parser.parse_args(argv)
    try:
        result = build_fixture(args.destination)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print(json.dumps({"status": "fixture_generation_failed", "runtime_authorization": "none",
                          "production_qualified": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
