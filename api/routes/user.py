import logging
import os
from datetime import datetime, timedelta
from typing import List, Literal, Optional, TypedDict, Union
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.responses import Response
from pydantic import BaseModel, Field, ValidationError

from api.db import db_client
from api.db.kodewaves_client import kodewaves_db_client
from api.db.models import (
    UserModel,
)
from api.errors.failure import ErrorSource, classify_exception, log_failure
from api.errors.mps import MPSUnavailableError
from api.schemas.onboarding_state import OnboardingState, OnboardingStateUpdate
from api.schemas.widget_texts import WidgetTexts
from api.schemas.workflow_configurations import (
    CallDispositionOption,
    TextChatInactivityTimeoutConstraints,
    WorkflowConfigurationDefaults,
    get_default_call_disposition_options,
    get_default_workflow_configurations,
)
from api.services.auth.depends import get_user
from api.services.credentials.master_credential_service import master_credential_service
from api.utils.common import normalize_local_ai_endpoint
from api.services.configuration.ai_model_configuration import (
    convert_legacy_ai_model_configuration_to_v2,
    get_resolved_ai_model_configuration,
    update_organization_ai_model_configuration_last_validated_at,
    upsert_organization_ai_model_configuration_v2,
)
from api.services.configuration.check_validity import (
    APIKeyStatusResponse,
    UserConfigurationValidator,
)
from api.services.configuration.defaults import DEFAULT_SERVICE_PROVIDERS
from api.services.configuration.masking import check_for_masked_keys, mask_user_config
from api.services.configuration.merge import merge_user_configurations
from api.services.configuration.registry import REGISTRY, ServiceType
from api.services.mps_service_key_client import mps_service_key_client
from api.services.organization_preferences import (
    get_organization_preferences,
    upsert_organization_preferences,
)
from api.services.user_onboarding import (
    get_onboarding_state,
    update_onboarding_state,
)
from api.services.workflow.answer_classification_service import (
    ANSWER_CLASSIFIER_SYSTEM_PROMPT,
)

router = APIRouter(prefix="/user")


class AuthUserResponse(TypedDict):
    id: int
    is_superuser: bool


class DefaultConfigurationsResponse(BaseModel):
    llm: dict[str, dict]
    tts: dict[str, dict]
    stt: dict[str, dict]
    embeddings: dict[str, dict]
    realtime: dict[str, dict]
    default_providers: dict[str, str]
    workflow_configurations: WorkflowConfigurationDefaults
    default_call_dispositions: list[CallDispositionOption] = Field(
        description=(
            "Built-in suggestions for call-disposition extraction. They do not "
            "enable extraction until saved in workflow_configurations.call_dispositions."
        )
    )
    default_answer_classifier_prompt: str = Field(
        description=(
            "Built-in instructions for the voicemail/screening classifier. The "
            "editor starts from these when a workflow has saved none of its own; "
            "a workflow that has saved instructions keeps showing those."
        )
    )
    text_chat_inactivity_timeout_constraints: TextChatInactivityTimeoutConstraints
    widget_text_defaults: WidgetTexts


@router.get("/configurations/defaults")
async def get_default_configurations() -> DefaultConfigurationsResponse:
    configurations = {
        "llm": {
            provider: model_cls.model_json_schema()
            for provider, model_cls in REGISTRY[ServiceType.LLM].items()
        },
        "tts": {
            provider: model_cls.model_json_schema()
            for provider, model_cls in REGISTRY[ServiceType.TTS].items()
        },
        "stt": {
            provider: model_cls.model_json_schema()
            for provider, model_cls in REGISTRY[ServiceType.STT].items()
        },
        "embeddings": {
            provider: model_cls.model_json_schema()
            for provider, model_cls in REGISTRY[ServiceType.EMBEDDINGS].items()
        },
        "realtime": {
            provider: model_cls.model_json_schema()
            for provider, model_cls in REGISTRY[ServiceType.REALTIME].items()
        },
        "default_providers": DEFAULT_SERVICE_PROVIDERS,
        "workflow_configurations": get_default_workflow_configurations(),
        "default_call_dispositions": get_default_call_disposition_options(),
        "default_answer_classifier_prompt": ANSWER_CLASSIFIER_SYSTEM_PROMPT,
        "text_chat_inactivity_timeout_constraints": (
            TextChatInactivityTimeoutConstraints()
        ),
        "widget_text_defaults": WidgetTexts(),
    }
    return DefaultConfigurationsResponse(**configurations)


@router.get("/auth/user")
async def get_auth_user(
    user: UserModel = Depends(get_user),
) -> AuthUserResponse:
    return {
        "id": user.id,
        "is_superuser": user.is_superuser,
    }


class UserConfigurationRequestResponseSchema(BaseModel):
    llm: dict[str, Union[str, float, list[str], None]] | None = None
    tts: dict[str, Union[str, float, list[str], None]] | None = None
    stt: dict[str, Union[str, float, list[str], None]] | None = None
    embeddings: dict[str, Union[str, float, list[str], None]] | None = None
    realtime: dict[str, Union[str, float, list[str], None]] | None = None
    is_realtime: bool | None = None
    test_phone_number: str | None = None
    timezone: str | None = None
    organization_pricing: dict[str, Union[float, str, bool]] | None = None


def _is_validation_cache_stale(
    last_validated_at: datetime | None,
    validity_ttl_seconds: int,
) -> bool:
    if last_validated_at is None:
        return True

    has_timezone = (
        last_validated_at.tzinfo is not None
        and last_validated_at.utcoffset() is not None
    )
    if has_timezone:
        now = datetime.now(last_validated_at.tzinfo)
    else:
        now = datetime.now()
    return last_validated_at < now - timedelta(seconds=validity_ttl_seconds)


@router.get("/configurations/user")
async def get_user_configurations(
    user: UserModel = Depends(get_user),
) -> UserConfigurationRequestResponseSchema:
    resolved_config = await get_resolved_ai_model_configuration(
        organization_id=user.selected_organization_id,
    )
    masked_config = mask_user_config(resolved_config.effective)
    if user.selected_organization_id:
        preferences = await get_organization_preferences(user.selected_organization_id)
        if preferences.test_phone_number is not None:
            masked_config["test_phone_number"] = preferences.test_phone_number
        if preferences.timezone is not None:
            masked_config["timezone"] = preferences.timezone

    # Add organization pricing info if available
    if user.selected_organization_id:
        org = await db_client.get_organization_by_id(user.selected_organization_id)
        if org and org.price_per_second_usd is not None:
            masked_config["organization_pricing"] = {
                "price_per_second_usd": org.price_per_second_usd,
                "currency": "USD",
                "billing_enabled": True,
            }

    return masked_config


@router.put("/configurations/user")
async def update_user_configurations(
    request: UserConfigurationRequestResponseSchema,
    user: UserModel = Depends(get_user),
) -> UserConfigurationRequestResponseSchema:
    existing_config = (
        await get_resolved_ai_model_configuration(
            organization_id=user.selected_organization_id,
        )
    ).effective

    incoming_dict = request.model_dump(exclude_none=True)

    # Remove organization_pricing from incoming dict as it's read-only
    incoming_dict.pop("organization_pricing", None)
    preferences_update = {
        key: incoming_dict.pop(key)
        for key in ("test_phone_number", "timezone")
        if key in incoming_dict
    }

    if incoming_dict:
        if not user.selected_organization_id:
            raise HTTPException(status_code=400, detail="No organization selected")

        # Merge via helper
        try:
            user_configurations = merge_user_configurations(
                existing_config, incoming_dict
            )
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))

        try:
            check_for_masked_keys(user_configurations)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        try:
            validator = UserConfigurationValidator()
            await validator.validate(
                user_configurations,
                organization_id=user.selected_organization_id,
                created_by=user.provider_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=e.args[0])

        try:
            organization_configuration = convert_legacy_ai_model_configuration_to_v2(
                user_configurations
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        await upsert_organization_ai_model_configuration_v2(
            user.selected_organization_id,
            organization_configuration,
        )
    else:
        user_configurations = existing_config

    if user.selected_organization_id and preferences_update:
        preferences = await get_organization_preferences(user.selected_organization_id)
        if "test_phone_number" in preferences_update:
            preferences.test_phone_number = preferences_update["test_phone_number"]
        if "timezone" in preferences_update:
            preferences.timezone = preferences_update["timezone"]
        await upsert_organization_preferences(
            user.selected_organization_id,
            preferences,
        )

    # Return masked version of updated config
    masked_config = mask_user_config(user_configurations)
    if user.selected_organization_id:
        preferences = await get_organization_preferences(user.selected_organization_id)
        if preferences.test_phone_number is not None:
            masked_config["test_phone_number"] = preferences.test_phone_number
        if preferences.timezone is not None:
            masked_config["timezone"] = preferences.timezone

    # Add organization pricing info if available
    if user.selected_organization_id:
        org = await db_client.get_organization_by_id(user.selected_organization_id)
        if org and org.price_per_second_usd is not None:
            masked_config["organization_pricing"] = {
                "price_per_second_usd": org.price_per_second_usd,
                "currency": "USD",
                "billing_enabled": True,
            }

    return masked_config


@router.get("/onboarding-state")
async def get_user_onboarding_state(
    user: UserModel = Depends(get_user),
) -> OnboardingState:
    return await get_onboarding_state(user.id)


@router.put("/onboarding-state")
async def update_user_onboarding_state(
    request: OnboardingStateUpdate,
    user: UserModel = Depends(get_user),
) -> OnboardingState:
    return await update_onboarding_state(user.id, request)


@router.get("/configurations/user/validate")
async def validate_user_configurations(
    validity_ttl_seconds: int = Query(default=60, ge=0, le=86400),
    user: UserModel = Depends(get_user),
) -> APIKeyStatusResponse:
    resolved_config = await get_resolved_ai_model_configuration(
        organization_id=user.selected_organization_id,
    )
    configurations = resolved_config.effective

    if _is_validation_cache_stale(
        configurations.last_validated_at,
        validity_ttl_seconds,
    ):
        validator = UserConfigurationValidator()
        try:
            status = await validator.validate(
                configurations,
                organization_id=user.selected_organization_id,
                created_by=user.provider_id,
            )
            if (
                resolved_config.source == "organization_v2"
                and user.selected_organization_id is not None
            ):
                await update_organization_ai_model_configuration_last_validated_at(
                    user.selected_organization_id
                )
            return status
        except ValueError as e:
            raise HTTPException(status_code=422, detail=e.args[0])
    else:
        return {"status": []}


# API Key Management Endpoints
class APIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


class CreateAPIKeyRequest(BaseModel):
    name: str


class CreateAPIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    api_key: str  # Only returned when creating a new key
    created_at: datetime


@router.get("/api-keys")
async def get_api_keys(
    include_archived: bool = Query(default=False),
    user: UserModel = Depends(get_user),
) -> List[APIKeyResponse]:
    """Get all API keys for the user's selected organization."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    api_keys = await db_client.get_api_keys_by_organization(
        user.selected_organization_id, include_archived=include_archived
    )

    return [
        APIKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            is_active=key.is_active,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            archived_at=key.archived_at,
        )
        for key in api_keys
    ]


@router.post("/api-keys")
async def create_api_key(
    request: CreateAPIKeyRequest,
    user: UserModel = Depends(get_user),
) -> CreateAPIKeyResponse:
    """Create a new API key for the user's selected organization."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    api_key, raw_key = await db_client.create_api_key(
        organization_id=user.selected_organization_id,
        name=request.name,
        created_by=user.id,
    )

    return CreateAPIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        api_key=raw_key,
        created_at=api_key.created_at,
    )


@router.delete("/api-keys/{api_key_id}")
async def archive_api_key(
    api_key_id: int,
    user: UserModel = Depends(get_user),
) -> dict:
    """Archive an API key (soft delete)."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    # Verify the API key belongs to the user's organization
    api_keys = await db_client.get_api_keys_by_organization(
        user.selected_organization_id, include_archived=True
    )
    if not any(key.id == api_key_id for key in api_keys):
        raise HTTPException(status_code=404, detail="API key not found")

    success = await db_client.archive_api_key(api_key_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to archive API key")

    return {"success": True, "message": "API key archived successfully"}


@router.put("/api-keys/{api_key_id}/reactivate")
async def reactivate_api_key(
    api_key_id: int,
    user: UserModel = Depends(get_user),
) -> dict:
    """Reactivate an archived API key."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    # Verify the API key belongs to the user's organization
    api_keys = await db_client.get_api_keys_by_organization(
        user.selected_organization_id, include_archived=True
    )
    if not any(key.id == api_key_id for key in api_keys):
        raise HTTPException(status_code=404, detail="API key not found")

    success = await db_client.reactivate_api_key(api_key_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reactivate API key")

    return {"success": True, "message": "API key reactivated successfully"}


# Voice Configuration Endpoints
TTSProvider = Literal[
    "kodewaves",
    "speaches",
    "openai",
    "elevenlabs",
    "cartesia",
    "deepgram",
    "sarvam",
    "navana",
    "google",
    "gemini",
    "azure",
    "azure_speech",
    "smallest",
    "rime",
    "lmnt",
    "speechify",
    "inworld",
    "camb",
    "minimax",
    "xai",
    "speaches",
    "piper",
    "dograh",
    "all",
    "auto",
]


UNIVERSAL_VOICE_CATALOG: dict[str, list[dict]] = {
    "speaches": [
        {"voice_id": "hf_alpha", "name": "Alpha (Hindi Female, Kokoro)", "description": "Local Kokoro ONNX Hindi voice.", "gender": "female", "accent": "in", "language": "hi", "provider": "speaches"},
        {"voice_id": "af_heart", "name": "Heart (US English Female, Kokoro)", "description": "Local Kokoro ONNX English voice; American accent.", "gender": "female", "accent": "us", "language": "en", "provider": "speaches"},
    ],
    "piper": [
        {"voice_id": "hi_IN-priyamvada-medium", "name": "Priyamvada (Hindi Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "in", "language": "hi"},
        {"voice_id": "hi_IN-pratham-medium", "name": "Pratham (Hindi Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "in", "language": "hi"},
        {"voice_id": "hi_IN-rohan-medium", "name": "Rohan (Hindi Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "in", "language": "hi"},
        {"voice_id": "te_IN-maya-medium", "name": "Maya (Telugu Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "in", "language": "te"},
        {"voice_id": "te_IN-padmavathi-medium", "name": "Padmavathi (Telugu Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "in", "language": "te"},
        {"voice_id": "te_IN-venkatesh-medium", "name": "Venkatesh (Telugu Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "in", "language": "te"},
        {"voice_id": "ml_IN-meera-medium", "name": "Meera (Malayalam Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "in", "language": "ml"},
        {"voice_id": "ml_IN-arjun-medium", "name": "Arjun (Malayalam Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "in", "language": "ml"},
        {"voice_id": "mr_IN-google-medium", "name": "Marathi (Google)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "in", "language": "mr"},
        {"voice_id": "bn_BD-google-medium", "name": "Bengali (Google)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "bd", "language": "bn"},
        {"voice_id": "ne_NP-google-medium", "name": "Nepali (Google)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "np", "language": "ne"},
        {"voice_id": "en_US-lessac-medium", "name": "Lessac (US English Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "en_US-amy-medium", "name": "Amy (US English Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "en_US-ryan-medium", "name": "Ryan (US English Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "en_US-libritts_r-medium", "name": "LibriTTS-R (US English Multi)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "en_GB-alan-medium", "name": "Alan (UK English Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "gb", "language": "en"},
        {"voice_id": "en_GB-alba-medium", "name": "Alba (UK English Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "gb", "language": "en"},
        {"voice_id": "es_ES-davefx-medium", "name": "DaveFX (Spanish Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "es", "language": "es"},
        {"voice_id": "fr_FR-siwis-medium", "name": "Siwis (French Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "fr", "language": "fr"},
        {"voice_id": "de_DE-thorsten-medium", "name": "Thorsten (German Male)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "male", "accent": "de", "language": "de"},
        {"voice_id": "it_IT-paola-medium", "name": "Paola (Italian Female)", "description": "Piper ONNX (OHF-Voice/piper1-gpl), runs locally on CPU.", "gender": "female", "accent": "it", "language": "it"},
    ],
    "openai": [
        {"voice_id": "alloy", "name": "Alloy (Neutral & Balanced)", "description": "Versatile and balanced voice suitable for general conversational agents.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "echo", "name": "Echo (Warm & Grounded)", "description": "Warm, resonant male voice ideal for storytelling and podcasts.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "fable", "name": "Fable (Expressive British)", "description": "Expressive male voice with British accent, great for character dialogue.", "gender": "male", "accent": "gb", "language": "en"},
        {"voice_id": "onyx", "name": "Onyx (Deep & Authoritative)", "description": "Authoritative and decisive male voice for enterprise workflows.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "nova", "name": "Nova (Energetic & Friendly)", "description": "Dynamic, upbeat female voice suitable for sales and engagement.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "shimmer", "name": "Shimmer (Clear & Expressive)", "description": "Bright, clear female tone optimal for educational and support content.", "gender": "female", "accent": "us", "language": "en"},
    ],
    "google": [
        {"voice_id": "Zephyr", "name": "Zephyr (Bright)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Puck", "name": "Puck (Upbeat)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Fenrir", "name": "Fenrir (Excitable)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Leda", "name": "Leda (Youthful)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Orus", "name": "Orus (Firm)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Aoede", "name": "Aoede (Breezy)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Callirrhoe", "name": "Callirrhoe (Easy-going)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Autonoe", "name": "Autonoe (Bright)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Enceladus", "name": "Enceladus (Breathy)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Iapetus", "name": "Iapetus (Clear)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Umbriel", "name": "Umbriel (Easy-going)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Algieba", "name": "Algieba (Smooth)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Despina", "name": "Despina (Smooth)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Erinome", "name": "Erinome (Clear)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Algenib", "name": "Algenib (Gravelly)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Rasalgethi", "name": "Rasalgethi (Informative)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Laomedeia", "name": "Laomedeia (Upbeat)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Achernar", "name": "Achernar (Soft)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Alnilam", "name": "Alnilam (Firm)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Schedar", "name": "Schedar (Even)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Gacrux", "name": "Gacrux (Mature)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Pulcherrima", "name": "Pulcherrima (Forward)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Achird", "name": "Achird (Friendly)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Zubenelgenubi", "name": "Zubenelgenubi (Casual)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Vindemiatrix", "name": "Vindemiatrix (Gentle)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Sadachbia", "name": "Sadachbia (Lively)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Sadaltager", "name": "Sadaltager (Knowledgeable)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Sulafat", "name": "Sulafat (Warm)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Charon", "name": "Charon (Informative)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "male", "accent": "multilingual", "language": "hi"},
        {"voice_id": "Kore", "name": "Kore (Firm)", "description": "Multilingual preset; follows the language of the generated text.", "gender": "female", "accent": "multilingual", "language": "hi"},
    ],
    "azure": [
        {"voice_id": "en-US-JennyNeural", "name": "Jenny (Natural Conversational)", "description": "Fluid, natural-sounding American female neural voice.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "en-US-GuyNeural", "name": "Guy (Casual American)", "description": "Friendly, relaxed American male voice for casual conversations.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "en-US-AriaNeural", "name": "Aria (Expressive Multipurpose)", "description": "Expressive American female voice suitable for customer assistance.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "en-IN-NeerjaNeural", "name": "Neerja (Indian English Professional)", "description": "Clear Indian English female accent for domestic customer service.", "gender": "female", "accent": "in", "language": "en"},
        {"voice_id": "en-IN-PrabhatNeural", "name": "Prabhat (Indian English Male)", "description": "Professional Indian English male voice for banking and finance.", "gender": "male", "accent": "in", "language": "en"},
        {"voice_id": "hi-IN-SwaraNeural", "name": "Swara (Hindi Neural)", "description": "Native Hindi female voice with authentic pronunciation and tone.", "gender": "female", "accent": "in", "language": "hi"},
    ],
    "elevenlabs": [
        {"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel (Calm & Professional)", "description": "Clear, gentle, and polished American female voice.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Deep & Versatile)", "description": "Deep, smooth male voice excellent for professional narration.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Warm & Friendly)", "description": "Crisp, trustworthy young male voice for commercial outreach.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella (Bubbly & Engaging)", "description": "Bright, energetic female voice great for sales and gaming.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi (Confident & Strong)", "description": "Strong female voice suited for training and instructions.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli (Soft & Sincere)", "description": "Gentle, emotional tone for counseling and wellness.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh (Conversational)", "description": "Casual, young American male voice for everyday chat.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam (Dynamic & Resonant)", "description": "Confident and dynamic voice for business pitches.", "gender": "male", "accent": "us", "language": "en"},
    ],
    "cartesia": [
        {"voice_id": "sonic-english", "name": "Sonic English (Ultra Low Latency)", "description": "Sub-100ms ultra low-latency conversational speech voice.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "sonic-multilingual", "name": "Sonic Multilingual", "description": "Low-latency multilingual voice spanning English, Spanish, and French.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "barbershop-man", "name": "Barbershop Man (Warm Baritone)", "description": "Warm, expressive baritone tone for friendly customer service.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "helpful-woman", "name": "Helpful Woman (Clear Support)", "description": "Clear, crisp support persona for telephony IVR systems.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "friendly-reading-man", "name": "Friendly Reading Man", "description": "Engaging narrator tone for long-form answers and explanations.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "brooke", "name": "Brooke (Youthful & Upbeat)", "description": "Upbeat young female voice for lead qualification and marketing.", "gender": "female", "accent": "us", "language": "en"},
    ],
    "sarvam": [
        {"voice_id": "arvind", "name": "Arvind (Indian English / Hindi Male)", "description": "Natural Indian male accent with fluent Hindi and English support.", "gender": "male", "accent": "in", "language": "hi"},
        {"voice_id": "amol", "name": "Amol (Business Indian Male)", "description": "Corporate Indian male voice suited for banking and fintech calls.", "gender": "male", "accent": "in", "language": "hi"},
        {"voice_id": "amrita", "name": "Amrita (Warm Indian Female)", "description": "Warm, polite Indian female voice ideal for customer care.", "gender": "female", "accent": "in", "language": "hi"},
        {"voice_id": "ananya", "name": "Ananya (Youthful Indian Female)", "description": "Energetic Indian female voice for outbound campaigns and surveys.", "gender": "female", "accent": "in", "language": "hi"},
        {"voice_id": "aditi", "name": "Aditi (Fluent Multilingual Female)", "description": "Supports seamless code-switching across Hindi, English, and regional dialects.", "gender": "female", "accent": "in", "language": "hi"},
        {"voice_id": "abhinav", "name": "Abhinav (Clear Articulation Male)", "description": "Crisp, authoritative Indian male voice for verification and OTP calls.", "gender": "male", "accent": "in", "language": "hi"},
    ],
    "navana": [
        {"voice_id": "hi-female-1", "name": "Navana Hindi Female (8kHz Telephony)", "description": "Acoustically optimized for Indian telephony networks and noisy lines.", "gender": "female", "accent": "in", "language": "hi"},
        {"voice_id": "hi-male-1", "name": "Navana Hindi Male (8kHz Telephony)", "description": "Robust Indian male telephony voice for debt collection and alerts.", "gender": "male", "accent": "in", "language": "hi"},
        {"voice_id": "te-female-1", "name": "Navana Telugu Female", "description": "Natural Telugu regional female voice for southern India customer support.", "gender": "female", "accent": "in", "language": "te"},
        {"voice_id": "kn-female-1", "name": "Navana Kannada Female", "description": "Authentic Kannada female voice tuned for conversational assistance.", "gender": "female", "accent": "in", "language": "kn"},
        {"voice_id": "mr-female-1", "name": "Navana Marathi Female", "description": "Native Marathi female voice with crisp regional pronunciation.", "gender": "female", "accent": "in", "language": "mr"},
    ],
    "smallest": [
        {"voice_id": "emily", "name": "Emily (Lightning Low-Latency)", "description": "High-velocity streaming voice with sub-80ms first-chunk response.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "arman", "name": "Arman (Indian Conversational)", "description": "Fast-paced Indian conversational male voice for interactive workflows.", "gender": "male", "accent": "in", "language": "en"},
        {"voice_id": "samantha", "name": "Samantha (Support Specialist)", "description": "Crisp and helpful persona for automated phone answering.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "raj", "name": "Raj (Fintech Telephony)", "description": "Clear male voice designed for transactional verification calls.", "gender": "male", "accent": "in", "language": "hi"},
    ],
    "lmnt": [
        {"voice_id": "lily", "name": "Lily (Natural Conversational)", "description": "Expressive American female voice for responsive dialogue.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "daniel", "name": "Daniel (Corporate Presenter)", "description": "Clean, engaging male presenter voice for sales automation.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "zoe", "name": "Zoe (Casual Assistant)", "description": "Upbeat and friendly assistant voice for daily check-ins.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "miles", "name": "Miles (Smooth Narrator)", "description": "Calm, rich baritone voice for audio guidance.", "gender": "male", "accent": "us", "language": "en"},
    ],
    "rime": [
        {"voice_id": "abbie", "name": "Abbie (Young Conversational)", "description": "Modern conversational female voice with natural inflection.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "allison", "name": "Allison (Warm Guide)", "description": "Warm, reassuring guide for patient intake and support.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "ali", "name": "Ali (Direct Professional)", "description": "Professional, no-nonsense tone for transactional notifications.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "antony", "name": "Antony (Smooth Operator)", "description": "Engaging conversational male voice with high audio clarity.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "arch", "name": "Arch (Authoritative Advisor)", "description": "Deep and experienced male voice for consultative sales.", "gender": "male", "accent": "us", "language": "en"},
    ],
    "deepgram": [
        {"voice_id": "aura-asteria-en", "name": "Asteria (Conversational Female)", "description": "Low-latency Deepgram Aura female voice for instant telephony responses.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "aura-luna-en", "name": "Luna (Warm Support)", "description": "Gentle, friendly female tone with expressive pitch range.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "aura-stella-en", "name": "Stella (Energetic Engagement)", "description": "Upbeat and positive female voice for lead qualification.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "aura-athena-en", "name": "Athena (Clear Articulation)", "description": "Polished corporate voice designed for high-clarity IVRs.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "aura-orion-en", "name": "Orion (Authoritative Male)", "description": "Calm and commanding male voice for security alerts.", "gender": "male", "accent": "us", "language": "en"},
    ],
}

# Annotate each voice with its originating provider
for prov_key, voice_list in UNIVERSAL_VOICE_CATALOG.items():
    for voice_item in voice_list:
        if "provider" not in voice_item:
            voice_item["provider"] = prov_key

# Build the complete universal catalog across all cloud & local providers
MANAGED_UNIVERSAL_VOICES: list[dict] = []
for p_key in ["elevenlabs", "cartesia", "openai", "deepgram", "google", "azure", "sarvam", "navana", "speaches", "piper", "smallest", "lmnt", "rime"]:
    if p_key in UNIVERSAL_VOICE_CATALOG:
        for v in UNIVERSAL_VOICE_CATALOG[p_key]:
            MANAGED_UNIVERSAL_VOICES.append(v)

# Alias mirror providers to primary catalog entries
GEMINI_TTS_LANGUAGE_TAGS = [
    "de-DE", "en-US", "es-ES", "fr-FR", "hi-IN", "it-IT", "ja-JP",
    "nl-NL", "pt-BR", "ru-RU",
]
for gemini_voice in UNIVERSAL_VOICE_CATALOG["google"]:
    # Gemini's prebuilt IDs are vocal style presets. The spoken language comes
    # from the generated transcript, so do not label them as US-English voices.
    gemini_voice["language"] = "multi"
    gemini_voice["languages"] = GEMINI_TTS_LANGUAGE_TAGS

UNIVERSAL_VOICE_CATALOG["gemini"] = UNIVERSAL_VOICE_CATALOG["google"]
UNIVERSAL_VOICE_CATALOG["azure_speech"] = UNIVERSAL_VOICE_CATALOG["azure"]
UNIVERSAL_VOICE_CATALOG["kodewaves"] = MANAGED_UNIVERSAL_VOICES
UNIVERSAL_VOICE_CATALOG["dograh"] = MANAGED_UNIVERSAL_VOICES
UNIVERSAL_VOICE_CATALOG["all"] = MANAGED_UNIVERSAL_VOICES


class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    description: Optional[str] = None
    accent: Optional[str] = None
    gender: Optional[str] = None
    language: Optional[str] = None
    languages: Optional[List[str]] = None
    preview_url: Optional[str] = None
    provider: Optional[str] = None


class VoiceFacets(BaseModel):
    """Distinct selector values across a provider's full voice catalog."""

    genders: List[str] = []
    accents: List[str] = []
    languages: List[str] = []
    providers: List[str] = []


class VoicesResponse(BaseModel):
    provider: str
    voices: List[VoiceInfo]
    facets: Optional[VoiceFacets] = None


@router.get("/configurations/voices/{provider}")
async def get_voices(
    provider: str,
    model: Optional[str] = None,
    language: Optional[str] = None,
    q: Optional[str] = None,
    gender: Optional[str] = None,
    accent: Optional[str] = None,
    provider_filter: Optional[str] = None,
    user: UserModel = Depends(get_user),
) -> VoicesResponse:
    """Get available voices for a TTS provider with strict master key filtering and preview URLs."""
    provider_key = provider.lower().strip()
    managed_selection = provider_key in ("kodewaves", "dograh", "all", "auto")
    from api.services.catalog.normalize import normalize_provider_name
    from api.services.catalog.voice_selection import model_voice_ids
    model = model if model not in ("auto", "default", "") else None
    if model and provider_key in ("kodewaves", "dograh", "all", "auto"):
        models = await kodewaves_db_client.list_models(enabled_only=True)
        matches = [entry for entry in models
                   if (entry.layer or entry.category) == "tts" and entry.model_identifier == model
                   and getattr(entry, "status", None) not in ("FAIL", "UNAVAILABLE")]
        providers = {
            "gemini" if str(entry.provider).lower().strip() == "gemini"
            else normalize_provider_name(entry.provider)
            for entry in matches
        }
        if len(providers) != 1:
            raise HTTPException(status_code=400, detail="Select an available TTS provider and model")
        provider_key = providers.pop()

    # Determine active providers with master keys
    local_ai_setting = await kodewaves_db_client.get_setting("local_ai") or {}
    local_engine_enabled = bool(local_ai_setting.get("enable_local_ai_engine", False))
    organization_id = user.selected_organization_id
    if organization_id:
        policy = await kodewaves_db_client.get_org_ai_policy(organization_id)
        local_engine_enabled = local_engine_enabled and (policy.local_allowed if policy else True)
        if local_ai_setting.get("local_ai_access_policy", "public") not in ("public", "all_workspaces"):
            access = await kodewaves_db_client.get_setting(f"local_ai_org_{organization_id}") or {}
            local_engine_enabled = local_engine_enabled and bool(access.get("enabled", False))
    else:
        local_engine_enabled = False

    enabled_provs = set()
    if local_engine_enabled:
        enabled_provs.add("speaches")
        enabled_provs.add("piper")

    for p in ["elevenlabs", "cartesia", "openai", "deepgram", "google", "gemini", "azure", "azure_speech", "sarvam", "navana", "smallest", "lmnt", "rime"]:
        try:
            creds = await master_credential_service.get_master_credential(p)
            if creds and (creds.get("api_key") or creds.get("auth_token")):
                enabled_provs.add(p)
                if p in ("google", "gemini"):
                    enabled_provs.add("google")
                    enabled_provs.add("gemini")
                if p in ("azure", "azure_speech"):
                    enabled_provs.add("azure")
                    enabled_provs.add("azure_speech")
        except Exception:
            pass

    # Fetch voice catalog from Database Truth Layer (voice_catalog table)
    norm_key = "google" if provider_key == "google" else ("azure" if provider_key == "azure_speech" else ("navana" if provider_key == "bodhi" else provider_key))
    db_voices = await kodewaves_db_client.list_voices(
        provider=None if provider_key in ("kodewaves", "dograh", "all", "auto") else norm_key,
        tts_model=model,
        language=language,
    )

    if provider_key == "speaches" and model and model != "piper" and not model.startswith("piper/"):
        raw_catalog = []
        whisper_endpoint = local_ai_setting.get("whisper_endpoint") or os.environ.get("WHISPER_ENDPOINT", "http://whisper:8000/v1")
        from api.services.catalog.local_inventory import whisper_api_base, local_tts_inventory, local_model_voice_catalog
        whisper_base = whisper_api_base(normalize_local_ai_endpoint(whisper_endpoint))
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get(f"{whisper_base.rstrip('/')}/models") as response:
                    payload = await response.json() if response.status == 200 else {}
            installed_model = local_tts_inventory(payload).get(model)
            if local_engine_enabled and installed_model:
                raw_catalog = local_model_voice_catalog(installed_model)
        except Exception:
            raw_catalog = []
    elif db_voices:
        raw_catalog = [
            {
                "voice_id": v.voice_id,
                "name": v.name,
                "gender": v.gender,
                "accent": "in" if (v.provider == "gemini" and v.languages
                                     and len(v.languages) == 1
                                     and v.languages[0].lower().endswith("-in")) else None,
                "language": (
                    "multi" if norm_key == "google" or len(v.languages or []) > 1
                    else (v.languages[0] if v.languages else "en-US")
                ),
                "languages": list(v.languages or []),
                "provider": v.provider,
                "preview_url": v.preview_url or f"/api/v1/user/configurations/voices/{v.provider}/{v.voice_id}/preview",
            }
            for v in db_voices
            if (provider_key in ("kodewaves", "dograh", "all", "auto") and v.provider in enabled_provs)
            or (v.provider in (norm_key, provider_key))
        ]
    elif provider_key in ("kodewaves", "dograh", "all", "auto"):
        raw_catalog = [dict(v) for v in MANAGED_UNIVERSAL_VOICES]
        raw_catalog = [v for v in raw_catalog if v.get("provider") in enabled_provs]
    elif provider_key in ("speaches", "piper"):
        # Piper Native Hindi & Indic ONNX Local CPU engine
        local_catalog = UNIVERSAL_VOICE_CATALOG.get("piper") or []
        raw_catalog = [dict(v) for v in local_catalog]
    else:
        raw_catalog = [dict(v) for v in (UNIVERSAL_VOICE_CATALOG.get(norm_key) or UNIVERSAL_VOICE_CATALOG.get(provider_key) or [])]
        if not raw_catalog:
            raw_catalog = [dict(v) for v in MANAGED_UNIVERSAL_VOICES if v.get("provider") in (norm_key, provider_key)]

    if managed_selection:
        raw_catalog = [voice for voice in raw_catalog if voice.get("provider") in enabled_provs]
        if norm_key not in ("kodewaves", "dograh", "all", "auto") and norm_key not in enabled_provs:
            return VoicesResponse(provider=provider, voices=[], facets=VoiceFacets())

    allowed_voice_ids = model_voice_ids(norm_key, model)
    if allowed_voice_ids is not None:
        raw_catalog = [voice for voice in raw_catalog if voice["voice_id"] in allowed_voice_ids]
        if not raw_catalog:
            raw_catalog = [{"voice_id": voice_id, "name": voice_id, "provider": norm_key}
                           for voice_id in sorted(allowed_voice_ids)]

    # Local voices must be installed: Piper otherwise silently uses its default voice.
    if any(v.get("provider", "piper") == "piper" for v in raw_catalog):
        from api.services.catalog.local_inventory import get_installed_piper_voices
        endpoint = local_ai_setting.get("piper_endpoint") or os.environ.get("PIPER_ENDPOINT", "http://piper:5000")
        try:
            installed = await get_installed_piper_voices(normalize_local_ai_endpoint(endpoint))
        except Exception:
            installed = {}
        raw_catalog = [
            v for v in raw_catalog
            if v.get("provider", "piper") not in ("piper", "speaches")
            or (local_engine_enabled and v["voice_id"] in installed)
        ]

    # Annotate with working preview URL
    for v in raw_catalog:
        v_prov = v.get("provider", "speaches")
        v["preview_url"] = f"/api/v1/user/configurations/voices/{v_prov}/{v['voice_id']}/preview"
        if model:
            v["preview_url"] += "?" + urlencode({"model": model})

    filtered = raw_catalog
    if provider_filter and provider_filter != "__all__":
        pf = provider_filter.lower()
        if pf in ("azure", "azure_speech"):
            filtered = [v for v in filtered if v.get("provider") in ("azure", "azure_speech")]
        elif pf in ("google", "gemini"):
            filtered = [v for v in filtered if v.get("provider") in ("google", "gemini")]
        else:
            filtered = [v for v in filtered if v.get("provider") == pf]
    if gender and gender != "__all__":
        filtered = [v for v in filtered if v.get("gender") == gender]
    if accent and accent != "__all__":
        filtered = [v for v in filtered if v.get("accent") == accent]
    if language and language != "__all__":
        language_key = language.lower().replace("_", "-")
        filtered = [
            v for v in filtered
            if any(
                str(candidate).lower().replace("_", "-").split("-")[0]
                == language_key.split("-")[0]
                for candidate in (v.get("languages") or [v.get("language")])
                if candidate
            )
        ]
    if q and q.strip():
        ql = q.strip().lower()
        filtered = [
            v for v in filtered
            if ql in v["name"].lower()
            or ql in v["voice_id"].lower()
            or ql in (v.get("description") or "").lower()
            or ql in (v.get("provider") or "").lower()
        ]

    # Calculate facets dynamically from active provider catalog
    genders = sorted(list({v.get("gender") for v in raw_catalog if v.get("gender")}))
    accents = sorted(list({v.get("accent") for v in raw_catalog if v.get("accent")}))
    languages = sorted({
        candidate
        for voice in raw_catalog
        for candidate in (voice.get("languages") or [voice.get("language")])
        if candidate
    })
    providers_list = sorted(list({v.get("provider") for v in raw_catalog if v.get("provider")}))

    return VoicesResponse(
        provider=provider,
        voices=[VoiceInfo(**v) for v in filtered],
        facets=VoiceFacets(
            genders=genders,
            accents=accents,
            languages=languages,
            providers=providers_list,
        ),
    )


async def _resolve_tts_preview_creds(provider_alias: str, user, db_client) -> dict:
    from api.services.catalog.normalize import normalize_provider_name
    from api.services.configuration.ai_model_configuration import get_organization_ai_model_configuration_v2

    provider = normalize_provider_name(provider_alias)
    byok_policy = await kodewaves_db_client.get_setting("byok_policy") or {}
    if byok_policy.get("allow_user_byok", True):
        configuration = await get_organization_ai_model_configuration_v2(user.selected_organization_id)
        if configuration and configuration.mode == "byok" and configuration.byok:
            pipeline = configuration.byok.pipeline
            tts = pipeline.tts if pipeline else None
            if tts and normalize_provider_name(getattr(tts.provider, "value", tts.provider)) == provider and tts.api_key:
                result = {"api_key": tts.api_key}
                for field in ("region", "base_url"):
                    value = getattr(tts, field, None)
                    if value:
                        result[field] = value
                return result

    # MasterCredentialService enforces administrator disablement and environment policy.
    credentials = await master_credential_service.get_master_credential(provider)
    return credentials or {}


_AUDIO_PREVIEW_CACHE: dict[str, tuple[bytes, str]] = {}


@router.get("/configurations/voices/{provider}/{voice_id}/preview")
async def preview_voice(
    provider: str,
    voice_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    user: UserModel = Depends(get_user),
):
    """Generate a voice preview using the selected organization's authorized provider."""
    provider_lower = provider.lower()
    from api.services.catalog.voice_selection import model_voice_ids
    allowed_voice_ids = model_voice_ids(provider_lower, model)
    if allowed_voice_ids is not None and voice_id not in allowed_voice_ids:
        raise HTTPException(status_code=400, detail="Selected voice is not supported by the selected TTS model")

    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="Select an organization first")

    is_local_model = provider_lower == "speaches" and bool(model) and model != "piper" and not model.startswith("piper/")
    local_voice_metadata = {}
    if provider_lower in ("piper", "speaches"):
        from api.services.catalog.catalog_service import catalog_service
        catalog = await catalog_service.get_available_catalog(
            organization_id=user.selected_organization_id,
            user_has_local_ai=bool(getattr(user, "has_local_ai_access", False)),
        )
        if not catalog.get("local_engine_enabled"):
            raise HTTPException(status_code=403, detail="Local AI is disabled or unavailable for this organization")
        settings = await kodewaves_db_client.get_setting("local_ai") or {}
        if is_local_model:
            from api.services.catalog.local_inventory import whisper_api_base, local_tts_inventory, local_model_voice_ids
            endpoint = settings.get("whisper_endpoint") or os.environ.get("WHISPER_ENDPOINT", "http://whisper:8000/v1")
            speaches_url = whisper_api_base(normalize_local_ai_endpoint(endpoint)).rstrip("/")
            import aiohttp
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    async with session.get(f"{speaches_url}/models") as response:
                        data = await response.json() if response.status == 200 else {}
                installed_model = local_tts_inventory(data).get(model)
                if installed_model is None:
                    raise HTTPException(status_code=400, detail="Selected local TTS model is not installed")
                if voice_id not in local_model_voice_ids(installed_model):
                    raise HTTPException(status_code=400, detail="Selected voice is not supported by the installed local TTS model")
                local_voice_metadata = next((voice for voice in installed_model.get("voices", [])
                    if isinstance(voice, dict) and (voice.get("id") or voice.get("voice_id") or voice.get("name")) == voice_id), {})
            except (aiohttp.ClientError, TimeoutError):
                raise HTTPException(status_code=503, detail="Unable to verify installed local TTS model")
        else:
            from api.services.catalog.local_inventory import get_installed_piper_voices
            endpoint = settings.get("piper_endpoint") or os.environ.get("PIPER_ENDPOINT", "http://piper:5000")
            piper_url = normalize_local_ai_endpoint(endpoint).rstrip("/").removesuffix("/synthesize")
            try:
                installed = await get_installed_piper_voices(piper_url)
            except Exception:
                raise HTTPException(status_code=503, detail="Unable to verify installed local voices")
            if voice_id not in installed:
                raise HTTPException(status_code=400, detail="Selected local voice is not installed; ask the administrator to install it")
    elif not await _resolve_tts_preview_creds(provider_lower, user, db_client):
        raise HTTPException(status_code=400, detail="No active credentials for the selected voice provider")

    cache_key = f"{user.selected_organization_id}:{provider_lower}:{model or 'default'}:{voice_id}:{language or 'default'}"
    if cache_key in _AUDIO_PREVIEW_CACHE:
        cached_bytes, cached_mime = _AUDIO_PREVIEW_CACHE[cache_key]
        return Response(content=cached_bytes, media_type=cached_mime,
                        headers={"Cache-Control": "private, no-store"})

    import aiohttp

    def _cache_and_respond(audio_bytes: bytes, mime_type: str) -> Response:
        if len(_AUDIO_PREVIEW_CACHE) < 500:
            _AUDIO_PREVIEW_CACHE[cache_key] = (audio_bytes, mime_type)
        return Response(
            content=audio_bytes,
            media_type=mime_type,
            headers={"Cache-Control": "private, no-store"},
        )

    # 0. Piper ONNX (OHF-Voice/piper1-gpl HTTP server, local CPU)
    if is_local_model:
        samples = {
            "en": "Hello, welcome to Kodewaves. How may I help you?",
            "hi": "नमस्ते, मैं आपकी कैसे मदद कर सकती हूँ?",
            "fr": "Bonjour, comment puis-je vous aider ?",
            "es": "Hola, ¿cómo puedo ayudarte?",
            "pt": "Olá, como posso ajudar?",
            "it": "Ciao, come posso aiutarti?",
            "ja": "こんにちは。どのようにお手伝いできますか？",
            "zh": "你好，我能帮你什么？",
        }
        voice_language = local_voice_metadata.get("language") or language or ""
        if not isinstance(voice_language, str):
            voice_language = ""
        text = local_voice_metadata.get("preview_text") or samples.get(voice_language.lower().split("-")[0])
        if not text:
            raise HTTPException(status_code=400, detail="The installed voice does not advertise a preview text for its language")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.post(f"{speaches_url}/audio/speech", json={
                    "model": model, "voice": voice_id, "input": text, "response_format": "wav",
                }) as response:
                    if response.status == 200:
                        return _cache_and_respond(await response.read(), "audio/wav")
        except Exception as error:
            logger.warning("Local model voice preview failed: {}", type(error).__name__)
        raise HTTPException(status_code=503, detail="Local voice synthesis failed")
    if provider_lower in ("piper", "speaches"):
        samples = {
            "hi": "नमस्ते, कोडवेव्स में आपका स्वागत है।",
            "mr": "नमस्कार, कोडवेव्स मध्ये आपले स्वागत आहे.",
            "te": "నమస్కారం, కోడ్‌వేవ్స్‌కు స్వాగతం.",
            "ml": "നമസ്കാരം, കോഡ്‌വേവ്സിലേക്ക് സ്വാഗതം.",
            "ne": "नमस्कार, कोडवेभ्समा तपाईंलाई स्वागत छ।",
        }
        text = samples.get(voice_id.split("_")[0], "Hello from Kodewaves.")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.post(f"{piper_url}/synthesize", json={"text": text, "voice": voice_id}) as response:
                    if response.status == 200:
                        return _cache_and_respond(await response.read(), "audio/wav")
        except Exception as error:
            logger.warning("Local voice preview failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Local voice synthesis failed")

    # 1. Sarvam Indic (Hindi)
    if provider_lower == "sarvam":
        creds = await _resolve_tts_preview_creds("sarvam", user, db_client)
        if creds.get("api_key"):
            try:
                headers = {"api-subscription-key": creds["api_key"]}
                payload = {
                    "inputs": ["नमस्ते, यह कोडवेव्स पर आवाज का पूर्वावलोकन है।"],
                    "target_language_code": "hi-IN",
                    "speaker": voice_id,
                    "model": model or "bulbul:v3",
                }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post("https://api.sarvam.ai/text-to-speech", json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            audios = data.get("audios", [])
                            if audios:
                                import base64
                                audio_bytes = base64.b64decode(audios[0])
                                return _cache_and_respond(audio_bytes, "audio/wav")
            except Exception as e:
                logger.warning(f"[VoicePreview] Sarvam preview failed: {e}")

    # 2. Cartesia
    if provider_lower == "cartesia":
        creds = await _resolve_tts_preview_creds("cartesia", user, db_client)
        if creds.get("api_key"):
            try:
                headers = {
                    "X-API-Key": creds["api_key"],
                    "Cartesia-Version": "2024-06-10",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model_id": model or "sonic-3.5",
                    "transcript": "Hello, this is a live preview of this voice on Kodewaves.",
                    "voice": {"mode": "id", "id": voice_id},
                    "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 24000},
                }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post("https://api.cartesia.ai/tts/bytes", json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            return _cache_and_respond(audio_data, "audio/wav")
            except Exception as e:
                logger.warning(f"[VoicePreview] Cartesia preview failed: {e}")

    # 3. OpenAI
    if provider_lower == "openai":
        creds = await _resolve_tts_preview_creds("openai", user, db_client)
        if creds.get("api_key"):
            try:
                headers = {"Authorization": f"Bearer {creds['api_key']}", "Content-Type": "application/json"}
                payload = {"model": model or "tts-1", "voice": voice_id, "input": "Hello, this is a sample preview on Kodewaves."}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post("https://api.openai.com/v1/audio/speech", json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            return _cache_and_respond(audio_data, "audio/mpeg")
            except Exception as e:
                logger.warning(f"[VoicePreview] OpenAI preview failed: {e}")

    # 4. ElevenLabs
    if provider_lower == "elevenlabs":
        creds = await _resolve_tts_preview_creds("elevenlabs", user, db_client)
        if creds.get("api_key"):
            try:
                headers = {"xi-api-key": creds["api_key"], "Content-Type": "application/json"}
                payload = {"text": "Hello, this is a sample preview on Kodewaves.", "model_id": model or "eleven_multilingual_v2"}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            return _cache_and_respond(audio_data, "audio/mpeg")
            except Exception as e:
                logger.warning(f"[VoicePreview] ElevenLabs preview failed: {e}")

    # 5. Google / Gemini
    if provider_lower in ("google", "gemini"):
        selected_model = model or "gemini-3.8-flash-lite-tts"
        credential_provider = "gemini" if selected_model.startswith("gemini-") else "google"
        creds = await _resolve_tts_preview_creds(credential_provider, user, db_client)
        api_key = creds.get("api_key")
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Google Gemini API key not found. Please add your GEMINI_API_KEY in Admin > Models or Workspace Settings to preview Gemini voices.",
            )

        gemini_voice = voice_id

        candidate_endpoints = [selected_model]
        language_code = (language or "en").lower().replace("_", "-").split("-")[0]
        preview_texts = {
            "de": "Guten Tag. Dies ist eine natürliche Sprachprobe.",
            "en": "Hello, this is a natural and conversational voice sample.",
            "es": "Hola. Esta es una muestra de voz natural y conversacional.",
            "fr": "Bonjour. Voici un échantillon de voix naturel et conversationnel.",
            "hi": "नमस्ते। यह एक स्वाभाविक और बातचीत जैसी आवाज़ का नमूना है।",
            "it": "Ciao. Questo è un esempio di voce naturale e colloquiale.",
            "ja": "こんにちは。自然で会話らしい音声サンプルです。",
            "nl": "Hallo. Dit is een natuurlijk en gesprekachtig stemvoorbeeld.",
            "pt": "Olá. Esta é uma amostra de voz natural e conversacional.",
            "ru": "Здравствуйте. Это естественный разговорный образец голоса.",
        }
        preview_text = preview_texts.get(language_code, preview_texts["en"])
        last_error = "Unknown error"
        for mdl in candidate_endpoints:
            try:
                method = "streamGenerateContent" if mdl.startswith("gemini-3.8-") else "generateContent"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:{method}"
                if method == "streamGenerateContent":
                    url += "?alt=sse"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                }
                if mdl.startswith("gemini-3.8-"):
                    payload = {
                        "contents": [{"role": "user", "parts": [{
                            "text": preview_text,
                            "speech_metadata": {
                                "style": "natural, relaxed conversational delivery with clear articulation"
                            },
                        }]}],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "responseFormat": {"audio": {"mimeType": "AUDIO_L16", "sampleRate": 24000}},
                            "speechConfig": {"voiceConfig": {"voice": gemini_voice}},
                        },
                    }
                else:
                    payload = {
                        "contents": [{"parts": [{"text": preview_text}]}],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {
                                "voiceConfig": {
                                    "prebuiltVoiceConfig": {"voiceName": gemini_voice}
                                }
                            },
                        },
                    }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            import base64
                            import io
                            import json
                            import wave

                            if method == "streamGenerateContent":
                                response_data = []
                                async for line in resp.content:
                                    line = line.strip()
                                    if line.startswith(b"data:"):
                                        event_data = line[5:].strip()
                                        if event_data and event_data != b"[DONE]":
                                            try:
                                                response_data.append(json.loads(event_data))
                                            except (json.JSONDecodeError, UnicodeDecodeError):
                                                continue
                            else:
                                response_data = [await resp.json()]
                            pcm_chunks = []
                            for data in response_data:
                                for candidate in data.get("candidates", []):
                                    for part in candidate.get("content", {}).get("parts", []):
                                        inline_data = part.get("inlineData") or part.get("inline_data") or {}
                                        if inline_data.get("data"):
                                            raw_audio = base64.b64decode(inline_data["data"])
                                            mime = inline_data.get("mimeType", "")
                                            if "wav" in mime:
                                                return _cache_and_respond(raw_audio, "audio/wav")
                                            if "mp3" in mime or "mpeg" in mime:
                                                return _cache_and_respond(raw_audio, "audio/mpeg")
                                            if "ogg" in mime or "opus" in mime:
                                                return _cache_and_respond(raw_audio, "audio/ogg")
                                            pcm_chunks.append(raw_audio)
                            if pcm_chunks:
                                wav_buf = io.BytesIO()
                                with wave.open(wav_buf, "wb") as wf:
                                    wf.setnchannels(1)
                                    wf.setsampwidth(2)
                                    wf.setframerate(24000)
                                    wf.writeframes(b"".join(pcm_chunks))
                                return _cache_and_respond(wav_buf.getvalue(), "audio/wav")
                        else:
                            err_body = await resp.text()
                            last_error = f"HTTP {resp.status}: {err_body[:120]}"
                            logger.warning(f"[VoicePreview] Gemini {mdl} returned {resp.status}: {err_body[:120]}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[VoicePreview] Gemini {mdl} preview failed: {e}")

        raise HTTPException(
            status_code=502,
            detail=f"Google Gemini voice preview generation failed: {last_error}",
        )

    # 6. Deepgram Aura
    if provider_lower == "deepgram":
        creds = await _resolve_tts_preview_creds("deepgram", user, db_client)
        if creds.get("api_key"):
            try:
                headers = {
                    "Authorization": f"Token {creds['api_key']}",
                    "Content-Type": "application/json",
                }
                model_name = voice_id if voice_id.startswith("aura-") else f"aura-{voice_id}-en"
                url = f"https://api.deepgram.com/v1/speak?model={model_name}"
                payload = {"text": "Hello, this is a sample preview of Deepgram Aura voice on Kodewaves."}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            return _cache_and_respond(audio_data, "audio/mp3")
            except Exception as e:
                logger.warning(f"[VoicePreview] Deepgram preview failed: {e}")

    # 7. Azure Speech
    if provider_lower in ("azure", "azure_speech"):
        creds = await _resolve_tts_preview_creds("azure", user, db_client)
        if creds.get("api_key"):
            try:
                region = creds.get("region") or os.environ.get("AZURE_SPEECH_REGION", "eastus")
                url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
                headers = {
                    "Ocp-Apim-Subscription-Key": creds["api_key"],
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
                }
                ssml = f"<speak version='1.0' xml:lang='en-US'><voice name='{voice_id}'>Hello, this is a live preview on Kodewaves.</voice></speak>"
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post(url, data=ssml.encode("utf-8"), headers=headers) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            return _cache_and_respond(audio_data, "audio/mpeg")
            except Exception as e:
                logger.warning(f"[VoicePreview] Azure preview failed: {e}")

    raise HTTPException(status_code=404, detail=f"Preview audio unavailable for voice '{voice_id}' on provider '{provider}'")
