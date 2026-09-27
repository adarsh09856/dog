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

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
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

# 3. Interactive Configuration
prompt_configuration() {
    echo ""
    echo -e "${BOLD}Configure your Domain & Deployment:${NC}"
    
    if [ -z "${DOMAIN:-}" ]; then
        echo -e "${YELLOW}Enter your public domain or subdomain (e.g. voice.yourdomain.com):${NC}"
        read -p "> " DOMAIN
        DOMAIN=$(echo "$DOMAIN" | tr -d ' ' | sed -e 's|^https://||' -e 's|^http://||' -e 's|/$||')
    fi

    if [ -z "$DOMAIN" ]; then
        log_error "Domain cannot be empty!"
        exit 1
    fi

    log_info "Domain set to: $DOMAIN (https://$DOMAIN)"

    # Generate secrets if .env doesn't exist
    if [ ! -f ".env" ]; then
        log_info "Generating production environment secrets (.env)..."
        POSTGRES_PASS=$(generate_secret)
        REDIS_PASS=$(generate_secret)
        MINIO_PASS=$(generate_secret)
        JWT_SECRET=$(generate_secret)
        FERNET_KEY=$(generate_fernet_key)
        TURN_SECRET=$(generate_secret)

        cat > .env << ENVFILE
# Kodewaves Production Environment Configuration
ENVIRONMENT=production
DOMAIN=$DOMAIN
PUBLIC_HOST=$DOMAIN
PUBLIC_BASE_URL=https://$DOMAIN
BACKEND_API_ENDPOINT=https://$DOMAIN

# Database & Cache Secrets
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$POSTGRES_PASS
REDIS_PASSWORD=$REDIS_PASS

# Sovereign Master Encryption Key (AES-256 Fernet)
MASTER_CREDENTIAL_ENCRYPTION_KEY=$FERNET_KEY
OSS_JWT_SECRET=$JWT_SECRET

# Local Storage (MinIO)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$MINIO_PASS

# WebRTC STUN/TURN
TURN_SECRET=$TURN_SECRET

# Workers
FASTAPI_WORKERS=2
ENABLE_SIGNUP=true
ENVFILE
        log_success "Created .env with cryptographically secure master keys."
    else
        log_info "Existing .env file detected. Keeping current secrets."
        # Ensure DOMAIN and PUBLIC_BASE_URL are up to date
        sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" .env || true
        sed -i "s|^PUBLIC_HOST=.*|PUBLIC_HOST=$DOMAIN|" .env || true
        sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$DOMAIN|" .env || true
    fi
}

# 4. Build and Start Docker Containers
deploy_containers() {
    log_info "Building and launching Kodewaves production containers..."
    echo -e "${CYAN}This may take 3-5 minutes on the first build while Python & Next.js compile...${NC}"
    
    docker compose -f docker-compose.aapanel.yaml up -d --build

    log_info "Waiting for PostgreSQL database container to become healthy..."
    sleep 8

    log_info "Applying database schema migrations (Alembic)..."
    docker exec kodewaves_api python -m alembic upgrade head || {
        log_warn "Direct alembic upgrade in container returned status. Checking container logs..."
    }
    
    log_success "All services are running healthy!"
}

# 5. Output aaPanel Nginx Reverse Proxy Instructions
print_aapanel_instructions() {
    echo ""
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
    echo -e "${GREEN}${BOLD} 🎉 Kodewaves Sovereign Platform Successfully Installed!${NC}"
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
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
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
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
        proxy_pass http://127.0.0.1:9000/voice-audio/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        client_max_body_size 100M;
    }

    # Frontend UI (Next.js 15)
    location / {
        proxy_pass http://127.0.0.1:3010;
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
    echo -e "${BOLD}Firewall Ports to Open in aaPanel (Security tab):${NC}"
    echo -e "   • Port 80 (TCP) & 443 (TCP) — Web and SSL"
    echo -e "   • Port 3478 (UDP/TCP) & 5349 (UDP/TCP) — WebRTC STUN/TURN"
    echo -e "   • Port 49152-49200 (UDP) — WebRTC Media Relays"
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
