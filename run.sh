#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
HOST="${HOST:-127.0.0.1}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

"$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"

if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  npm --prefix "$ROOT_DIR/frontend" install
fi

echo "Backend:  http://$HOST:$BACKEND_PORT"
echo "Frontend: http://$HOST:$FRONTEND_PORT"

(
  cd "$ROOT_DIR/backend"
  "$ROOT_DIR/.venv/bin/uvicorn" app.main:app \
    --host "$HOST" \
    --port "$BACKEND_PORT" \
    --reload
) &
BACKEND_PID=$!

(
  cd "$ROOT_DIR/frontend"
  NEXT_PUBLIC_API_BASE_URL="http://$HOST:$BACKEND_PORT" \
    npm run dev -- -H "$HOST" -p "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

wait
