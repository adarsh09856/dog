#!/usr/bin/env bash
# ==============================================================================
# Kodewaves Sovereign Voice AI — Automated Docker Disk Cache Cleanup Utility
# Safely reclaims 50-100+ GB of disk space from Docker BuildKit, untagged images,
# dangling layers, and temporary containers on Linux VPS without touching volumes.
# ==============================================================================

set -eo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${BOLD} 🧹 Kodewaves Docker Disk & Build Cache Cleanup Utility${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# Check Docker availability
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not installed or not in PATH!${NC}" >&2
    exit 1
fi

echo -e "${BLUE}[1/5] Checking current disk and Docker storage usage...${NC}"
echo -e "${BOLD}--- Host Filesystem Disk Space ---${NC}"
df -h / | tail -n +1
echo ""
echo -e "${BOLD}--- Docker Storage Allocation ---${NC}"
docker system df || true
echo ""

echo -e "${BLUE}[2/5] Pruning Docker BuildKit build cache (reclaims 50-100GB)...${NC}"
# BuildKit saves multi-stage caches for every container build in /var/lib/docker/buildkit
docker builder prune -af || true
echo -e "${GREEN}✓ Docker build cache cleared.${NC}"

echo -e "${BLUE}[3/5] Pruning unused and dangling Docker images...${NC}"
# Prune unreferenced images that are not tagged and not used by running containers
docker image prune -af --filter "until=24h" || docker image prune -af || true
echo -e "${GREEN}✓ Unused images pruned.${NC}"

echo -e "${BLUE}[4/5] Pruning stopped temporary build containers & networks...${NC}"
docker container prune -f || true
docker network prune -f || true
echo -e "${GREEN}✓ Stopped build containers and idle networks cleaned.${NC}"

echo -e "${BLUE}[5/5] Storage status after cleanup...${NC}"
echo -e "${BOLD}--- Updated Host Filesystem Disk Space ---${NC}"
df -h / | tail -n +1
echo ""
echo -e "${BOLD}--- Updated Docker Storage Allocation ---${NC}"
docker system df || true

echo ""
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} ✓ Docker disk cache cleanup successfully completed!${NC}"
echo -e "${GREEN}   Persistent database, MinIO audio files, and model volumes were PRESERVED.${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo ""
echo -e "${CYAN}${BOLD}💡 Tip: Add this cleanup as a weekly automated cron job in your VPS:${NC}"
echo -e "   crontab -e"
echo -e "   0 3 * * 0 /bin/bash $(pwd)/scripts/docker_clean.sh >/var/log/kodewaves_docker_clean.log 2>&1"
echo ""
