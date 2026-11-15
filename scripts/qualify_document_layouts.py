"""Record exact layout observations using the native, isolated parser."""

import argparse
import hashlib
import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

from document_layout_cases import make_docx_case, make_pdf_case
from fastapi.testclient import TestClient

from app import extract
from app.extraction_worker import create_app


def sha256(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def passage_bindings(passages):
    return [{"locator": locator, "text_sha256": sha256(text)} for locator, text in passages]


def compare(case, result):
    actual = tuple((row["locator"], row["text"]) for row in result["passages"])
    omissions = []
    for locator, text in case.omitted_passages:
        omissions.append({
            "locator": locator,
            "reference_text_sha256": sha256(text),
            "reference_text_found": any(text in seen_text for _, seen_text in actual),
            "page_warning": any(warning.startswith(locator + ":") for warning in result["warnings"]),
        })
    return {
        "filename": case.filename,
        "original_sha256": sha256(case.content),
        "media_bytes": len(case.content),
        "page_count": result["page_count"],
        "extraction_profile": result.get("extraction_profile"),
        "expected_passages": passage_bindings(case.expected_passages),
        "observed_passages": passage_bindings(actual),
        "expected_text_and_locators_match": actual == case.expected_passages,
        "omitted_reference_passages": omissions,
        "warnings": result["warnings"],
    }


def tool_version(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=True)
    return (result.stdout or result.stderr).splitlines()[0]


def qualify(font):
    languages = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=5, check=True)
    if not {"tur", "eng"} <= set(languages.stdout.splitlines()[1:]):
        raise ValueError("Turkish and English native OCR language data required")
    app = Path(extract.__file__).resolve().parent
    source = {name: sha256((app / name).read_bytes()) for name in
              ("extract.py", "extraction_client.py", "extraction_worker.py", "docx_textboxes.py")}
    cases = (make_pdf_case(font), make_docx_case())
    reports = []
    token = "synthetic-document-layout-token-only"
    with TestClient(create_app(token)) as client:
        for case in cases:
            response = client.post("/extract", content=case.content, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "X-Document-Suffix": Path(case.filename).suffix,
            })
            reports.append(compare(case, response.raise_for_status().json()))
    pdf, docx = reports
    observed = (all(report["expected_text_and_locators_match"] for report in reports)
                and pdf["page_count"] == 6 and docx["extraction_profile"] == "docx-textboxes-v5"
                and [(row["locator"], row["reference_text_found"], row["page_warning"])
                     for row in pdf["omitted_reference_passages"]] == [
                         ("Sayfa 2", False, False), ("Sayfa 6", False, True),
                     ]
                and all(any(warning.startswith(f"Sayfa {page}: OCR kullanıldı;") for warning in pdf["warnings"])
                        for page in (3, 4, 5)))
    return {
        "schema": "synthetic-document-layout-observation-v1",
        "matches_declared_observation": observed,
        "synthetic_only": True,
        "transport": "authenticated_isolated_extraction",
        "parser_source_sha256": source,
        "fixture_source_sha256": sha256(Path(__file__).with_name("document_layout_cases.py").read_bytes()),
        "font_sha256": sha256(font.read_bytes()),
        "versions": {"python": platform.python_version(), "architecture": platform.machine(),
                     **{package: version(package) for package in
                        ("pypdf", "Pillow", "reportlab", "python-docx", "pytesseract")},
                     "tesseract": tool_version(["tesseract", "--version"]),
                     "pdftoppm": tool_version(["pdftoppm", "-v"])},
        "cases": reports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, required=True, help="Local TrueType font used for the synthetic raster pages")
    args = parser.parse_args()
    report = qualify(args.font)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["matches_declared_observation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
