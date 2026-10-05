#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
if [[ ! -x backend/.venv/bin/python || ! -d frontend/node_modules ]]; then
  echo 'Install development dependencies first: (cd backend && uv sync --frozen --extra dev); (cd frontend && npm ci)' >&2
  exit 1
fi
if [[ -n "${LA_DATABASE_URL:-}" && "${LA_DATABASE_URL}" != sqlite:* ]]; then
  echo 'Demo launcher refuses a non-SQLite database. Use Compose for the configured deployment.' >&2
  exit 1
fi
# This launcher never sources .env, reads the provider credential, or changes an existing user.
# Process values override file settings. Demo state is isolated from a configured installation.
export LA_DEMO_MODE=true
export LA_DATABASE_URL="sqlite:///$ROOT/.data/demo/workspace.db"
export LA_DATA_DIR="$ROOT/.data/demo"
export LA_COOKIE_SECURE=false
export LA_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
export LA_GATEWAY_ENABLED=false LA_GATEWAY_URL= LA_GATEWAY_TOKEN=
export LA_GRAPH_URL= LA_OPENSEARCH_URL= LA_SEARCH_RELEASE_ID=
export LA_EXTRACTION_URL= LA_EXTRACTION_TOKEN=
export LLM_PROVIDER_BASE_URL= LLM_PROVIDER_API_KEY= LLM_PROVIDER_MODEL=
export LLM_PROVIDER_IDENTITY_VERIFIED=false
mkdir -p "$LA_DATA_DIR"
API_PID=
WEB_PID=
cleanup() {
  [[ -z "$WEB_PID" ]] || kill "$WEB_PID" 2>/dev/null || true
  [[ -z "$API_PID" ]] || kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
PYTHONPATH="$ROOT/backend" backend/.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log &
API_PID=$!
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort &
WEB_PID=$!
echo 'Synthetic local demo: http://127.0.0.1:5173 — demo / demo-local-only'
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do sleep 1; done
echo 'One development service stopped; shutting down the other.' >&2
exit 1
