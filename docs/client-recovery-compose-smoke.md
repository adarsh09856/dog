# Disposable Docker recovery smoke test

`api/tests/test_client_recovery_compose_smoke.py` exercises the Docker volume
backup, restore, and rollback orchestration with real Postgres and MinIO data.
It is an explicitly opted-in developer/operations check; the normal test suite
skips it.

The test requires a Docker daemon and three **already available local images**:

- `KW_RECOVERY_SMOKE_POSTGRES_IMAGE`: Postgres or pgvector image pinned by
  `@sha256:<digest>`. It must include `/bin/sh` and `tar` because it is also the
  bounded volume snapshot helper.
- `KW_RECOVERY_SMOKE_MINIO_IMAGE`: local MinIO server image.
- `KW_RECOVERY_SMOKE_S3_CLIENT_IMAGE`: local Python image with the `minio`
  client package installed; used only as a one-shot client on the private test
  network.

Find local image references with `docker image ls --digests`. The test inspects
the selected images and uses `pull_policy: never` and `--pull=never`; it does
not download or build images. Example PowerShell setup:

```powershell
$env:KODEWAVES_RUN_DISPOSABLE_COMPOSE_RECOVERY = '1'
$env:KW_RECOVERY_SMOKE_POSTGRES_IMAGE = 'pgvector/pgvector:pg17@sha256:<local-digest>'
$env:KW_RECOVERY_SMOKE_MINIO_IMAGE = 'minio/minio:<local-tag>'
$env:KW_RECOVERY_SMOKE_S3_CLIENT_IMAGE = 'kodewaves-api:<local-tag>'
pytest api/tests/test_client_recovery_compose_smoke.py -q
```

The project name and all volume names are generated uniquely for each run. The
test creates only named test volumes and one internal-only Docker network. No
host ports are published, no external network access is available to test
services, and no existing host path or production volume is mounted. Postgres,
MinIO, and the volume helper have 256 MB and 0.25 CPU limits; other stand-ins
have lower limits. The helper container also has a 64 PID limit.

It writes a row to a real PostgreSQL instance and an object through the MinIO
S3 API, takes a cold backup, mutates the original data, restores to new
uniquely labeled volumes, checks the backed-up values, rolls back, and checks
the mutated values in the original volumes. Cleanup runs in `finally`, stops
the exact generated Compose project, removes its project-owned volumes and
network, and removes only recovery volumes bearing that run's recovery label.
Cleanup assertions fail the test if matching resources remain.

The API and UI service names are sleeping Postgres-image stand-ins, and Redis
is also a stand-in. This test does not start the Kodewaves application, verify
license/owner behavior, exercise telephony, or prove upgrade, production
restore, alerting, or customer acceptance. It tests volume orchestration and
data round-trip behavior only.
