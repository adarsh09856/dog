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
exec python -m api.services.campaign.campaign_orchestrator
