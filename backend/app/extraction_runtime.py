"""Current extractor service with format-specific parser entry points."""

import subprocess
import sys
from types import FunctionType, SimpleNamespace

import uvicorn

from . import extraction_worker

_PARSERS = {".pdf": "app.pdf_severe_extract", ".docx": "app.docx_extract"}


def _start_parser(command, **kwargs):
    if len(command) == 5 and command[:3] == [sys.executable, "-m", "app.extract"]:
        parser = _PARSERS.get(command[-1])
        if parser:
            command = [sys.executable, "-m", parser, *command[3:]]
    return subprocess.Popen(command, **kwargs)


def _bind(function, **dependencies):
    # The historical worker is source-pinned. Bind only these functions to a
    # private namespace so the original worker and Python subprocess module
    # remain suitable for reproducing its qualification.
    namespace = {**function.__globals__, **dependencies}
    return FunctionType(function.__code__, namespace, argdefs=function.__defaults__,
                        closure=function.__closure__)


def create_app(token=None):
    launcher = SimpleNamespace(Popen=_start_parser, DEVNULL=subprocess.DEVNULL,
                               TimeoutExpired=subprocess.TimeoutExpired)
    parse = _bind(extraction_worker.parse_document, subprocess=launcher)
    factory = _bind(extraction_worker.create_app, parse_document=parse)
    return factory(token)


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=8002, access_log=False, limit_concurrency=8,
                timeout_keep_alive=5, h11_max_incomplete_event_size=16384)
