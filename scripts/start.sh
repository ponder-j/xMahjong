#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
uv sync --locked
exec uv run uvicorn xmahjong.app:app --app-dir backend --host 127.0.0.1 --port "${PORT:-8765}"
