# Client and voice integration review

Read-only committed-state comparison. No merge performed. Dirty working-tree and VPS changes are not included.

Client commit: a6d40d8886eaaf64fadfdc666bb3c0bcc7e3f074
Voice commit: 35ae46d3e7fc2c08b38099208c27ab4bdc3235cd
Common ancestor: b45d766a0f428209fd08b329f4a2a588b5c848cc

Shared changed paths: 50

Preserve both active checkouts. Capture uncommitted voice/VPS work before a dedicated integration checkout is created. Review shared paths individually; do not choose an entire branch side to resolve conflicts.

- .gitignore
- api/.env.example
- api/app.py
- api/db/kodewaves_client.py
- api/local_models/dhvaani/Dockerfile
- api/local_models/dhvaani/app.py
- api/local_models/dhvaani/voices/.gitignore
- api/local_models/dhvaani/voices/README.md
- api/local_models/indic_mio/app.py
- api/local_models/indic_parler/Dockerfile
- api/local_models/indic_parler/README.md
- api/local_models/indic_parler/app.py
- api/local_models/indic_vits/Dockerfile
- api/local_models/indic_vits/NOTICE.md
- api/local_models/indic_vits/app.py
- api/routes/admin/settings.py
- api/routes/crm.py
- api/routes/payments.py
- api/services/catalog/catalog_service.py
- api/services/catalog/local_inventory.py
- api/services/configuration/kodewaves_resolver.py
- api/services/configuration/registry.py
- api/services/configuration/speech_persona.py
- api/services/pipecat/booking_tool_choice.py
- api/services/pipecat/local_speech_aggregator.py
- api/services/pipecat/realtime_feedback_observer.py
- api/services/pipecat/service_factory.py
- api/services/pipecat/speaches_tts.py
- api/services/workflow/pipecat_engine.py
- api/services/workflow/pipecat_engine_context_composer.py
- api/services/workflow/tools/booking.py
- docker-compose.aapanel.yaml
- docker-compose.yaml
- scripts/warm_local_ollama.py
- ui/next.config.ts
- ui/src/app/admin/settings/page.tsx
- ui/src/app/billing-sovereign/page.tsx
- ui/src/app/forms/page.tsx
- ui/src/app/widgets/page.tsx
- ui/src/app/workflow/[workflowId]/run/[runId]/hooks/useWebSocketRTC.tsx
- ui/src/app/workflow/create/page.tsx
- ui/src/client/types.gen.ts
- ui/src/components/AIModelConfigurationV2Editor.tsx
- ui/src/components/VoiceSelectorModal.tsx
- ui/src/components/workflow/CreateWorkflowButton.tsx
- ui/src/components/workflow/TemplateCard.tsx
- ui/src/components/workflow/conversation/MessageBubble.tsx
- ui/src/components/workflow/conversation/activeBotMessage.ts
- ui/src/lib/kodewavesApi.ts
- ui/src/lib/promptTemplateWorkflow.ts

## Merge simulation

Simulation exit status: 1
Conflicting paths: 32

This simulation writes Git objects only. It does not check out or merge files.

- api/.env.example
- api/app.py
- api/db/kodewaves_client.py
- api/local_models/indic_vits/NOTICE.md
- api/local_models/indic_vits/app.py
- api/routes/admin/settings.py
- api/routes/crm.py
- api/routes/payments.py
- api/services/catalog/catalog_service.py
- api/services/catalog/local_inventory.py
- api/services/configuration/kodewaves_resolver.py
- api/services/configuration/speech_persona.py
- api/services/pipecat/booking_tool_choice.py
- api/services/pipecat/local_speech_aggregator.py
- api/services/pipecat/realtime_feedback_observer.py
- api/services/pipecat/service_factory.py
- api/services/pipecat/speaches_tts.py
- api/services/workflow/pipecat_engine.py
- api/services/workflow/pipecat_engine_context_composer.py
- api/services/workflow/tools/booking.py
- docker-compose.aapanel.yaml
- docker-compose.yaml
- ui/next.config.ts
- ui/src/app/admin/settings/page.tsx
- ui/src/app/billing-sovereign/page.tsx
- ui/src/app/workflow/[workflowId]/run/[runId]/hooks/useWebSocketRTC.tsx
- ui/src/app/workflow/create/page.tsx
- ui/src/components/AIModelConfigurationV2Editor.tsx
- ui/src/components/workflow/CreateWorkflowButton.tsx
- ui/src/components/workflow/TemplateCard.tsx
- ui/src/components/workflow/conversation/activeBotMessage.ts
- ui/src/lib/kodewavesApi.ts

## Working tree snapshot

On 28 October 2026 the client branch had 517 committed changed paths since the common ancestor, and the active production-integration checkout had 80 porcelain status entries. These counts are snapshots; recalculate after the voice owner hands off. The production VPS also has uncommitted files. Never use a committed-only merge as proof those changes are preserved.
