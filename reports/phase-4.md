# Phase 4 Report: Resolver & Service Factory Stabilization

**Date:** 5 Oct 2026  
**Status:** COMPLETE  
**Git Branch:** `stabilize`  
**Test Suite:** `api/tests/test_resolver_and_factory.py` (9 tests passing, 21 regression tests total passing)

---

## 1. Executive Summary

In Work Package 4 (WP4), we unified configuration resolution across all conversational AI tiers (LLM, STT, TTS, S2S Realtime). We eliminated silent fallbacks, enforced strong typing with metadata attribution (`user_key`, `master_key`, `local`), integrated standard BCP-47 language normalization, and validated direct Google Gemini API key operation without requiring Google Cloud service account JSON files.

---

## 2. Key Architectural Deliverables

### 2.1 Unified Language Normalizer (`api/services/configuration/language_normalizer.py`)
- Standardizes arbitrary language inputs (e.g. `"Hindi"`, `"hi-IN"`, `"hi_in"`, `"en-US"`) to provider-compliant formats.
- **Deepgram**: Normalizes regional codes to 2-letter base ISO codes (`hi-IN` $\rightarrow$ `hi`, `en-US` $\rightarrow$ `en`, `es-ES` $\rightarrow$ `es`), preventing runtime failures with Deepgram's Nova models.
- **Sarvam AI**: Enforces BCP-47 locale format with regional tags (`hi` $\rightarrow$ `hi-IN`, `en` $\rightarrow$ `en-IN`, `bn` $\rightarrow$ `bn-IN`).
- **Piper Neural TTS**: Automatically selects high-quality Indic and English medium models (`hi` $\rightarrow$ `hi_IN-priyamvada-medium`, `en` $\rightarrow$ `en_US-lessac-medium`, `te` $\rightarrow$ `te_IN-rama-medium`, `ta` $\rightarrow$ `ta_IN-valluvar-medium`).

### 2.2 Strongly Typed Resolver (`api/services/configuration/kodewaves_resolver.py`)
- **ResolvedLayerInfo & ResolutionMetadata**: Each active layer (LLM, STT, TTS, Realtime) carries explicit metadata:
  ```python
  @dataclass
  class ResolvedLayerInfo:
      provider: str
      model: str
      source: Literal["user_key", "master_key", "local"]
      voice: Optional[str] = None
      language: Optional[str] = None
  ```
- Attached directly to `effective.resolution_info` for billing accounting, audit trails, and frontend inspectability.
- **Zero Silent Fallback**: If an explicit provider is selected (e.g. `deepgram`, `cartesia`, `openai`) but neither a BYOK key nor an active master credential exists, the resolver immediately raises `HTTPException(status_code=400, detail="Requested <layer> provider '<provider>' has no active master credentials or is disabled.")`.
- **Wallet & Minute Balance Enforcement**: Cloud master keys are guarded by organization minute ledger balances; local CPU engines remain 100% free and accessible regardless of balance.

### 2.3 Pipecat Service Factory Hardening (`api/services/pipecat/service_factory.py`)
- Added explicit first-class branches for `OLLAMA`, `PIPER`, and `WHISPER` in `create_llm_service_from_provider`, `create_stt_service`, and `create_tts_service`.
- Upgraded `KodewavesGoogleLLMService` and `KodewavesGeminiLiveLLMService` to initialize directly via `api_key` without demanding a GCP service account JSON credential file.
- Cleaned up sentinel token requirements (`sovereign-local-cpu`), enabling clean URL-based dispatching to local engine containers.

---

## 3. Test Verification Matrix

All 9 tests in `api/tests/test_resolver_and_factory.py` pass:

| Test Name | Description | Status |
|---|---|---|
| `test_deepgram_language_normalization` | Regional BCP-47 (`hi-IN`, `en-US`) mapped to primary codes (`hi`, `en`) | **PASSED** |
| `test_sarvam_language_normalization` | Language codes normalized to Indic BCP-47 (`hi-IN`, `en-IN`) | **PASSED** |
| `test_piper_voice_selection_by_language` | Auto-selection of Hindi (`priyamvada`) and English (`lessac`) voices | **PASSED** |
| `test_resolver_byok_priority` | User BYOK keys strictly take precedence over master platform keys | **PASSED** |
| `test_resolver_master_key_fallback` | Platform master credentials utilized when BYOK key omitted | **PASSED** |
| `test_resolver_zero_silent_fallback_error` | Missing credentials on explicit provider immediately raises 400 error | **PASSED** |
| `test_resolver_local_cpu_resolution` | Local CPU engines resolve to internal Docker endpoints with `local` source | **PASSED** |
| `test_gemini_llm_api_key_without_service_account` | Gemini LLM instantiates directly with API key without service account | **PASSED** |
| `test_ollama_llm_factory_initialization` | Ollama LLM instantiates with local base URL and model | **PASSED** |

**Total Regression Tests Passing:** 21 / 21 across Phase 1, Phase 2, Phase 3, and Phase 4.
