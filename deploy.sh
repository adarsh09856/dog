#!/usr/bin/env bash
# ==============================================================================
# Kodewaves Sovereign Voice AI — Fast Production Update & Redeploy Script
# Updates an existing application deployment without host-wide cleanup.
# ==============================================================================

set -euo pipefail
# Application source is bind-mounted into containers running as non-root users.
umask 022

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
PREVIOUS_REVISION="$(git rev-parse HEAD)"

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
    CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "stabilize")"
    echo -e "${BLUE}[1/6] Pulling latest updates from Git (${CURRENT_BRANCH})...${NC}"
    git pull --ff-only origin "${CURRENT_BRANCH}"
else
    echo -e "${BLUE}[1/6] Deploying from local workspace directory...${NC}"
fi

# Check ENABLE_LOCAL_AI_ENGINE configuration
ENABLE_LOCAL="${ENABLE_LOCAL_AI_ENGINE:-}"
if [ -z "$ENABLE_LOCAL" ] && [ -f ".env" ]; then
    ENABLE_LOCAL="$(grep '^ENABLE_LOCAL_AI_ENGINE=' .env 2>/dev/null | cut -d '=' -f2- | tr -d '\"' || true)"
fi

PROFILE_FLAGS=""
if [ "$ENABLE_LOCAL" = "true" ]; then
    echo -e "${BLUE}Local AI Engine profile enabled; retaining existing engine services...${NC}"
    PROFILE_FLAGS="--profile local"
else
    echo -e "${YELLOW}Local AI Engine profile disabled; retaining existing engine services...${NC}"
fi

# Validate before any mutation. Compose scope must remain this application.
docker compose -f "$COMPOSE_FILE" $PROFILE_FLAGS config -q

# Back up before restarting the API: its entrypoint itself runs migrations.
BACKUP_DIR="$APP_DIR/run/deploy-backups"
umask 077
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/database_$(date +%Y%m%d_%H%M%S).sql"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP_FILE"
test -s "$BACKUP_FILE"
printf '%s\n' "$PREVIOUS_REVISION" > "$BACKUP_FILE.previous-revision"
git rev-parse HEAD > "$BACKUP_FILE.target-revision"
umask 022

# 2. Build only application images; leave existing infrastructure in place.
echo -e "${BLUE}[2/6] Building and updating application containers...${NC}"
docker compose -f "$COMPOSE_FILE" $PROFILE_FLAGS build api ui
docker compose -f "$COMPOSE_FILE" $PROFILE_FLAGS up -d --no-deps api ui

# The API entrypoint runs migrations before starting its services. Wait for
# readiness rather than swallowing failures or running concurrent migrations.
echo "Waiting for application readiness..."
for attempt in $(seq 1 60); do
    if docker compose -f "$COMPOSE_FILE" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)" >/dev/null 2>&1 &&
       docker compose -f "$COMPOSE_FILE" exec -T ui node -e "fetch('http://127.0.0.1:3010/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" = 60 ]; then
        echo "Deployment failed readiness checks. Backup: $BACKUP_FILE" >&2
        exit 1
    fi
    sleep 5
done
# No host-wide pruning, environment rewriting or unrelated service cleanup.

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
echo "Database backup: $BACKUP_FILE"
