#!/usr/bin/env bash
set -e

###############################################################################
### CONFIGURATION
###############################################################################

BASE_DIR="$(cd "$(dirname "$(dirname "${BASH_SOURCE[0]}")")" && pwd)"
ENV_FILE="$BASE_DIR/api/.env"

# Clamp CPU thread spinning in OpenMP, PyTorch, BLAS, and NumPy
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OMP_WAIT_POLICY=PASSIVE
export TORCH_NUM_THREADS=1
export KMP_BLOCKTIME=0
export GOMP_SPINCOUNT=0
export KMP_AFFINITY=disabled

ARQ_WORKERS=1
FASTAPI_WORKERS=1
UVICORN_BASE_PORT=${UVICORN_BASE_PORT:-8000}

cd "$BASE_DIR"
echo "Starting Dograh Services (DOCKER) at $(date) in BASE_DIR: ${BASE_DIR}"

###############################################################################
### 1) Load env file if mounted (env normally comes from docker-compose)
###############################################################################

if [[ -f "$ENV_FILE" ]]; then
  set -a && . "$ENV_FILE" && set +a
fi

###############################################################################
### 2) Run migrations
###############################################################################

alembic -c "$BASE_DIR/api/alembic.ini" upgrade head

###############################################################################
### 3) Signal handling — forward TERM/INT to children for clean docker stop
###############################################################################

pids=()

shutdown() {
  echo "Received shutdown signal, stopping services..."
  for pid in "${pids[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  wait
  exit 0
}

trap shutdown TERM INT

start() {
  local name=$1
  shift
  echo "→ Starting $name"
  "$@" &
  pids+=($!)
  echo "  $name PID $!"
}

###############################################################################
### 4) Start services (logs go to stdout for `docker logs`)
###############################################################################

# ari_manager and campaign_orchestrator are optional; each defaults to on and
# can be turned off (e.g. for an API/worker-only replica) by setting the flag to
# "false" in the container env / docker-compose .env.
ENABLE_ARI_MANAGER=false
ENABLE_CAMPAIGN_ORCHESTRATOR=${ENABLE_CAMPAIGN_ORCHESTRATOR:-false}

if [[ "$ENABLE_ARI_MANAGER" == "true" ]]; then
  start ari_manager           python -m api.services.telephony.ari_manager
else
  echo "ari_manager disabled (ENABLE_ARI_MANAGER=$ENABLE_ARI_MANAGER)"
fi

if [[ "$ENABLE_CAMPAIGN_ORCHESTRATOR" == "true" ]]; then
  start campaign_orchestrator python -m api.services.campaign.campaign_orchestrator
else
  echo "campaign_orchestrator disabled (ENABLE_CAMPAIGN_ORCHESTRATOR=$ENABLE_CAMPAIGN_ORCHESTRATOR)"
fi

# Spawn FASTAPI_WORKERS independent uvicorn processes on consecutive ports
# starting at UVICORN_BASE_PORT. nginx upstream (configured in setup_remote.sh)
# balances across them with least_conn — better than uvicorn --workers for
# long-lived WebSocket connections, which would otherwise stick to whichever
# worker accepted them first.
for ((i=0; i<FASTAPI_WORKERS; i++)); do
  port=$((UVICORN_BASE_PORT + i))
  start "uvicorn$i" uvicorn api.app:app --host 0.0.0.0 --port "$port" --workers 1
done

for ((i=1; i<=ARQ_WORKERS; i++)); do
  start "arq$i" python -m arq api.tasks.arq.WorkerSettings --custom-log-dict api.tasks.arq.LOG_CONFIG
done

###############################################################################
### 5) Wait — if any service exits, tear the container down so docker restarts
###############################################################################

START_TIME=$(date +%s)
wait -n
EXIT_TIME=$(date +%s)
UPTIME=$((EXIT_TIME - START_TIME))
echo "A service exited after ${UPTIME}s; tearing down container."
if [ "$UPTIME" -lt 10 ]; then
  echo "Service exited in under 10s (${UPTIME}s). Backing off for 10s to prevent rapid CPU crash-loop..."
  sleep 10
fi
shutdown
