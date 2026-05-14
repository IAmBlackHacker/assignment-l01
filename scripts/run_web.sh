#!/usr/bin/env bash
# Run FastAPI server + Vite dev server concurrently for development.
set -euo pipefail
cd "$(dirname "$0")/.."

# Activate venv
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Start FastAPI in the background
uvicorn web.server:app --reload --port 8000 &
API_PID=$!

# Trap to clean up on exit
cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# Run Vite (foreground)
cd web-ui
npm run dev
