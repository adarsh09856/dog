#!/usr/bin/env bash
# Backward compatibility forwarder to run_kodewaves_init.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run_kodewaves_init.sh" "$@"
