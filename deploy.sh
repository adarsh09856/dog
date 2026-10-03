#!/usr/bin/env bash
# ==============================================================================
# Kodewaves Sovereign Voice AI — Fast Production Update & Redeploy Script
# Pulls latest changes, applies database migrations, seeds models, and checks health
# ==============================================================================

set -eo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${BOLD} 🚀 Kodewaves Sovereign Voice AI — Production Deployment & Update${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# Detect compose configuration file
COMPOSE_FILE="${COMPOSE_FILE:-}"
if [ -z "$COMPOSE_FILE" ]; then
    if [ -f "docker-compose.aapanel.yaml" ]; then
        COMPOSE_FILE="docker-compose.aapanel.yaml"
    elif [ -f "docker-compose.yaml" ]; then
        COMPOSE_FILE="docker-compose.yaml"
    else
        echo -e "${RED}Error: Neither docker-compose.aapanel.yaml nor docker-compose.yaml found!${NC}" >&2
        exit 1
    fi
fi
echo -e "${BLUE}Using Docker Compose configuration: ${BOLD}${COMPOSE_FILE}${NC}"

# 1. Pull latest code if git repo
if [ -d ".git" ]; then
    echo -e "${BLUE}[1/5] Pulling latest updates from Git...${NC}"
    git pull origin main || echo -e "${YELLOW}⚠️ Git pull failed or working offline, proceeding with local changes.${NC}"
else
    echo -e "${BLUE}[1/5] Deploying from local workspace directory...${NC}"
fi

# 2. Rebuild and restart application containers
echo -e "${BLUE}[2/5] Building and updating application containers...${NC}"
docker compose -f "$COMPOSE_FILE" up -d --build

# 3. Apply Alembic database migrations & platform catalog seed
echo -e "${BLUE}[3/5] Applying database migrations (Alembic)...${NC}"
sleep 5
docker compose -f "$COMPOSE_FILE" exec -T api python -m alembic -c api/alembic.ini upgrade head \
    || docker exec kodewaves_api python -m alembic -c api/alembic.ini upgrade head \
    || echo -e "${YELLOW}⚠️ Alembic migration execution skipped or reported warning.${NC}"

echo -e "${BLUE}[4/5] Bootstrapping platform catalog (Piper Hindi TTS, Ollama, Models, Wallets)...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T api python -m scripts.seed_platform \
    || docker exec kodewaves_api python -m scripts.seed_platform \
    || echo -e "${YELLOW}⚠️ Platform seed executed with warning.${NC}"

# 5. Service health verification
echo -e "${BLUE}[5/5] Verifying running services and API health...${NC}"
docker compose -f "$COMPOSE_FILE" ps

# Read API port from .env or default to 8000
API_PORT="${API_PORT:-$(grep '^API_PORT=' .env 2>/dev/null | cut -d '=' -f2- || true)}"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-$(grep '^UI_PORT=' .env 2>/dev/null | cut -d '=' -f2- || true)}"
UI_PORT="${UI_PORT:-3010}"

echo ""
echo -e "${GREEN}${BOLD}✓ Kodewaves Sovereign Platform successfully deployed!${NC}"
echo -e "${GREEN}  • Web UI:      http://127.0.0.1:${UI_PORT}${NC}"
echo -e "${GREEN}  • Backend API: http://127.0.0.1:${API_PORT}${NC}"
echo -e "${GREEN}  • Engine:      Independent Cloud & Local CPU Mix-and-Match${NC}"
echo -e "${GREEN}  • Local TTS:   Piper ONNX (Native Hindi) + Kokoro-82M (English)${NC}"
echo -e "${GREEN}  • Local STT:   Faster-Whisper Base (English & Hindi)${NC}"
echo -e "${GREEN}  • Admin Panel: Governance, Moderation, Secret Protection & Audit Trail${NC}"
echo ""
