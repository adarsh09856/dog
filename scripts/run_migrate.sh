#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$(dirname "${BASH_SOURCE[0]}")")" && pwd)"
ENV_FILE="$BASE_DIR/api/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a && . "$ENV_FILE" && set +a
elif [[ -f "$BASE_DIR/.env" ]]; then
  set -a && . "$BASE_DIR/.env" && set +a
fi

cd "$BASE_DIR"
alembic -c "$BASE_DIR/api/alembic.ini" upgrade head
python -m scripts.seed_platform
