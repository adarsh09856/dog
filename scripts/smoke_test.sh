#!/usr/bin/env bash
# ==============================================================================
# Kodewaves Sovereign Platform — Deployment Smoke Test Suite
# Part of Work Package 11 (Deployment Hardening & Final Gate)
# ==============================================================================
# Usage:
#   ./scripts/smoke_test.sh
#   API_URL=http://localhost:8000 UI_URL=http://localhost:3010 ./scripts/smoke_test.sh
# ==============================================================================

set -uo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

API_URL="${API_URL:-http://127.0.0.1:8000}"
UI_URL="${UI_URL:-http://127.0.0.1:3010}"
PIPER_URL="${PIPER_URL:-http://127.0.0.1:8766}"
WHISPER_URL="${WHISPER_URL:-http://127.0.0.1:8765}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

PASS_COUNT=0
FAIL_COUNT=0

check() {
    local name="$1"
    local command="$2"
    echo -n "  • Checking $name... "
    if eval "$command" >/dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo -e "${RED}FAIL${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

echo -e "${BLUE}${BOLD}==============================================================================${NC}"
echo -e "${BOLD} 🧪 Kodewaves Sovereign Voice AI — Smoke Test Verification${NC}"
echo -e "${BLUE}${BOLD}==============================================================================${NC}"
echo ""

# 1. API Health Checks
echo -e "${BOLD}[1/4] Core API Health & Security Invariants${NC}"
check "API Root Endpoint (/)" "curl -fsS ${API_URL}/"
check "API Health Check (/health)" "curl -fsS ${API_URL}/health | grep -q '\"status\":\"ok\"'"
check "API v1 Health Check (/api/v1/health)" "curl -fsS ${API_URL}/api/v1/health | grep -q '\"status\":\"ok\"'"
check "Admin Route Gate (Unauthenticated Blocked 401/403)" "curl -s -o /dev/null -w '%{http_code}' ${API_URL}/api/v1/admin/master-keys | grep -E '^(401|403)$'"
check "Catalog Endpoint Availability (/api/v1/catalog/available)" "curl -s -o /dev/null -w '%{http_code}' ${API_URL}/api/v1/catalog/available | grep -E '^(200|401)$'"

# 2. Frontend UI Health Check
echo ""
echo -e "${BOLD}[2/4] Frontend UI Health & Next.js Endpoints${NC}"
check "UI Container Health (/api/health)" "curl -fsS ${UI_URL}/api/health | grep -q '\"status\":\"ok\"'"
check "UI Web Application Root (/)" "curl -fsS ${UI_URL}/ | grep -qi -E '(html|kodewaves|doctype)'"

# 3. Security & Telephony Signature Invariant
echo ""
echo -e "${BOLD}[3/4] Security Configuration & Guardrails${NC}"
if [ -f "api/.env" ]; then
    check "SKIP_TELEPHONY_SIGNATURE_VERIFICATION Refused" "! grep -qE '^SKIP_TELEPHONY_SIGNATURE_VERIFICATION=[\"'\'' ]*true' api/.env"
else
    echo "  • Skipping api/.env check (offline or running in container)"
fi

# 4. Local AI Engines (Opt-in Check)
echo ""
echo -e "${BOLD}[4/4] Local Self-Hosted CPU AI Engines (Optional)${NC}"
if curl -fsS "${PIPER_URL}/voices" >/dev/null 2>&1; then
    check "Piper TTS HTTP Server (/voices)" "curl -fsS ${PIPER_URL}/voices"
else
    echo -e "  • Piper TTS: ${YELLOW}Inactive or not running (Local profile disabled)${NC}"
fi

if curl -fsS "${WHISPER_URL}/health" >/dev/null 2>&1; then
    check "Whisper STT Server (/health)" "curl -fsS ${WHISPER_URL}/health"
else
    echo -e "  • Whisper STT: ${YELLOW}Inactive or not running (Local profile disabled)${NC}"
fi

if curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    check "Ollama LLM Server (/api/tags)" "curl -fsS ${OLLAMA_URL}/api/tags"
else
    echo -e "  • Ollama LLM: ${YELLOW}Inactive or not running (Local profile disabled)${NC}"
fi

echo ""
echo -e "${BOLD}==============================================================================${NC}"
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ ALL SMOKE TESTS PASSED (${PASS_COUNT} checks passed)${NC}"
    exit 0
else
    echo -e "${RED}${BOLD}✗ SMOKE TESTS FAILED (${FAIL_COUNT} failed, ${PASS_COUNT} passed)${NC}"
    exit 1
fi
