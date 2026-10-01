from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from api.services.configuration.registry import (
    DograhEmbeddingsConfiguration,
    DograhLLMService,
    DograhSTTService,
    DograhTTSService,
    EmbeddingsConfig,
    KodewavesEmbeddingsConfiguration,
    KodewavesLLMService,
    KodewavesSTTService,
    KodewavesTTSService,
    LLMConfig,
    RealtimeConfig,
    ServiceProviders,
    STTConfig,
    TTSConfig,
)

KODEWAVES_SPEED_MIN = 0.5
KODEWAVES_SPEED_MAX = 2.0
KODEWAVES_SPEED_STEP = 0.1
KODEWAVES_SPEED_OPTIONS: tuple[float, ...] = (0.8, 1.0, 1.2)
KODEWAVES_DEFAULT_VOICE = "default"
KODEWAVES_DEFAULT_LANGUAGE = "multi"

DOGRAH_SPEED_MIN = KODEWAVES_SPEED_MIN
DOGRAH_SPEED_MAX = KODEWAVES_SPEED_MAX
DOGRAH_SPEED_STEP = KODEWAVES_SPEED_STEP
DOGRAH_SPEED_OPTIONS = KODEWAVES_SPEED_OPTIONS
DOGRAH_DEFAULT_VOICE = KODEWAVES_DEFAULT_VOICE
DOGRAH_DEFAULT_LANGUAGE = KODEWAVES_DEFAULT_LANGUAGE


class EffectiveAIModelConfiguration(BaseModel):
    llm: LLMConfig | None = None
    stt: STTConfig | None = None
    tts: TTSConfig | None = None
    embeddings: EmbeddingsConfig | None = None
    realtime: RealtimeConfig | None = None
    is_realtime: bool = False
    managed_service_version: int | None = None
    test_phone_number: str | None = None
    timezone: str | None = None
    last_validated_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def strip_incomplete_realtime_when_disabled(cls, data):
        """Skip realtime validation when is_realtime is False and api_key is missing."""
        if isinstance(data, dict) and not data.get("is_realtime", False):
            realtime = data.get("realtime")
            if isinstance(realtime, dict) and not realtime.get("api_key"):
                data.pop("realtime", None)
        return data


class KodewavesManagedAIModelConfiguration(BaseModel):
    api_key: str = "sovereign-managed"
    voice: str = KODEWAVES_DEFAULT_VOICE
    speed: float = Field(default=1.0, ge=KODEWAVES_SPEED_MIN, le=KODEWAVES_SPEED_MAX)
    language: str = KODEWAVES_DEFAULT_LANGUAGE

    @model_validator(mode="before")
    @classmethod
    def default_empty_api_key(cls, data):
        if isinstance(data, dict):
            api_key = data.get("api_key")
            if not api_key or not str(api_key).strip():
                data["api_key"] = "sovereign-managed"
        return data


DograhManagedAIModelConfiguration = KodewavesManagedAIModelConfiguration


class BYOKPipelineAIModelConfiguration(BaseModel):
    llm: LLMConfig
    tts: TTSConfig
    stt: STTConfig
    embeddings: EmbeddingsConfig | None = None

    @model_validator(mode="after")
    def reject_kodewaves_providers(self):
        _reject_kodewaves_provider("llm", self.llm)
        _reject_kodewaves_provider("tts", self.tts)
        _reject_kodewaves_provider("stt", self.stt)
        _reject_kodewaves_provider("embeddings", self.embeddings)
        return self


class BYOKRealtimeAIModelConfiguration(BaseModel):
    realtime: RealtimeConfig
    llm: LLMConfig
    embeddings: EmbeddingsConfig | None = None

    @model_validator(mode="after")
    def reject_kodewaves_providers(self):
        _reject_kodewaves_provider("llm", self.llm)
        _reject_kodewaves_provider("embeddings", self.embeddings)
        return self


class BYOKAIModelConfiguration(BaseModel):
    mode: Literal["pipeline", "realtime"]
    pipeline: BYOKPipelineAIModelConfiguration | None = None
    realtime: BYOKRealtimeAIModelConfiguration | None = None

    @model_validator(mode="after")
    def validate_selected_mode(self):
        if self.mode == "pipeline" and self.pipeline is None:
            raise ValueError("byok.pipeline is required when byok.mode is pipeline")
        if self.mode == "realtime" and self.realtime is None:
            raise ValueError("byok.realtime is required when byok.mode is realtime")
        return self


class OrganizationAIModelConfigurationV2(BaseModel):
    version: Literal[2] = 2
    mode: Literal["kodewaves", "dograh", "byok"]
    kodewaves: KodewavesManagedAIModelConfiguration | None = None
    dograh: DograhManagedAIModelConfiguration | None = None
    byok: BYOKAIModelConfiguration | None = None

    @model_validator(mode="before")
    @classmethod
    def sync_kodewaves_dograh_fields(cls, data):
        if isinstance(data, dict):
            if data.get("mode") in ("kodewaves", "dograh"):
                cfg = data.get("kodewaves") or data.get("dograh")
                data["kodewaves"] = cfg
                data["dograh"] = cfg
        return data

    @model_validator(mode="after")
    def validate_selected_mode(self):
        if self.mode in ("kodewaves", "dograh") and self.kodewaves is None and self.dograh is None:
            raise ValueError("kodewaves configuration is required when mode is kodewaves")
        if self.mode == "byok" and self.byok is None:
            raise ValueError("byok configuration is required when mode is byok")
        return self


class OrganizationAIModelConfigurationResponse(BaseModel):
    configuration: dict | None
    effective_configuration: dict
    source: Literal["organization_v2", "legacy_user_v1", "empty"]


def compile_ai_model_configuration_v2(
    configuration: OrganizationAIModelConfigurationV2,
) -> EffectiveAIModelConfiguration:
    if configuration.mode in ("kodewaves", "dograh"):
        cfg = configuration.kodewaves or configuration.dograh
        if cfg is None:
            raise ValueError("kodewaves configuration is required")
        return _compile_kodewaves_configuration(cfg)

    if configuration.byok is None:
        raise ValueError("byok configuration is required")
    if configuration.byok.mode == "pipeline":
        if configuration.byok.pipeline is None:
            raise ValueError("byok.pipeline is required")
        pipeline = configuration.byok.pipeline
        return EffectiveAIModelConfiguration(
            llm=pipeline.llm,
            tts=pipeline.tts,
            stt=pipeline.stt,
            embeddings=pipeline.embeddings,
            is_realtime=False,
        )

    if configuration.byok.realtime is None:
        raise ValueError("byok.realtime is required")
    realtime = configuration.byok.realtime
    return EffectiveAIModelConfiguration(
        llm=realtime.llm,
        realtime=realtime.realtime,
        embeddings=realtime.embeddings,
        is_realtime=True,
    )


def _compile_kodewaves_configuration(
    configuration: KodewavesManagedAIModelConfiguration,
) -> EffectiveAIModelConfiguration:
    api_key = configuration.api_key or "sovereign-managed"
    return EffectiveAIModelConfiguration(
        llm=KodewavesLLMService(
            provider=ServiceProviders.KODEWAVES,
            api_key=api_key,
            model="default",
        ),
        tts=KodewavesTTSService(
            provider=ServiceProviders.KODEWAVES,
            api_key=api_key,
            model="default",
            voice=configuration.voice,
            speed=configuration.speed,
        ),
        stt=KodewavesSTTService(
            provider=ServiceProviders.KODEWAVES,
            api_key=api_key,
            model="default",
            language=configuration.language,
        ),
        embeddings=KodewavesEmbeddingsConfiguration(
            provider=ServiceProviders.KODEWAVES,
            api_key=api_key,
            model="kodewaves_embedding_v1",
        ),
        is_realtime=False,
        managed_service_version=2,
    )


_compile_dograh_configuration = _compile_kodewaves_configuration


def _reject_kodewaves_provider(section: str, service) -> None:
    if service is None:
        return
    if getattr(service, "provider", None) in (ServiceProviders.KODEWAVES, ServiceProviders.DOGRAH):
        raise ValueError(f"BYOK {section} cannot use Kodewaves provider")


_reject_dograh_provider = _reject_kodewaves_provider
