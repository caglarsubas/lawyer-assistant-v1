#!/bin/sh
set -eu
# The validator holds a shared publication lock through JVM exec. It builds
# private TDB2 indexes from signed immutable N-Quads before exposing queries.
exec python3 /opt/fuseki/runtime.py
