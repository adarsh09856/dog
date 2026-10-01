{{/*
Common helpers.
*/}}

{{- define "kodewaves.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kodewaves.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "kodewaves.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kodewaves.labels" -}}
helm.sh/chart: {{ include "kodewaves.chart" . }}
{{ include "kodewaves.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "kodewaves.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kodewaves.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "kodewaves.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kodewaves.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Component-specific names.
*/}}
{{- define "kodewaves.web.fullname" -}}{{ include "kodewaves.fullname" . }}-web{{- end }}
{{- define "kodewaves.arqWorker.fullname" -}}{{ include "kodewaves.fullname" . }}-arq-worker{{- end }}
{{- define "kodewaves.ariManager.fullname" -}}{{ include "kodewaves.fullname" . }}-ari-manager{{- end }}
{{- define "kodewaves.campaignOrchestrator.fullname" -}}{{ include "kodewaves.fullname" . }}-campaign-orchestrator{{- end }}
{{- define "kodewaves.ui.fullname" -}}{{ include "kodewaves.fullname" . }}-ui{{- end }}
{{- define "kodewaves.coturn.fullname" -}}{{ include "kodewaves.fullname" . }}-coturn{{- end }}
{{- define "kodewaves.migrate.fullname" -}}{{ include "kodewaves.fullname" . }}-migrate{{- end }}

{{- define "kodewaves.configMapName" -}}{{ include "kodewaves.fullname" . }}-config{{- end }}
{{- define "kodewaves.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- include "kodewaves.fullname" . }}-secret
{{- end -}}
{{- end }}

{{/*
Image reference.
*/}}
{{- define "kodewaves.image" -}}
{{- $registry := .Values.image.registry | default "docker.io" -}}
{{- printf "%s/%s:%s" $registry .Values.image.repository .Values.image.tag -}}
{{- end }}

{{- define "kodewaves.ui.image" -}}
{{- $registry := .Values.ui.image.registry | default "docker.io" -}}
{{- printf "%s/%s:%s" $registry .Values.ui.image.repository .Values.ui.image.tag -}}
{{- end }}

{{- define "kodewaves.coturn.image" -}}
{{- $registry := .Values.coturn.image.registry | default "docker.io" -}}
{{- printf "%s/%s:%s" $registry .Values.coturn.image.repository .Values.coturn.image.tag -}}
{{- end }}

{{/*
Subchart enabling — flips top-level chart-dependency `enabled` flags from mode.
Called from each template via `include "kodewaves.deps.resolved" .` (no-op output).
*/}}
{{- define "kodewaves.deps.resolved" -}}
{{- /* compute whether internal deps are enabled */ -}}
{{- end }}

{{/*
In-cluster service references for internal deps.
*/}}
{{- define "kodewaves.postgresHost" -}}{{ .Release.Name }}-postgresql{{- end }}
{{- define "kodewaves.redisHost" -}}{{ .Release.Name }}-redisinternal-master{{- end }}
{{- define "kodewaves.minioHost" -}}{{ .Release.Name }}-minio{{- end }}

{{/*
Resolved passwords for the bundled internal deps.
Precedence: explicit value in values.yaml wins; else reuse the value already
stored in the Secret (so `helm upgrade` does NOT rotate the password and desync a
running datastore); else generate a fresh one. `lookup` returns empty during
`helm template` (no cluster), so dry renders get a throwaway random value — fine.
Each is materialized in exactly one place (the dep's Secret); every other
reference is a secretKeyRef, so the generated value is stable within a render.
*/}}
{{- define "kodewaves.postgresPassword" -}}
{{- if .Values.postgresql.auth.password -}}
{{- .Values.postgresql.auth.password -}}
{{- else -}}
{{- $s := lookup "v1" "Secret" .Release.Namespace (printf "%s-postgresql" .Release.Name) -}}
{{- if and $s $s.data (index $s.data "password") -}}
{{- index $s.data "password" | b64dec -}}
{{- else -}}
{{- randAlphaNum 24 -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "kodewaves.redisPassword" -}}
{{- if .Values.redisinternal.auth.password -}}
{{- .Values.redisinternal.auth.password -}}
{{- else -}}
{{- $s := lookup "v1" "Secret" .Release.Namespace (printf "%s-redisinternal" .Release.Name) -}}
{{- if and $s $s.data (index $s.data "redis-password") -}}
{{- index $s.data "redis-password" | b64dec -}}
{{- else -}}
{{- randAlphaNum 24 -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "kodewaves.minioRootPassword" -}}
{{- if .Values.minio.auth.rootPassword -}}
{{- .Values.minio.auth.rootPassword -}}
{{- else -}}
{{- $s := lookup "v1" "Secret" .Release.Namespace (printf "%s-minio" .Release.Name) -}}
{{- if and $s $s.data (index $s.data "root-password") -}}
{{- index $s.data "root-password" | b64dec -}}
{{- else -}}
{{- randAlphaNum 24 -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Default DATABASE_URL when database.mode=internal.
The bundled Postgres (templates/internal-postgres.yaml) stores the app-user
password in the <release>-postgresql Secret under key `password`; kodewaves.dbEnv
projects it into $(POSTGRES_PASSWORD), which this URL interpolates at runtime.
Auth username/database default to `kodewaves` (see values.postgresql.auth).
*/}}
{{- define "kodewaves.databaseUrl" -}}
{{- if eq .Values.database.mode "internal" -}}
postgresql+asyncpg://{{ .Values.postgresql.auth.username }}:$(POSTGRES_PASSWORD)@{{ include "kodewaves.postgresHost" . }}:5432/{{ .Values.postgresql.auth.database }}
{{- else -}}
$(DATABASE_URL)
{{- end -}}
{{- end }}

{{- define "kodewaves.redisUrl" -}}
{{- if eq .Values.redis.mode "internal" -}}
redis://:$(REDIS_PASSWORD)@{{ include "kodewaves.redisHost" . }}:6379
{{- else -}}
$(REDIS_URL)
{{- end -}}
{{- end }}

{{/*
Database / Redis connection env for backend workloads (web, arq, singletons,
migrate).

ORDER IS LOAD-BEARING. POSTGRES_PASSWORD / REDIS_PASSWORD are declared BEFORE
DATABASE_URL / REDIS_URL because Kubernetes only expands a $(VAR) reference to
an env var defined *earlier* in the same container's env list — a forward
reference is left as the literal string "$(VAR)". DATABASE_URL / REDIS_URL
embed $(POSTGRES_PASSWORD) / $(REDIS_PASSWORD) (see kodewaves.databaseUrl /
kodewaves.redisUrl), so the password vars must come first or the composed URLs
ship with a literal "$(POSTGRES_PASSWORD)" as the password.
*/}}
{{- define "kodewaves.dbEnv" -}}
{{- if eq .Values.database.mode "internal" }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-postgresql
      key: password
{{- end }}
{{- if eq .Values.redis.mode "internal" }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-redisinternal
      key: redis-password
{{- end }}
- name: DATABASE_URL
  value: {{ include "kodewaves.databaseUrl" . | quote }}
- name: REDIS_URL
  value: {{ include "kodewaves.redisUrl" . | quote }}
{{- if eq .Values.storage.mode "internalMinio" }}
{{- /* Internal MinIO creds come from the <release>-minio secret, the same
       source the MinIO server uses (no ordering constraint — no composition). */}}
- name: MINIO_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-minio
      key: root-user
- name: MINIO_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-minio
      key: root-password
{{- end }}
{{- end }}

{{/*
Common env block for backend workloads (web, arq, singletons, migrate).
References the ConfigMap + Secret via envFrom. DATABASE_URL and REDIS_URL
are added inline because they may need composition from subchart secrets.
*/}}
{{- define "kodewaves.backendEnvFrom" -}}
- configMapRef:
    name: {{ include "kodewaves.configMapName" . }}
- secretRef:
    name: {{ include "kodewaves.secretName" . }}
{{- end }}
