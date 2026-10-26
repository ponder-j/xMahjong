#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
uv sync --locked
uv run python scripts/download-mortal.py
docker build -f tools/mortal.Dockerfile -t xmahjong/mortal:local .
uv run python scripts/setup-mortal.py
