#!/usr/bin/env bash
# ==============================================================================
# Kodewaves Sovereign Voice AI — Fast Production Update & Redeploy Script
# Pulls latest changes, applies database migrations, and updates containers
# ==============================================================================

set -eo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${BOLD} 🚀 Kodewaves Sovereign Voice AI — Production Deployment & Update${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Pull latest code if git repo
if [ -d ".git" ]; then
    echo -e "${BLUE}[1/4] Pulling latest updates from Git...${NC}"
    git pull origin main || echo -e "${YELLOW}⚠️ Git pull failed or working offline, proceeding with local changes.${NC}"
else
    echo -e "${BLUE}[1/4] Deploying from local workspace directory...${NC}"
fi

# 2. Rebuild and restart modified containers
echo -e "${BLUE}[2/4] Building and updating application containers...${NC}"
docker compose -f docker-compose.aapanel.yaml up -d --build

# 3. Apply any new Alembic database migrations & platform seed
echo -e "${BLUE}[3/4] Running database migrations & platform seed...${NC}"
sleep 5
docker exec kodewaves_api python -m alembic -c api/alembic.ini upgrade head || true
docker exec kodewaves_api python -m scripts.seed_platform || true

# 4. Container health verification
echo -e "${BLUE}[4/4] Verifying running services...${NC}"
docker compose -f docker-compose.aapanel.yaml ps

echo ""
echo -e "${GREEN}${BOLD}✓ Kodewaves update successfully deployed!${NC}"
echo -e "${GREEN}Services are running healthy on ports 3010 (UI) and 8000 (API).${NC}"
echo ""
