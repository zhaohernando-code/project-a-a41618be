#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_FRONTEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.frontend.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

FRONTEND_DIR="$REPO_ROOT/frontend"
PORT="${ASHARE_LOCAL_FRONTEND_PORT:-5173}"

cd "$FRONTEND_DIR"
npm run build
exec npx vite preview --host 127.0.0.1 --port "$PORT"
