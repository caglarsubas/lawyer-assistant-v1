#!/usr/bin/env python3
"""Create a private, wholly invented three-practice extraction study.

Only the fixed TXT samples in this file enter the bounded local parser. The
five-file dossier is read as data and pinned by digest; no supplied originals,
settings, credentials, reviews or providers are accessed or modified. Synthetic
success establishes neither real-corpus coverage nor legal or rights approval.
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

# These original text/locator expectations are authored before running the parser.
# Never derive a reference transcription from the extraction being evaluated.
SAMPLES = (
    ("contracts", (
        ("Paragraf 1", "SENTETİK SÖZLEŞME ÖRNEĞİ. Bu uydurma metin hukuk kuralı veya gerçek dosya değildir."),
        ("Paragraf 2", "TEST-SOZ-010 kaydında tarih 12.03.2022, tutar 2.345,67 TL olarak yazılmıştır."),
        ("Paragraf 3", "Ödeme yapılmadı. Yazılı izin varsa teslim koşulu uygulanmaz."),
    ), (
        (1, "TEST-SOZ-010", "identifier"), (1, "12.03.2022", "date"), (1, "2.345,67 TL", "amount"),
        (2, "Ödeme yapılmadı", "negation"), (2, "Yazılı izin varsa", "exception"),
    )),
    ("commercial", (
        ("Paragraf 1", "SENTETİK TİCARİ KAYIT. Hiçbir gerçek şirketi, işlemi veya yargı kararını anlatmaz."),
        ("Paragraf 2", "TEST-TIC-020 için 08.09.2023 tarihinde 9.876,54 TL tutarı kaydedildi."),
        ("Paragraf 3", "Mal teslim edilmedi. Kontrol kaydı varsa bu deneme adımı atlanır."),
    ), (
        (1, "TEST-TIC-020", "identifier"), (1, "08.09.2023", "date"), (1, "9.876,54 TL", "amount"),
        (2, "Mal teslim edilmedi", "negation"), (2, "Kontrol kaydı varsa", "exception"),
    )),
    ("employment", (
        ("Paragraf 1", "SENTETİK ÇALIŞMA ÖRNEĞİ. Tamamı uydurmadır; bir kişiye veya hukuki sonuca işaret etmez."),
        ("Paragraf 2", "TEST-ISC-030 denemesinde 27.11.2024 tarihi ve 5.432,10 TL tutarı kullanıldı."),
        ("Paragraf 3", "Bildirim gönderilmedi. Ek kayıt bulunursa bu test koşulu değişir."),
    ), (
        (1, "TEST-ISC-030", "identifier"), (1, "27.11.2024", "date"), (1, "5.432,10 TL", "amount"),
        (2, "Bildirim gönderilmedi", "negation"), (2, "Ek kayıt bulunursa", "exception"),
    )),
)


class FixtureError(ValueError):
    """Fixed safe diagnostic, without submitted paths or parser text."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid synthetic-study arguments; use --help.\n")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _extractor_version():
    files = {name: _sha256((ROOT / "backend" / "app" / name).read_bytes())
             for name in ("extract.py", "extraction_worker.py", "extraction_client.py")}
    return "sha256-" + _sha256(_json_bytes(files))


def _parse_known_text(raw):
    from app.extraction_client import ExtractionError
    from app.extraction_worker import parse_document

    try:
        return parse_document(raw, ".txt")
    except ExtractionError:
        raise FixtureError("synthetic_parser_failed") from None


def _prepare_package(dossier_report):
    from app.calibration_study import StudyManifest, evaluate_study
    from app.extraction_calibration import CalibrationSample, evaluate_calibration

    version = _extractor_version()
    artifacts, entries, timings = {}, [], []
    for practice, passages, critical in SAMPLES:
        raw = ("\n\n".join(text for _, text in passages) + "\n").encode()
        start = time.perf_counter()
        extraction = _parse_known_text(raw)
        elapsed = time.perf_counter() - start
        expected = {"passages": [{"locator": locator, "text": text} for locator, text in passages],
                    "warnings": [], "page_count": None, "passage_count": len(passages)}
        if extraction != expected:
            raise FixtureError("synthetic_extraction_differs_from_independent_reference")
        reference_passages = []
        for ordinal, (locator, text) in enumerate(passages):
            spans = []
            for index, literal, category in critical:
                if index == ordinal:
                    start = text.index(literal)
                    spans.append({"start": start, "end": start + len(literal), "category": category})
            reference_passages.append({"ordinal": ordinal, "locator": locator, "text": text, "critical_spans": spans})
        reference = {"schema_version": "reference-transcription-v1", "raw_sha256": _sha256(raw),
                     "coverage": "complete", "reference_status": "unreviewed", "passages": reference_passages}
        extracted_bytes, reference_bytes = _json_bytes(extraction), _json_bytes(reference)
        sample = {
            "schema_version": "extraction-calibration-sample-v1", "sample_kind": "synthetic",
            "data_classification": "synthetic_fixture", "practice": practice, "recorded_on": "2026-10-05",
            "source_suffix": ".txt", "raw_sha256": _sha256(raw),
            "extraction_sha256": _sha256(extracted_bytes), "reference_sha256": _sha256(reference_bytes),
            "extractor_id": "isolated-extractor", "extractor_version": version,
            "extraction_elapsed_seconds": elapsed,
        }
        comparison = evaluate_calibration(CalibrationSample.model_validate(sample), raw,
                                          extracted_bytes, reference_bytes)["comparison"]
        if not comparison["full_reference_comparison_passed"]:
            raise FixtureError("synthetic_comparison_did_not_pass")
        sample_bytes = _json_bytes(sample)
        for content in (sample_bytes, raw, extracted_bytes, reference_bytes):
            artifacts[_sha256(content) + ".bin"] = content
        entries.append({
            "sample_sha256": _sha256(sample_bytes), "raw_sha256": sample["raw_sha256"],
            "extraction_sha256": sample["extraction_sha256"], "reference_sha256": sample["reference_sha256"],
            "source_identity_sha256": sample["raw_sha256"], "sample_kind": "synthetic", "practice": practice,
            "source_family_id": None, "layout": "born_digital", "unit": "documents", "observed_units": 1,
            "reviewer_seconds": None, "assessed_items": None, "disagreements": None,
        })
        timings.append(elapsed)
    if version != _extractor_version():
        raise FixtureError("extractor_changed_during_generation")
    manifest = {"schema_version": "extraction-calibration-study-v1", "dossier_sha256": dossier_report["dossier_sha256"],
                "recorded_on": "2026-10-05", "entries": entries}
    evaluate_study(StudyManifest.model_validate(manifest), artifacts, dossier_report, set())
    return _json_bytes(manifest), artifacts, timings


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


def _cleanup(parent_fd, root_name, root_fd, children, written):
    # Remove only identities created by this invocation. Never force recursive cleanup.
    for directory_fd, filename, identity in reversed(written):
        try:
            info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and _identity(info) == identity:
                os.unlink(filename, dir_fd=directory_fd)
        except OSError:
            pass
    for name, descriptor in reversed(children):
        try:
            _check_binding(root_fd, name, descriptor)
            os.rmdir(name, dir_fd=root_fd)
        except (OSError, FixtureError):
            pass
    if root_fd is not None:
        try:
            _check_binding(parent_fd, root_name, root_fd)
            os.rmdir(root_name, dir_fd=parent_fd)
        except (OSError, FixtureError):
            pass


def build_fixture(destination: Path, dossier_directory: Path) -> dict:
    """Write one new synthetic package, keeping all original dossier bytes unchanged."""
    from app.qualification import inspect_components, read_components
    from app.qualification_evidence import _check_chain, _directory_chain

    target = Path(destination)
    if not target.name or ".." in target.parts:
        raise FixtureError("destination_must_be_new")
    with _directory_chain(target.parent) as (descriptors, names):
        parent_fd = descriptors[-1]
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FixtureError("destination_must_be_new")
        original_dossier = read_components(dossier_directory)
        dossier_report = inspect_components(original_dossier)
        manifest, artifacts, timings = _prepare_package(dossier_report)
        if read_components(dossier_directory) != original_dossier:
            raise FixtureError("dossier_changed_during_generation")
        _check_chain(descriptors, names)
        root_fd, children, written = None, [], []
        try:
            root_fd = _create_private_directory(parent_fd, target.name)
            for name in ("study", "artifacts"):
                descriptor = _create_private_directory(root_fd, name)
                children.append((name, descriptor))
            study_fd, artifact_fd = [descriptor for _, descriptor in children]
            for name, content in artifacts.items():
                written.append((artifact_fd, name, _write_new_file(artifact_fd, name, content)))
            written.append((study_fd, "study.json", _write_new_file(study_fd, "study.json", manifest)))
            if read_components(dossier_directory) != original_dossier:
                raise FixtureError("dossier_changed_during_generation")
            for name, descriptor in children:
                _check_binding(root_fd, name, descriptor)
                os.fsync(descriptor)
            _check_binding(parent_fd, target.name, root_fd)
            _check_chain(descriptors, names)
            os.fsync(root_fd)
            os.fsync(parent_fd)
        except BaseException:
            _cleanup(parent_fd, target.name, root_fd, children, written)
            raise
        finally:
            for _, descriptor in reversed(children):
                os.close(descriptor)
            if root_fd is not None:
                os.close(root_fd)
    return {
        "status": "synthetic_study_fixture_created", "sample_kind": "synthetic",
        "data_classification": "synthetic_fixture", "sample_count": len(SAMPLES),
        "artifact_count": len(artifacts), "practice_count": 3, "observed_documents": len(SAMPLES),
        "critical_span_count": sum(len(critical) for _, _, critical in SAMPLES),
        "extraction_elapsed_seconds": sum(timings),
        "timing_scope": "generated_fixture_parser_call_wall_time_including_startup",
        "reference_status": "unreviewed", "real_corpus_measurements": 0,
        "dossier_sha256": dossier_report["dossier_sha256"], "dossier_modified": False,
        "independent_literal_reference_matched": True,
        "runtime_authorization": "none", "production_qualified": False,
    }


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("destination", type=Path, help="New package root under an existing real parent")
    parser.add_argument("--dossier-dir", type=Path, default=ROOT / "qualification",
                        help="Existing five-file R01 dossier; read only")
    args = parser.parse_args(argv)
    try:
        result = build_fixture(args.destination, args.dossier_dir)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print(json.dumps({"status": "study_fixture_generation_failed", "runtime_authorization": "none",
                          "production_qualified": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
