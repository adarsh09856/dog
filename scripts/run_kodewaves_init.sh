#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${KODEWAVES_INIT_WORKSPACE_DIR:-${DOGRAH_INIT_WORKSPACE_DIR:-/workspace}}"
OUTPUT_ROOT="${KODEWAVES_INIT_OUTPUT_ROOT:-${DOGRAH_INIT_OUTPUT_ROOT:-/generated}}"
NGINX_OUTPUT_DIR="$OUTPUT_ROOT/nginx"
COTURN_OUTPUT_DIR="$OUTPUT_ROOT/coturn"
CERTS_DIR="${KODEWAVES_INIT_CERTS_DIR:-${DOGRAH_INIT_CERTS_DIR:-/certs}}"

# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/setup_common.sh"

KODEWAVES_DEPLOY_PROJECT_DIR="$WORKSPACE_DIR"
KODEWAVES_DEPLOY_PROJECT_DIR="$WORKSPACE_DIR"
DOGRAH_DEPLOY_PROJECT_DIR="$WORKSPACE_DIR"

mkdir -p "$NGINX_OUTPUT_DIR" "$COTURN_OUTPUT_DIR"

if [[ "${ENVIRONMENT:-local}" == "production" ]]; then
    kodewaves_validate_remote_runtime_env
    [[ -f "$CERTS_DIR/local.crt" ]] || kodewaves_fail "certs/local.crt not found"
    [[ -f "$CERTS_DIR/local.key" ]] || kodewaves_fail "certs/local.key not found"

    export TURN_EXTERNAL_IP="$SERVER_IP"
    kodewaves_render_remote_nginx_conf "$WORKSPACE_DIR" "$NGINX_OUTPUT_DIR/default.conf"
    kodewaves_render_remote_turn_conf "$WORKSPACE_DIR" "$COTURN_OUTPUT_DIR/turnserver.conf"
    kodewaves_success "✓ kodewaves-init rendered remote nginx and coturn config"
    exit 0
fi

if [[ -n "${TURN_SECRET:-}" && -n "${TURN_HOST:-}" ]]; then
    export TURN_EXTERNAL_IP="$TURN_HOST"
    kodewaves_render_remote_turn_conf "$WORKSPACE_DIR" "$COTURN_OUTPUT_DIR/turnserver.conf"
    kodewaves_success "✓ kodewaves-init rendered local TURN config"
    exit 0
fi

kodewaves_success "✓ kodewaves-init no-op for current profile"
