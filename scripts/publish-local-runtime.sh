#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$HOME/codex/runtime/projects/ashare-dashboard}"
BACKEND_URL="${ASHARE_LOCAL_BACKEND_URL:-http://127.0.0.1:8000/health}"
FRONTEND_URL="${ASHARE_LOCAL_FRONTEND_URL:-http://127.0.0.1:5173/}"
LOCAL_API_BASE_URL="${ASHARE_LOCAL_API_BASE_URL:-http://127.0.0.1:8000/}"
CANONICAL_BASE_URL="${ASHARE_CANONICAL_BASE_URL:-https://hernando-zhao.cn/projects/ashare-dashboard/}"
RSYNC_BIN="${RSYNC_BIN:-rsync}"
MAX_WAIT_SECONDS="${ASHARE_PUBLISH_MAX_WAIT_SECONDS:-30}"

if ! command -v "$RSYNC_BIN" >/dev/null 2>&1; then
  echo "Missing required command: $RSYNC_BIN" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Missing required command: npm" >&2
  exit 1
fi

if ! command -v launchctl >/dev/null 2>&1; then
  echo "Missing required command: launchctl" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing required command: curl" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing required command: python3" >&2
  exit 1
fi

LOCK_DIR="$HOME/.codex-system/locks"
PUBLISH_LOCK="$LOCK_DIR/publish.lock"
LOCK_MAX_AGE_SECONDS=300

acquire_publish_lock() {
  mkdir -p "$LOCK_DIR"
  if [[ -f "$PUBLISH_LOCK" ]]; then
    local lock_age
    lock_age="$(($(date +%s) - $(stat -f %m "$PUBLISH_LOCK" 2>/dev/null || date +%s)))"
    if [[ "$lock_age" -lt "$LOCK_MAX_AGE_SECONDS" ]]; then
      echo "Refusing to publish: lock file exists (age=${lock_age}s)." >&2
      echo "Another publish may be in progress. Remove $PUBLISH_LOCK if this is stale." >&2
      exit 1
    fi
    echo "Stale lock file (age=${lock_age}s) — overwriting." >&2
  fi
  printf "pid=%s\nstarted=%s\noperation=publish\n" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$PUBLISH_LOCK"
}

release_publish_lock() {
  rm -f "$PUBLISH_LOCK"
}

trap release_publish_lock EXIT

DIRTY_STATUS="$(git -C "$REPO_ROOT" status --short --untracked-files=normal)"
if [[ -n "$DIRTY_STATUS" ]]; then
  echo "Refusing to publish from a dirty worktree. Commit or stash changes first." >&2
  echo "$DIRTY_STATUS" >&2
  exit 1
fi

# Pause scheduled refresh during publish to avoid concurrent DB writes
SCHEDULED_LABEL="com.codex.ashare-dashboard.scheduled-refresh"
echo "[publish] Pausing scheduled-refresh"
launchctl stop "$SCHEDULED_LABEL" 2>/dev/null || true

COMMIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"

BACKUP_ROOT="$HOME/codex/runtime/projects/ashare-dashboard.backups"
BACKUP_DIR="$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT_SHA:0:7}"
MAX_BACKUPS=5

mkdir -p "$RUNTIME_ROOT"

echo "[publish] Release source commit: $COMMIT_SHA"

# Snapshot current runtime before overwriting (AI rollback path)
echo "[publish] Backing up runtime to $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
if [ -d "$RUNTIME_ROOT/frontend/dist" ] || [ -d "$RUNTIME_ROOT/src" ]; then
  rsync -a --exclude ".git" --exclude "data" "$RUNTIME_ROOT/" "$BACKUP_DIR/"
  echo "[publish] Backup saved: $BACKUP_DIR"
  echo "[publish] Rollback: rsync -a --delete $BACKUP_DIR/ $RUNTIME_ROOT/"
else
  echo "[publish] Runtime empty — skipping backup (first publish?)"
fi

# Rotate old backups
backup_count=$(ls -d "$BACKUP_ROOT"/*/ 2>/dev/null | wc -l | tr -d ' ')
if [ "$backup_count" -gt "$MAX_BACKUPS" ]; then
  ls -dt "$BACKUP_ROOT"/*/ | tail -n +$((MAX_BACKUPS + 1)) | xargs rm -rf
  echo "[publish] Rotated backups, keeping last $MAX_BACKUPS"
fi
echo "[publish] Building repo frontend"
npm --prefix "$REPO_ROOT/frontend" run build

echo "[publish] Syncing repo to runtime"
"$RSYNC_BIN" -a --delete \
  --exclude "data" \
  --exclude ".venv" \
  --exclude ".venv-mac" \
  --exclude "venv" \
  --exclude "node_modules" \
  --exclude "frontend/node_modules" \
  "$REPO_ROOT/" "$RUNTIME_ROOT/"

echo "[publish] Restarting LaunchAgents"
launchctl kickstart -k "gui/$(id -u)/com.codex.ashare-dashboard.backend"
launchctl kickstart -k "gui/$(id -u)/com.codex.ashare-dashboard.frontend"

wait_for_health() {
  local url="$1"
  local deadline=$((SECONDS + MAX_WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

echo "[publish] Waiting for backend health"
wait_for_health "$BACKEND_URL"

echo "[publish] Waiting for frontend health"
wait_for_health "$FRONTEND_URL"

repo_index_html="$REPO_ROOT/frontend/dist/index.html"
runtime_index_html="$RUNTIME_ROOT/frontend/dist/index.html"

if [[ ! -f "$repo_index_html" ]]; then
  echo "Repo build output missing: $repo_index_html" >&2
  exit 1
fi

if [[ ! -f "$runtime_index_html" ]]; then
  echo "Runtime build output missing: $runtime_index_html" >&2
  exit 1
fi

repo_assets="$(grep -Eo 'assets/index-[^\" ]+\.(js|css)' "$repo_index_html" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
served_assets="$(curl -fsS "$FRONTEND_URL" | grep -Eo 'assets/index-[^\" ]+\.(js|css)' | tr '\n' ' ' | sed 's/[[:space:]]*$//')"

if [[ -z "$repo_assets" ]]; then
  echo "Unable to read repo asset names from $repo_index_html" >&2
  exit 1
fi

if [[ "$repo_assets" != "$served_assets" ]]; then
  echo "Served frontend assets do not match repo build." >&2
  echo "repo:   $repo_assets" >&2
  echo "served: $served_assets" >&2
  exit 1
fi

echo "[publish] Verifying repo/runtime/canonical parity"
MANIFEST_PATH="$(
  cd "$REPO_ROOT"
  PYTHONPATH=src python3 -m ashare_evidence.release_verifier \
    --repo-root "$REPO_ROOT" \
    --runtime-root "$RUNTIME_ROOT" \
    --local-frontend-url "$FRONTEND_URL" \
    --local-api-base-url "$LOCAL_API_BASE_URL" \
    --canonical-base-url "$CANONICAL_BASE_URL" \
    --expected-commit-sha "$COMMIT_SHA"
)"

mkdir -p "$RUNTIME_ROOT/output/releases"
cp "$MANIFEST_PATH" "$RUNTIME_ROOT/output/releases/latest-successful.json"
printf '%s\n' "$COMMIT_SHA" > "$RUNTIME_ROOT/output/releases/latest-successful.commit"

echo "[publish] Resuming scheduled-refresh"
launchctl start "$SCHEDULED_LABEL" 2>/dev/null || true

echo "[publish] Runtime frontend matches repo build"
echo "[publish] Backend healthy at $BACKEND_URL"
echo "[publish] Frontend healthy at $FRONTEND_URL"
echo "[publish] Release parity manifest: $MANIFEST_PATH"
