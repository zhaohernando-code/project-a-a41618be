#!/usr/bin/env bash
set -euo pipefail

# Clean up browser automation sessions left by Playwright CLI verification.
# This intentionally targets only Playwright daemon/profile processes and does
# not terminate the user's normal Google Chrome process.

export PATH="${CODEX_NODE_BIN:-$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin}:$PATH"
PWCLI="${PWCLI:-$HOME/.codex/skills/playwright/scripts/playwright_cli.sh}"

if [[ -x "$PWCLI" ]]; then
  "$PWCLI" close-all >/dev/null 2>&1 || true
fi

pkill -TERM -f 'playwright-core/lib/entry/cliDaemon.js' >/dev/null 2>&1 || true
pkill -TERM -f 'playwright_chromiumdev_profile' >/dev/null 2>&1 || true

sleep 1

if pgrep -f 'playwright-core/lib/entry/cliDaemon.js|playwright_chromiumdev_profile' >/dev/null 2>&1; then
  pkill -KILL -f 'playwright-core/lib/entry/cliDaemon.js' >/dev/null 2>&1 || true
  pkill -KILL -f 'playwright_chromiumdev_profile' >/dev/null 2>&1 || true
fi

remaining="$(pgrep -fl 'playwright-core/lib/entry/cliDaemon.js|playwright_chromiumdev_profile' || true)"
if [[ -n "$remaining" ]]; then
  echo "Browser automation cleanup incomplete:" >&2
  echo "$remaining" >&2
  exit 1
fi

echo "Browser automation cleanup complete."
