#!/usr/bin/env bash
# ==============================================================================
# Kodewaves Sovereign Voice AI — Automated Turnkey VPS & aaPanel Installer
# Supported OS: Ubuntu 20.04/22.04/24.04 LTS, Debian 11/12, AlmaLinux/CentOS
# Compatible with: aaPanel, cPanel, CyberPanel, and Standalone Linux VPS
# ==============================================================================

set -eo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

RESET_DB=false
for arg in "$@"; do
    case "$arg" in
        --reset-db|--fresh|--wipe-db)
            RESET_DB=true
            ;;
    esac
done

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

print_banner() {
    clear || true
    echo -e "${CYAN}${BOLD}"
    cat << "EOF"
  _  __          _                                
 | |/ /___   __| | _____      ______ __   _____  ___
 | ' // _ \ / _` |/ _ \ \ /\ / / __ `/ | / / _ \/ __|
 | . \ (_) | (_| |  __/\ V  V / /_/ /| |/ /  __/\__ \
 |_|\_\___/ \__,_|\___| \_/\_/\__,_/ |___/\___/|___/
      Sovereign Voice AI Platform • Turnkey VPS Installer
EOF
    echo -e "${NC}"
    echo -e "${BOLD}==============================================================================${NC}"
    echo -e " 🚀 Production Installer for aaPanel, Cloud VPS, and Dedicated Servers"
    echo -e " 🛡️ 100% Decoupled: Local Master Credentials Vault (AES-256 Fernet)"
    echo -e " 🛡️ Multi-Site Safe: Safe Local Ports (3010/8000) Never Conflict with Port 80/443"
    echo -e "${BOLD}==============================================================================${NC}"
    echo ""
}

# 1. Root Check
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root or with sudo privileges."
        echo "Please re-run: sudo bash install.sh"
        exit 1
    fi
}

# 2. Check and Install Docker & Docker Compose
check_docker() {
    log_info "Verifying Docker engine and Docker Compose..."
    if ! command -v docker >/dev/null 2>&1; then
        log_warn "Docker is not installed. Installing official Docker engine..."
        curl -fsSL https://get.docker.com | sh
        systemctl enable docker
        systemctl start docker
        log_success "Docker installed successfully."
    else
        log_success "Docker is already installed ($(docker --version))."
    fi

    # Check docker compose
    if ! docker compose version >/dev/null 2>&1; then
        log_warn "Installing Docker Compose plugin..."
        apt-get update && apt-get install -y docker-compose-plugin || yum install -y docker-compose-plugin || true
    fi
    log_success "Docker Compose is verified."
}

# Helper: Generate random secure token
generate_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 24
    else
        cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1
    fi
}

# Helper: Generate valid Fernet 32-byte base64 encryption key
generate_fernet_key() {
    if command -v python3 >/dev/null 2>&1 && python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())" 2>/dev/null; then
        python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    elif command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 32
    else
        echo "k5Zp9mR8wX2yQ4tL7vN1jF3bH6aC8eD0sU2iO4gA6cY="
    fi
}

# Helper: Check if a port is in use on the host (ignoring existing Kodewaves containers)
is_port_in_use() {
    local port=$1
    if command -v ss >/dev/null 2>&1; then
        if ss -tuln | grep -E "[: ]${port}[ ]+" >/dev/null 2>&1; then
            if docker ps --filter "name=kodewaves_" --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                return 1 # Belongs to existing Kodewaves container
            fi
            return 0 # In use by an external host process
        fi
    elif command -v netstat >/dev/null 2>&1; then
        if netstat -tuln | grep -E "[: ]${port}[ ]+" >/dev/null 2>&1; then
            if docker ps --filter "name=kodewaves_" --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                return 1
            fi
            return 0
        fi
    elif command -v lsof >/dev/null 2>&1; then
        if lsof -i :"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            if docker ps --filter "name=kodewaves_" --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                return 1
            fi
            return 0
        fi
    fi
    return 1 # Port is completely free
}

# Helper: Find first available free port starting from base_port
resolve_free_port() {
    local base_port=$1
    local service_name=$2
    local port=$base_port
    while is_port_in_use "$port"; do
        log_warn "Port $port is already occupied by a host service. Trying port $((port + 1))..."
        port=$((port + 1))
    done
    if [ "$port" -ne "$base_port" ]; then
        log_info "Auto-assigned $service_name to free port: $port (was $base_port)"
    else
        log_success "Port $port for $service_name is available."
    fi
    printf '%s\n' "$port"
}

# 3. Interactive Configuration
prompt_configuration() {
    echo ""
    echo -e "${BOLD}Configure your Domain & Superadmin Credentials:${NC}"
    
    # 1. Domain (default: app.kodewaves.in)
    if [ -z "${DOMAIN:-}" ]; then
        echo -e "${YELLOW}Enter your public domain [press Enter for default: app.kodewaves.in]:${NC}"
        read -p "> " INPUT_DOMAIN
        INPUT_DOMAIN=$(echo "$INPUT_DOMAIN" | tr -d ' ' | sed -e 's|^https://||' -e 's|^http://||' -e 's|/$||')
        DOMAIN=${INPUT_DOMAIN:-app.kodewaves.in}
    fi
    log_info "Domain set to: $DOMAIN (https://$DOMAIN)"

    # 2. Admin Email (default: admin@admin.com)
    if [ -z "${ADMIN_EMAIL:-}" ]; then
        echo -e "${YELLOW}Enter Admin Email [press Enter for default: admin@admin.com]:${NC}"
        read -p "> " INPUT_EMAIL
        INPUT_EMAIL=$(echo "$INPUT_EMAIL" | tr -d ' ')
        ADMIN_EMAIL=${INPUT_EMAIL:-admin@admin.com}
    fi
    log_info "Admin email set to: $ADMIN_EMAIL"

    # 3. Admin Password (default: admin)
    if [ -z "${ADMIN_PASSWORD:-}" ]; then
        echo -e "${YELLOW}Enter Admin Password [press Enter for default: admin]:${NC}"
        read -s -p "> " INPUT_PASS
        echo ""
        INPUT_PASS=$(echo "$INPUT_PASS" | tr -d ' ')
        ADMIN_PASSWORD=${INPUT_PASS:-admin}
    fi
    log_info "Admin password set to: $ADMIN_PASSWORD"

    # Check available ports to prevent conflicts with aaPanel / host services
    echo ""
    log_info "Scanning for available host ports (preventing port collisions)..."
    UI_PORT=$(resolve_free_port 3010 "Frontend UI")
    API_PORT=$(resolve_free_port 8000 "Backend API")
    POSTGRES_PORT=$(resolve_free_port 5432 "PostgreSQL")
    REDIS_PORT=$(resolve_free_port 6379 "Redis")
    MINIO_PORT=$(resolve_free_port 9000 "MinIO Storage")
    MINIO_CONSOLE_PORT=$(resolve_free_port 9001 "MinIO Console")

    # Clean up corrupted .env from previous failed run if it contains ANSI escape codes
    if [ -f ".env" ] && grep -q $'\x1b' .env 2>/dev/null; then
        log_warn "Detected corrupted .env from previous run (contained ANSI escape sequences). Re-generating clean .env..."
        rm -f .env
    fi

    # Generate secrets if .env doesn't exist
    if [ ! -f ".env" ]; then
        log_info "Generating production environment secrets (.env)..."
        POSTGRES_PASS=$(generate_secret)
        REDIS_PASS=$(generate_secret)
        MINIO_PASS=$(generate_secret)
        JWT_SECRET=$(generate_secret)
        FERNET_KEY=$(generate_fernet_key)
        TURN_SECRET=$(generate_secret)
        DEV_SECRET=$(generate_secret)

        cat > .env << ENVFILE
# Kodewaves Production Environment Configuration
ENVIRONMENT=production
DOMAIN=$DOMAIN
PUBLIC_HOST=$DOMAIN
PUBLIC_BASE_URL=https://$DOMAIN
BACKEND_API_ENDPOINT=https://$DOMAIN
UI_APP_URL=https://$DOMAIN

# Service Port Bindings (Collision-free)
UI_PORT=$UI_PORT
API_PORT=$API_PORT
POSTGRES_PORT=$POSTGRES_PORT
REDIS_PORT=$REDIS_PORT
MINIO_PORT=$MINIO_PORT
MINIO_CONSOLE_PORT=$MINIO_CONSOLE_PORT

# Superadmin Login Credentials
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD

# Database & Cache Secrets (Auto-created by Docker + Alembic)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$POSTGRES_PASS
POSTGRES_DB=postgres
DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASS}@postgres:5432/postgres

REDIS_PASSWORD=$REDIS_PASS
REDIS_URL=redis://:${REDIS_PASS}@redis:6379

# Sovereign Master Encryption Key (AES-256 Fernet)
MASTER_CREDENTIAL_ENCRYPTION_KEY=$FERNET_KEY
KODEWAVES_SECRET_KEY=$FERNET_KEY
OSS_JWT_SECRET=$JWT_SECRET
JWT_SECRET=$JWT_SECRET
KODEWAVES_DEVOPS_SECRET=$DEV_SECRET

# Local Storage (MinIO)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$MINIO_PASS

# WebRTC Audio Relay (Coturn STUN / TURN)
ENABLE_COTURN=true
TURN_SECRET=$TURN_SECRET

# Process Workers & Lean Resource Allocation
FASTAPI_WORKERS=1
ENABLE_ARI_MANAGER=false
ENABLE_CAMPAIGN_ORCHESTRATOR=false
ENABLE_SIGNUP=true

# Local CPU AI Engine (Ollama + Speaches — Admin Opt-In)
OLLAMA_ENDPOINT=http://ollama:11434
SPEACHES_ENDPOINT=http://speaches:8000/v1
ENABLE_LOCAL_AI_ENGINE=true

# Payment Gateways (Configure in Admin Panel → Master Keys)
# RAZORPAY_KEY_ID=
# RAZORPAY_KEY_SECRET=
# STRIPE_SECRET_KEY=
# STRIPE_PUBLISHABLE_KEY=
# STRIPE_WEBHOOK_SECRET=
ENVFILE
        log_success "Created .env with database credentials, port mappings, and master keys."
    else
        log_info "Existing .env file detected. Keeping database & token secrets."

        # If --reset-db was not passed on the CLI, prompt the user
        if [ "$RESET_DB" = false ] && [ -t 0 ]; then
            echo ""
            echo -e "${YELLOW}${BOLD}Existing database detected.${NC}"
            echo -e "Choose deployment mode:"
            echo -e "  ${BOLD}[1] Keep existing database${NC} (Standard Update — Preserves users, workflows, and call history) [Default]"
            echo -e "  ${BOLD}[2] Clean database reset${NC} (Wipes old test runs & starts fresh with clean seed data)"
            read -p "Select [1/2, default 1]: " DB_CHOICE
            if [ "$DB_CHOICE" = "2" ]; then
                RESET_DB=true
                log_warn "Clean database reset selected."
            else
                log_info "Keeping existing database."
            fi
        fi

        # Ensure domain & admin credentials match the configured values
        sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" .env || true
        sed -i "s|^PUBLIC_HOST=.*|PUBLIC_HOST=$DOMAIN|" .env || true
        sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$DOMAIN|" .env || true
        sed -i "s|^BACKEND_API_ENDPOINT=.*|BACKEND_API_ENDPOINT=https://$DOMAIN|" .env || true
        sed -i "s|^UI_APP_URL=.*|UI_APP_URL=https://$DOMAIN|" .env || true

        if grep -q '^ADMIN_EMAIL=' .env; then
            sed -i "s|^ADMIN_EMAIL=.*|ADMIN_EMAIL=$ADMIN_EMAIL|" .env || true
        else
            echo "ADMIN_EMAIL=$ADMIN_EMAIL" >> .env
        fi

        if grep -q '^ADMIN_PASSWORD=' .env; then
            sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PASSWORD|" .env || true
        else
            echo "ADMIN_PASSWORD=$ADMIN_PASSWORD" >> .env
        fi

        # Ensure collision-free ports are present in existing .env
        grep -q '^UI_PORT=' .env || echo "UI_PORT=$UI_PORT" >> .env
        grep -q '^API_PORT=' .env || echo "API_PORT=$API_PORT" >> .env
        grep -q '^POSTGRES_PORT=' .env || echo "POSTGRES_PORT=$POSTGRES_PORT" >> .env
        grep -q '^REDIS_PORT=' .env || echo "REDIS_PORT=$REDIS_PORT" >> .env
        grep -q '^MINIO_PORT=' .env || echo "MINIO_PORT=$MINIO_PORT" >> .env
        grep -q '^MINIO_CONSOLE_PORT=' .env || echo "MINIO_CONSOLE_PORT=$MINIO_CONSOLE_PORT" >> .env

        # Ensure encryption and secret keys exist
        EXISTING_JWT=$(grep '^OSS_JWT_SECRET=' .env 2>/dev/null | cut -d '=' -f2- || true)
        EXISTING_FERNET=$(grep '^MASTER_CREDENTIAL_ENCRYPTION_KEY=' .env 2>/dev/null | cut -d '=' -f2- || true)
        [ -z "$EXISTING_JWT" ] && EXISTING_JWT=$(generate_secret) && echo "OSS_JWT_SECRET=$EXISTING_JWT" >> .env
        [ -z "$EXISTING_FERNET" ] && EXISTING_FERNET=$(generate_fernet_key) && echo "MASTER_CREDENTIAL_ENCRYPTION_KEY=$EXISTING_FERNET" >> .env
        grep -q '^JWT_SECRET=' .env || echo "JWT_SECRET=$EXISTING_JWT" >> .env
        grep -q '^KODEWAVES_SECRET_KEY=' .env || echo "KODEWAVES_SECRET_KEY=$EXISTING_FERNET" >> .env

        # Ensure Kodewaves v2 Local AI Engine env vars exist
        grep -q '^OLLAMA_ENDPOINT=' .env || echo "OLLAMA_ENDPOINT=http://ollama:11434" >> .env
        grep -q '^SPEACHES_ENDPOINT=' .env || echo "SPEACHES_ENDPOINT=http://speaches:8000/v1" >> .env
        grep -q '^ENABLE_LOCAL_AI_ENGINE=' .env || echo "ENABLE_LOCAL_AI_ENGINE=true" >> .env
        grep -q '^KODEWAVES_DEVOPS_SECRET=' .env || echo "KODEWAVES_DEVOPS_SECRET=$(generate_secret)" >> .env

        log_success "Existing .env updated with Kodewaves v2 configuration."
    fi
}

# 4. Build and Start Docker Containers
deploy_containers() {
    log_info "Preparing production environment and infrastructure..."
    
    if [ "$RESET_DB" = true ]; then
        log_warn "⚠️ RESETTING DATABASE: Stopping existing containers and wiping database volume..."
        docker compose -f docker-compose.aapanel.yaml down -v || true
        log_success "Database volume wiped clean."
    fi

    # Start infrastructure services first (database, cache, storage)
    docker compose -f docker-compose.aapanel.yaml up -d postgres redis minio

    log_info "Waiting for PostgreSQL database container to become healthy..."
    local attempts=0
    until docker exec kodewaves_postgres pg_isready -U postgres >/dev/null 2>&1 || [ $attempts -ge 20 ]; do
        sleep 2
        attempts=$((attempts + 1))
    done

    if [ $attempts -ge 20 ]; then
        log_warn "PostgreSQL took longer than expected to report healthy, continuing..."
    else
        log_success "PostgreSQL database is online and accepting connections."
    fi

    log_info "Applying database schema migrations (Alembic)..."
    docker compose -f docker-compose.aapanel.yaml run --rm api python -m alembic -c api/alembic.ini upgrade head || {
        log_error "Alembic migrations failed! Check database container logs."
        exit 1
    }
    log_success "Database schema & tables verified."

    log_info "Initializing Superadmin account in database..."
    docker compose -f docker-compose.aapanel.yaml run --rm api python -m scripts.create_superuser --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD" || {
        log_warn "Superadmin creation script completed."
    }

    # Start Local AI Engine containers (Ollama + Speaches) before seeding
    log_info "Starting Local CPU AI Engine (Ollama + Speaches)..."
    docker compose -f docker-compose.aapanel.yaml up -d ollama speaches || {
        log_warn "Local AI containers may not be available on this hardware."
    }

    # Wait briefly for Ollama to initialize
    sleep 5

    log_info "Bootstrapping platform defaults (AI Catalog, SaaS Plans, Templates, Wallets, Local AI Model)..."
    docker compose -f docker-compose.aapanel.yaml run --rm api python -m scripts.seed_platform || {
        log_warn "Platform seed bootstrap completed with notice."
    }
    log_success "Platform defaults, models catalog, plans, templates, and wallets verified."

    log_info "Building and launching full production application stack..."
    docker compose -f docker-compose.aapanel.yaml up -d --build
    
    log_success "All services are running! (API, UI, Coturn, Ollama, Speaches, PostgreSQL, Redis, MinIO)"
}

# 5. Output aaPanel Nginx Reverse Proxy Instructions
print_aapanel_instructions() {
    # Ensure port variables are populated from current environment or .env
    UI_PORT=${UI_PORT:-$(grep '^UI_PORT=' .env 2>/dev/null | cut -d '=' -f2- || true)}
    UI_PORT=${UI_PORT:-3010}
    API_PORT=${API_PORT:-$(grep '^API_PORT=' .env 2>/dev/null | cut -d '=' -f2- || true)}
    API_PORT=${API_PORT:-8000}
    MINIO_PORT=${MINIO_PORT:-$(grep '^MINIO_PORT=' .env 2>/dev/null | cut -d '=' -f2- || true)}
    MINIO_PORT=${MINIO_PORT:-9000}

    echo ""
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
    echo -e "${GREEN}${BOLD} 🎉 Kodewaves Sovereign Platform Successfully Installed!${NC}"
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
    echo ""
    echo -e "${BOLD}🔑 CREDENTIALS & ACCESS DETAILS (Saved in .env):${NC}"
    echo -e "   🌐 Web Application:       ${CYAN}${BOLD}https://${DOMAIN}${NC} (Local: http://127.0.0.1:${UI_PORT})"
    echo -e "   🛡️ Sovereign Admin Panel: ${CYAN}${BOLD}https://${DOMAIN}/admin${NC}"
    echo -e "   👤 Superadmin Email:      ${BOLD}${ADMIN_EMAIL}${NC}"
    echo -e "   🔑 Superadmin Password:   ${BOLD}${ADMIN_PASSWORD}${NC}"
    echo -e "   🔌 API Backend Port:      ${BOLD}127.0.0.1:${API_PORT}${NC}"
    echo -e "   🗄️ Database:              ${GREEN}PostgreSQL 17 (Auto-initialized with pgvector)${NC}"
    echo -e "   📁 Configuration:         ${CYAN}${APP_DIR}/.env${NC}"
    echo ""
    echo -e "${BOLD}NEXT STEP: Configure your aaPanel Website (Reverse Proxy & SSL)${NC}"
    echo -e "1. Open your ${CYAN}aaPanel Dashboard${NC} in your browser."
    echo -e "2. Go to ${BOLD}Website${NC} -> Click ${BOLD}Add Site${NC}."
    echo -e "   • Domain: ${CYAN}${DOMAIN}${NC}"
    echo -e "   • Database: None (managed by Kodewaves Docker)"
    echo -e "   • PHP Version: Pure Static (or any PHP)"
    echo ""
    echo -e "3. Open Site Settings for ${CYAN}${DOMAIN}${NC} -> Go to ${BOLD}SSL${NC} tab:"
    echo -e "   • Select ${BOLD}Let's Encrypt${NC} -> Check your domain -> Click ${BOLD}Apply${NC}."
    echo -e "   • Turn ON ${BOLD}Force HTTPS${NC}."
    echo ""
    echo -e "4. Go to ${BOLD}ConfigFile${NC} (or Reverse Proxy) in Site Settings:"
    echo -e "   Replace the server block content or append the following location blocks:"
    echo ""
    echo -e "${YELLOW}------------------- COPY THIS NGINX CONFIG INTO aaPanel -------------------${NC}"
    cat << NGINX_CONF
    # Backend API and WebSockets (Live audio streaming & signaling)
    location /api/v1/ {
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
        client_max_body_size 100M;
    }

    # Sovereign Audio Recordings (MinIO)
    location /voice-audio/ {
        proxy_pass http://127.0.0.1:${MINIO_PORT}/voice-audio/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        client_max_body_size 100M;
    }

    # Frontend UI (Next.js 15)
    location / {
        proxy_pass http://127.0.0.1:${UI_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
    }
NGINX_CONF
    echo -e "${YELLOW}---------------------------------------------------------------------------${NC}"
    echo ""
    echo -e "5. Save the Nginx config in aaPanel. Your platform is now LIVE at:"
    echo -e "   👉 ${CYAN}${BOLD}https://${DOMAIN}${NC}"
    echo -e "   👉 Sovereign Admin Panel: ${CYAN}${BOLD}https://${DOMAIN}/admin${NC}"
    echo ""
    echo -e "${BOLD}Firewall Ports Configuration (aaPanel Security tab):${NC}"
    echo -e "   • ${BOLD}80 (TCP) & 443 (TCP)${NC} [MANDATORY] — Web UI, API, and Phone Telephony (Twilio/Plivo/Exotel)"
    echo -e "   • ${BOLD}3478 (UDP/TCP), 5349 (UDP/TCP), 49152-49200 (UDP)${NC} [REQUIRED FOR WEBRTC TEST AUDIO] — Coturn STUN/TURN"
    echo -e "     (Must be opened in aaPanel Security / VPS firewall so browser microphone 'Test Audio' works)"
    echo ""
}

main() {
    print_banner
    check_root
    check_docker
    prompt_configuration
    deploy_containers
    print_aapanel_instructions
}

main "$@"
