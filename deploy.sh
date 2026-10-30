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

COMPOSE_ARGS=(-f "$COMPOSE_FILE")
OWNER_KEYS_CONFIGURED="${KODEWAVES_OWNER_KEYS_DIR:-}"
if [ -z "$OWNER_KEYS_CONFIGURED" ] && [ -f .env ]; then
    OWNER_KEYS_CONFIGURED="$(sed -n 's/^KODEWAVES_OWNER_KEYS_DIR=//p' .env | tail -n 1 | tr -d "\"'")"
fi
if [ -n "$OWNER_KEYS_CONFIGURED" ]; then
    COMPOSE_ARGS+=(-f deploy/owner/docker-compose.owner.yaml)
    echo "Owner license signer overlay enabled."
fi

read_boolean_setting() {
    local setting_name="$1"
    local setting_value="${!setting_name:-}"
    local config_file

    if [ -z "$setting_value" ]; then
        for config_file in .env api/.env; do
            if [ -f "$config_file" ]; then
                setting_value="$(grep -m 1 "^[[:space:]]*${setting_name}[[:space:]]*=" "$config_file" 2>/dev/null | cut -d '=' -f2- | sed 's/[[:space:]]*#.*$//' | xargs || true)"
                [ -n "$setting_value" ] && break
            fi
        done
    fi

    printf '%s' "$setting_value" | tr '[:upper:]' '[:lower:]'
}

# Read both supported env locations so the deploy profile matches the app config.
ENABLE_LOCAL="$(read_boolean_setting ENABLE_LOCAL_AI_ENGINE)"

# Indic-Mio needs substantially more headroom than the other CPU services.
# Keep it opt-in so it cannot OOM a small production VPS during synthesis.
ENABLE_INDIC_MIO="$(read_boolean_setting ENABLE_INDIC_MIO_TTS)"

INDIC_MIO_PROFILE_FLAGS=""
if [ "$ENABLE_INDIC_MIO" = "true" ]; then
    if [ "$ENABLE_LOCAL" != "true" ]; then
        echo -e "${RED}Indic-Mio requires ENABLE_LOCAL_AI_ENGINE=true.${NC}" >&2
        exit 1
    fi
    AVAILABLE_MEMORY_KB="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
    # The test VPS globally OOM-killed this process near 9.6 GiB RSS while
    # the API, Ollama, Whisper and the OS were resident. Require 20 GiB free
    # before allowing the opt-in service to start, preserving host headroom.
    MIN_INDIC_MIO_MEMORY_KB=20971520
    if [ -z "$AVAILABLE_MEMORY_KB" ] || [ "$AVAILABLE_MEMORY_KB" -lt "$MIN_INDIC_MIO_MEMORY_KB" ]; then
        echo -e "${RED}Indic-Mio was not started: it needs at least 20 GiB host MemAvailable for safe CPU inference; current MemAvailable is ${AVAILABLE_MEMORY_KB:-unknown} KiB.${NC}" >&2
        exit 1
    fi
    INDIC_MIO_PROFILE_FLAGS="--profile indic-mio"
    echo -e "${BLUE}Indic-Mio opt-in enabled; host memory headroom check passed.${NC}"
else
    echo -e "${YELLOW}Indic-Mio TTS is disabled; set ENABLE_INDIC_MIO_TTS=true only on a high-memory host.${NC}"
fi

PROFILE_FLAGS=""
if [ "$ENABLE_LOCAL" = "true" ]; then
    echo -e "${BLUE}Local AI Engine profile enabled; retaining existing engine services...${NC}"
    PROFILE_FLAGS="--profile local"
else
    echo -e "${YELLOW}Local AI Engine profile disabled; retaining existing engine services...${NC}"
fi

# Validate before any mutation. Compose scope must remain this application.
if [ "$COMPOSE_FILE" = "docker-compose.aapanel.yaml" ] && [ -f .env ]; then
    # The aaPanel host proxy reaches the API via its localhost-published port.
    # Docker NAT presents the Compose bridge gateway to Uvicorn. Replace the
    # historical wildcard with that exact peer before restarting the API.
    PROXY_PEER="$(docker inspect kodewaves_postgres --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' 2>/dev/null || true)"
    if [ -z "$PROXY_PEER" ]; then
        echo -e "${RED}Could not determine the Docker bridge gateway; refusing to deploy with uncertain proxy-header trust.${NC}" >&2
        exit 1
    fi
    if grep -q '^FORWARDED_ALLOW_IPS=' .env; then
        sed -i "s|^FORWARDED_ALLOW_IPS=.*|FORWARDED_ALLOW_IPS=$PROXY_PEER|" .env
    else
        echo "FORWARDED_ALLOW_IPS=$PROXY_PEER" >> .env
    fi
    echo -e "${GREEN}Restricted forwarded-header trust to the local Docker gateway ($PROXY_PEER).${NC}"
fi
docker compose "${COMPOSE_ARGS[@]}" $PROFILE_FLAGS config -q

# Back up before restarting the API: its entrypoint itself runs migrations.
BACKUP_DIR="$APP_DIR/run/deploy-backups"
umask 077
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/database_$(date +%Y%m%d_%H%M%S).sql"
docker compose "${COMPOSE_ARGS[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP_FILE"
test -s "$BACKUP_FILE"
printf '%s\n' "$PREVIOUS_REVISION" > "$BACKUP_FILE.previous-revision"
git rev-parse HEAD > "$BACKUP_FILE.target-revision"
umask 022

# 2. Build only application images; leave existing infrastructure in place.
echo -e "${BLUE}[2/6] Building and updating application containers...${NC}"
docker compose "${COMPOSE_ARGS[@]}" $PROFILE_FLAGS build api ui
if [ "$ENABLE_LOCAL" = "true" ]; then
    if [ "$ENABLE_INDIC_MIO" = "true" ]; then
        docker compose "${COMPOSE_ARGS[@]}" $PROFILE_FLAGS $INDIC_MIO_PROFILE_FLAGS build indic-mio-tts
    fi
fi
echo "Checking the candidate migration history against the running database..."
docker compose "${COMPOSE_ARGS[@]}" $PROFILE_FLAGS run --rm --no-deps --entrypoint python api -m api.services.release_schema --preflight-deploy
docker compose "${COMPOSE_ARGS[@]}" $PROFILE_FLAGS up -d --no-deps api ui

# The API entrypoint runs migrations before starting its services. Wait for
# readiness rather than swallowing failures or running concurrent migrations.
echo "Waiting for application readiness..."
for attempt in $(seq 1 60); do
    if docker compose "${COMPOSE_ARGS[@]}" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)" >/dev/null 2>&1 &&
       docker compose "${COMPOSE_ARGS[@]}" exec -T ui node -e "fetch('http://127.0.0.1:3010/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" = 60 ]; then
        echo "Deployment failed readiness checks. Backup: $BACKUP_FILE" >&2
        exit 1
    fi
    sleep 5
done

# Keep the selected local LLM resident after Docker or VPS restarts. The small
# monitor checks Ollama's installed-model inventory and never downloads weights.
if [ "$ENABLE_LOCAL" = "true" ]; then
    docker compose "${COMPOSE_ARGS[@]}" $PROFILE_FLAGS up -d --no-deps ollama-warmup
    if [ "$ENABLE_INDIC_MIO" = "true" ]; then
        docker compose "${COMPOSE_ARGS[@]}" $PROFILE_FLAGS $INDIC_MIO_PROFILE_FLAGS up -d --no-deps indic-mio-tts
    fi
fi

# No host-wide pruning, environment rewriting or unrelated service cleanup.
if command -v python3 >/dev/null 2>&1; then
    python3 scripts/prune_ui_build_cache.py --apply --max-gb "${KODEWAVES_UI_BUILD_CACHE_GB:-8}" ||
        echo "Warning: application build-cache cleanup failed; deployment remains healthy." >&2
fi

# 6. Service health verification
echo -e "${BLUE}[6/6] Verifying running services and API health...${NC}"
docker compose "${COMPOSE_ARGS[@]}" ps

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
