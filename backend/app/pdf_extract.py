"""Resource-bounded PDF extraction with page-specific coverage warnings."""

import json
import resource
import sys
from pathlib import Path

from .extract import extract
from .pdf_image_coverage import add_pdf_coverage_warnings


def main():
    if len(sys.argv) != 3 or sys.argv[2] != ".pdf":
        return 1
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    try:
        source = Path(sys.argv[1])
        result = add_pdf_coverage_warnings(source, extract(source, ".pdf"))
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        # Only the isolated worker's controlled failure reaches the caller.
        # Do not log content, paths or parser exception details.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
