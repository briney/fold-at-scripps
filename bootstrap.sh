#!/usr/bin/env bash
# Bootstrap fold@Scripps: sync deps, then hand off to foldapp.
# Usage: ./bootstrap.sh   (run from the repo checkout)
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found on PATH. Install it: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv sync
echo
echo "Dependencies synced. Next:"
echo "  uv run foldapp doctor      # verify prerequisites"
echo "  uv run foldapp install     # first-time setup"
echo "  uv run foldapp admin create-admin --email you@scripps.edu --display-name 'You'"
