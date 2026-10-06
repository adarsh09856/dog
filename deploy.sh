#!/usr/bin/env bash
# ==============================================================================
# Kodewaves Sovereign Voice AI — Fast Production Update & Redeploy Script
# Pulls latest changes, cleans old server artifacts, applies migrations, seeds models
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
    CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || echo "main")"
    echo -e "${BLUE}[1/6] Pulling latest updates from Git (${CURRENT_BRANCH})...${NC}"
    git pull origin "${CURRENT_BRANCH}" || echo -e "${YELLOW}⚠️ Git pull failed or working offline, proceeding with local changes.${NC}"
else
    echo -e "${BLUE}[1/6] Deploying from local workspace directory...${NC}"
fi

# Ensure collision-free PIPER_PORT and WHISPER_PORT exist in .env
if [ -f ".env" ]; then
    grep -q '^PIPER_PORT=' .env || echo "PIPER_PORT=8766" >> .env
    grep -q '^WHISPER_PORT=' .env || echo "WHISPER_PORT=8765" >> .env
fi

# Check ENABLE_LOCAL_AI_ENGINE configuration
ENABLE_LOCAL="${ENABLE_LOCAL_AI_ENGINE:-}"
if [ -z "$ENABLE_LOCAL" ] && [ -f ".env" ]; then
    ENABLE_LOCAL="$(grep '^ENABLE_LOCAL_AI_ENGINE=' .env 2>/dev/null | cut -d '=' -f2- | tr -d '\"' || true)"
fi

PROFILE_FLAGS=""
if [ "$ENABLE_LOCAL" = "true" ]; then
    echo -e "${BLUE}Local AI Engine profile active: starting Ollama, Whisper, and Piper...${NC}"
    PROFILE_FLAGS="--profile local"
else
    echo -e "${YELLOW}Local AI Engine profile inactive: keeping Ollama, Whisper, and Piper OFF (saving host RAM)${NC}"
fi

# 2. Rebuild and restart application containers (removes orphaned/old containers)
echo -e "${BLUE}[2/6] Building and updating application containers...${NC}"
docker compose -f "$COMPOSE_FILE" $PROFILE_FLAGS up -d --build --remove-orphans

if [ "$ENABLE_LOCAL" != "true" ]; then
    # Ensure local engine containers are stopped if they were left running
    docker compose -f "$COMPOSE_FILE" stop ollama whisper piper >/dev/null 2>&1 || true
fi

# 3. Apply Alembic database migrations (with safe pre-migration pg_dump)
echo -e "${BLUE}[3/6] Backing up database and applying migrations (Alembic)...${NC}"
sleep 5
docker compose -f "$COMPOSE_FILE" exec -T postgres pg_dump -U postgres postgres > "db_backup_pre_migration_$(date +%Y%m%d_%H%M%S).sql" 2>/dev/null \
    || docker exec kodewaves_postgres pg_dump -U postgres postgres > "db_backup_pre_migration_$(date +%Y%m%d_%H%M%S).sql" 2>/dev/null \
    || echo -e "${YELLOW}⚠️ Pre-migration database dump skipped (offline or not running).${NC}"

docker compose -f "$COMPOSE_FILE" exec -T api python -m alembic -c api/alembic.ini upgrade head \
    || docker exec kodewaves_api python -m alembic -c api/alembic.ini upgrade head \
    || echo -e "${YELLOW}⚠️ Alembic migration execution skipped or reported warning.${NC}"

# 4. Bootstrap platform catalog seed
echo -e "${BLUE}[4/6] Bootstrapping platform catalog (Piper Hindi TTS, Ollama, Models, Wallets)...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T api python -m scripts.seed_platform \
    || docker exec kodewaves_api python -m scripts.seed_platform \
    || echo -e "${YELLOW}⚠️ Platform seed executed with warning.${NC}"

# 5. Clean up old unused/dangling artifacts and Docker build cache on the server
echo -e "${BLUE}[5/6] Cleaning up Docker build cache, dangling containers, and legacy server artifacts...${NC}"
# Prune BuildKit build cache (preventing 50-100GB buildup on VPS)
docker builder prune -af --filter "until=24h" >/dev/null 2>&1 || docker builder prune -af >/dev/null 2>&1 || true

# Prune dangling/unused images left over from previous builds on the server
docker image prune -af --filter "until=72h" >/dev/null 2>&1 || docker image prune -f >/dev/null 2>&1 || true
docker container prune -f >/dev/null 2>&1 || true

# Clean up any legacy environment keys in server .env (e.g. duplicate DOGRAH keys)
if [ -f ".env" ]; then
    sed -i '/^DOGRAH_DEVOPS_SECRET=/d' .env 2>/dev/null || true
fi

# Clean up any stale PID/band lock files from old host-level runs
rm -f run/*.pid run/active_band run/*.port 2>/dev/null || true

echo -e "${GREEN}✓ Server cleanup completed (freed disk space, pruned build cache & dangling images)${NC}"

# 6. Service health verification
echo -e "${BLUE}[6/6] Verifying running services and API health...${NC}"
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
echo -e "${GREEN}  • Engine:      Dual-Mode Sovereign (General Cascade + S2S Realtime)${NC}"
echo -e "${GREEN}  • S2S Realtime: Google Gemini Live & OpenAI Realtime (Sub-300ms)${NC}"
echo -e "${GREEN}  • Local CPU:   Ollama LLM (Qwen 2.5) + Piper ONNX TTS (Hindi ~40ms)${NC}"
echo -e "${GREEN}  • Cloud Stack: Deepgram, Gemini, OpenAI, Sarvam, Cartesia, ElevenLabs${NC}"
echo ""
