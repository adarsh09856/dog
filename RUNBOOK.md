# Kodewaves Sovereign Voice AI Platform — Operations Runbook

**Date:** October 2026  
**Version:** 2.0  
**Stack:** FastAPI, Next.js 15, PostgreSQL 17 + pgvector, Redis 7, MinIO, Coturn, Ollama, Piper, Whisper  

---

## 1. Platform Architecture & Service Layout

Kodewaves runs as a decoupled, multi-container system driven by Docker Compose with strict service profiles:

### Profiles
- **`core` (Default)**:
  - `postgres` (PostgreSQL 17 + pgvector, internal port `127.0.0.1:5432`)
  - `redis` (Redis 7 Alpine, internal port `127.0.0.1:6379`)
  - `minio` (S3-compatible audio storage, internal `127.0.0.1:9000` / `127.0.0.1:9001`)
  - `api` (FastAPI backend with Uvicorn, internal `127.0.0.1:8000`)
  - `ui` (Next.js 15 frontend, internal `127.0.0.1:3010`)
  - `coturn` (WebRTC STUN/TURN server, public UDP/TCP `3478`, `5349`, `49152-49350`)
- **`local` (Optional / Admin Opt-In)**:
  - `ollama` (Local LLM inference, internal `127.0.0.1:11434`, capped at 4GB RAM)
  - `piper` (Local ONNX Hindi/English TTS, internal `127.0.0.1:8766`, capped at 768MB RAM)
  - `whisper` (Local Faster-Whisper STT via speaches, internal `127.0.0.1:8765`, capped at 1.5GB RAM)
- **`tunnel` (Optional)**:
  - `cloudflared` (Cloudflare Tunnel for environments without a static public IP)
- **`proxy` (Optional)**:
  - `nginx` (Only used on standalone setups without aaPanel)

### Port Isolation Rule
All database, cache, storage, and API services are strictly bound to `127.0.0.1`. The host reverse proxy (aaPanel / Nginx / Traefik) is the sole entry point on ports `80` and `443`. Only Coturn WebRTC relay ports are open publicly.

---

## 2. Installation & Deployment

### 2.1 Fresh Installation (aaPanel or Plain VPS)
1. Ensure minimum system requirements:
   - **CPU**: 2+ vCPUs (4+ recommended for local AI)
   - **RAM**: 2GB minimum for Cloud cascade; 8GB recommended for Local AI
   - **Disk**: 20GB+ free NVMe/SSD space
2. Clone repository:
   ```bash
   git clone https://github.com/kodewaves/kodewaves.git
   cd kodewaves
   ```
3. Run the turnkey installer:
   ```bash
   sudo bash install.sh
   ```
   The installer validates preflight system floors, generates cryptographic secrets, detects available CPU cores for `FASTAPI_WORKERS`, provisions `.env`, starts core containers, applies database migrations, and prints reverse proxy configurations.

### 2.2 Updating & Redeploying
To deploy updates without downtime or data loss:
```bash
bash deploy.sh
```
`deploy.sh` performs:
1. Pulls git updates or packages local changes.
2. Performs automated pre-migration `pg_dump` backup.
3. Rebuilds containers with `--remove-orphans`.
4. Executes `alembic upgrade head`.
5. Executes `scripts.seed_platform` to sync catalog and sovereign defaults.
6. Prunes Docker build cache (`docker builder prune -af`) to prevent VPS disk exhaustion.
7. Verifies healthcheck endpoints.

---

## 3. Environment Variables & Master Vault

> [!WARNING]
> **KEY ROTATION MANDATORY**: The Google Gemini API key ending in `FVoQ` that was previously present in chat history files MUST be deleted in Google AI Studio immediately before staging or production deployment, and replaced with a newly generated key. AI assistants and local scripts cannot rotate upstream provider keys for you. In Google AI Studio / provider consoles, delete the exposed key and create a new one.

Master provider credentials (API keys for Gemini, OpenAI, Anthropic, Groq, Deepgram, Cartesia, ElevenLabs, Sarvam, Azure) are managed exclusively through the **Encrypted Database Vault** (`/api/v1/admin/master-keys`). They are encrypted at rest using AES-256 Fernet.

### Complete Environment Variable Reference (Appendix B)

| Variable | Default | Secret | Who May Change | Description & Operational Impact |
|---|---|---|---|---|
| `ENVIRONMENT` | `production` | No | Sysadmin | `production`, `development`, or `test`. |
| `DEPLOYMENT_MODE` | `oss` | No | Sysadmin | `oss` or `cloud`. Controls licensing and auth options. |
| `KODEWAVES_ENV` | `production` | No | Sysadmin | Canonical environment identifier. |
| `KODEWAVES_INSTANCE` | `node-1` | No | Sysadmin | Multi-cluster instance identifier. |
| `DOMAIN` | `localhost` | No | Sysadmin | Canonical domain name. |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | No | Sysadmin | Fully-qualified public URL with HTTPS scheme. |
| `BACKEND_API_ENDPOINT` | `http://localhost:8000` | No | Sysadmin | URL for carrier webhooks and external APIs. |
| `UI_APP_URL` | `http://localhost:3000` | No | Sysadmin | Frontend public URL for OAuth redirects. |
| `UI_INTERNAL_URL` | `http://ui:3010` | No | Sysadmin | Docker network internal address for UI SSR. |
| `CORS_ALLOWED_ORIGINS` | `*` | No | Sysadmin | Comma-separated list of allowed CORS origins. |
| `FORWARDED_ALLOW_IPS` | `*` | No | Sysadmin | Required so Uvicorn honors `X-Forwarded-Proto: https`. |
| `DATABASE_URL` | — | Yes | Sysadmin | PostgreSQL asyncpg connection string. |
| `REDIS_URL` | — | Yes | Sysadmin | Redis connection string with auth password. |
| `MASTER_CREDENTIAL_ENCRYPTION_KEY` | — | Yes | Sysadmin | 32-byte Fernet base64 key for database vault. |
| `OSS_JWT_SECRET` | — | Yes | Sysadmin | Secret for signing user session JWTs. |
| `OSS_JWT_EXPIRY_HOURS` | `720` | No | Sysadmin | Session token lifespan (default 30 days). |
| `AUTH_PROVIDER` | `local` | No | Sysadmin | `local` (email/password) or `stack`. |
| `STACK_AUTH_*` | `""` | Yes | Sysadmin | Optional Stack Auth project configuration. |
| `KODEWAVES_DEVOPS_SECRET` | — | Yes | Sysadmin | Secret protecting administrative health and update endpoints. |
| `DEFAULT_ORG_CONCURRENCY_LIMIT` | `10` | No | Admin | Fallback concurrent calls cap per tenant. |
| `MAX_CONCURRENT_CALLS` | `50` | No | Admin | Platform-wide concurrent calls ceiling. |
| `local_ai_max_concurrency` | `2` | No | Admin | Simultaneous call capacity for local CPU inference. |
| `FASTAPI_WORKERS` | `auto` | No | Sysadmin | Uvicorn worker count. Scaled from CPU (`1-4`). |
| `ARQ_WORKERS` | `1` | No | Sysadmin | Background task worker concurrency. |
| `ASGI_WORKER_ID` | `1` | No | System | Sequential process worker ID. |
| `SKIP_TELEPHONY_SIGNATURE_VERIFICATION` | `false` | No | Sysadmin | **REFUSED IN PRODUCTION**. Must be false. |
| `TELEPHONY_WS_TOKEN_SECRET` | `""` | Yes | Sysadmin | HMAC secret for signing carrier media websocket URLs. |
| `TELEPHONY_WS_TOKEN_ENFORCE` | `false` | No | Sysadmin | Enforce signature check on carrier media websockets. |
| `ENABLE_ARI_MANAGER` | `false` | No | Sysadmin | Starts Asterisk ARI bridge process. |
| `ENABLE_ARI_STASIS` | `false` | No | Sysadmin | Enables Asterisk Stasis application listeners. |
| `ENABLE_CAMPAIGN_ORCHESTRATOR` | `false` | No | Sysadmin | Starts outbound campaign dialing worker. |
| `ENABLE_CALL_RECORDING_UPLOAD` | `true` | No | Admin | Uploads audio recordings to MinIO bucket. |
| `ENABLE_AWS_S3` | `false` | No | Sysadmin | Use AWS S3 instead of local MinIO. |
| `MINIO_*` | — | Yes | Sysadmin | Storage credentials, endpoints, and bucket names. |
| `ENABLE_COTURN` | `true` | No | Sysadmin | Starts Coturn STUN/TURN server container. |
| `TURN_HOST` | `localhost` | No | Sysadmin | Public hostname or IP for WebRTC relay. |
| `TURN_SECRET` | — | Yes | Sysadmin | Shared secret for time-limited TURN REST tokens. |
| `TURN_USERNAME` | `kodewaves` | No | Sysadmin | Coturn static username. |
| `TURN_PASSWORD` | — | Yes | Sysadmin | Coturn static password matching TURN_SECRET. |
| `TURN_PORT` | `3478` | No | Sysadmin | Coturn standard listening port. |
| `TURN_TLS_PORT` | `5349` | No | Sysadmin | Coturn TLS listening port. |
| `TURN_CREDENTIAL_TTL` | `86400` | No | Sysadmin | Validity period of ephemeral TURN credentials (24h). |
| `FORCE_TURN_RELAY` | `false` | No | Admin | Force all WebRTC traffic through TURN relay. |
| `ENABLE_LOCAL_AI_ENGINE` | `true` | No | Admin | Enables local Ollama, Piper, and Whisper profile. |
| `OLLAMA_ENDPOINT` | `http://ollama:11434` | No | Sysadmin | Ollama API endpoint. |
| `PIPER_ENDPOINT` | `http://piper:5000` | No | Sysadmin | Piper TTS HTTP synthesize endpoint. |
| `WHISPER_ENDPOINT` | `http://whisper:8000/v1` | No | Sysadmin | Faster-Whisper OpenAI-compatible STT endpoint. |
| `WEBHOOK_DELIVERY_*` | — | No | Sysadmin | Retry backoff and timeout parameters for outbound webhooks. |
| `LOG_FILE_PATH` | `logs/kodewaves.log` | No | Sysadmin | File logging path. |
| `LOG_ROTATION_SIZE` | `20 MB` | No | Sysadmin | Size triggering log file rotation. |
| `LOG_RETENTION` | `30 days` | No | Sysadmin | Retention window for rotated logs. |
| `LOG_COMPRESSION` | `zip` | No | Sysadmin | Compression format for rotated logs. |
| `SERIALIZE_LOG_OUTPUT` | `false` | No | Sysadmin | Format logs as JSON. |
| `ENABLE_TURN_LOGGING` | `false` | No | Admin | Detailed conversation turn telemetry. |
| `SENTRY_DSN` | `""` | Yes | Sysadmin | Sentry error tracking project DSN. |
| `ENABLE_TELEMETRY` | `false` | No | Sysadmin | Product analytics toggle. |
| `ENABLE_PROMETHEUS_METRICS` | `false` | No | Sysadmin | Prometheus `/metrics` scraping toggle. |
| `KODEWAVES_DOCS_PATH` | `./docs` | No | Sysadmin | Product documentation directory. |
| `TUNER_BASE_URL` | `""` | No | Sysadmin | Optional voice prompt tuner service. |
| `RAZORPAY_*` | — | Yes | Admin | Payment gateway keys (DB settings take precedence). |
| `STRIPE_*` | — | Yes | Admin | Payment gateway keys (DB settings take precedence). |
| `OPENAI_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `GEMINI_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `GOOGLE_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `ANTHROPIC_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `GROQ_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `DEEPGRAM_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `CARTESIA_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `ELEVENLABS_API_KEY` | — | Yes | Bootstrap | Fallback key (prefer Vault in DB). |
| `AZURE_SPEECH_REGION` | — | No | Bootstrap | Azure region (e.g. `eastus`). |
| `GENDERAPI_API_KEY` | — | Yes | Bootstrap | Fallback key for gender detection. |
| `GENDER_API_KEY` | — | Yes | Bootstrap | Fallback key alias. |

---

## 4. Operational Maintenance & Monitoring

### 4.1 Running Smoke Tests
Run the automated verification suite to validate that all services and security gates are functioning:
```bash
./scripts/smoke_test.sh
```

### 4.2 Backups & Disaster Recovery
- **Database Backup**:
  ```bash
  docker exec kodewaves_postgres pg_dump -U postgres postgres > backup_$(date +%Y%m%d).sql
  ```
- **Database Restore**:
  ```bash
  cat backup_20261006.sql | docker exec -i kodewaves_postgres psql -U postgres -d postgres
  ```
- **Audio Recordings Backup**:
  Back up the `kodewaves_minio_data` Docker volume or sync the bucket directly via MinIO Client (`mc`):
  ```bash
  mc mirror local/voice-audio s3-backup/voice-audio
  ```

### 4.3 Routine Maintenance & Cache Cleanup
Run the weekly maintenance script to prune old Docker build caches and dangling images:
```bash
bash scripts/docker_clean.sh
```

---

## 5. Security & Incident Response

### 5.1 Telephony Webhook Signature Failures (HTTP 403 / 401)
- Verify `FORWARDED_ALLOW_IPS="*"` in `.env` so Uvicorn honors `X-Forwarded-Proto: https`.
- Verify the public URL configured on Twilio/Exotel matches `PUBLIC_BASE_URL` exactly.
- Run the signature simulator:
  ```bash
  python -m scripts.e2e.twilio_signature --url "https://your-domain.com/telephony/inbound/twilio" --auth-token "<token>"
  ```

### 5.2 Capacity & Concurrency Overload (HTTP 429)
If users receive "Platform busy / limit reached":
1. Check live calls: Admin Panel -> Live Calls (`/admin/live-calls`).
2. Adjust concurrency limits: Admin Panel -> Settings -> Concurrency.
3. If local AI inference is pegged, check `local_ai_max_concurrency` (default 2) and verify thread clamping is active (`OMP_NUM_THREADS=1`).
