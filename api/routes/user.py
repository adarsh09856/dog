import logging
import os
from datetime import datetime, timedelta
from typing import List, Literal, Optional, TypedDict, Union

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
        {"voice_id": "Journey", "name": "Journey (Adaptive Conversational)", "description": "High-fidelity conversational voice with expressive pitch and pace.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "Puck", "name": "Puck (Playful & Quick)", "description": "Lively voice with fast turn-taking capability for interactive bots.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "Charon", "name": "Charon (Calm & Informative)", "description": "Deep, grounded tone perfect for briefings and announcements.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "Aoede", "name": "Aoede (Warm & Melodic)", "description": "Warm female voice tuned for storytelling and guided onboarding.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "Fenrir", "name": "Fenrir (Crisp & Direct)", "description": "Crisp male articulation designed for high intelligibility on telephony.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "Kore", "name": "Kore (Friendly Professional)", "description": "Friendly, modern corporate persona for front-desk reception.", "gender": "female", "accent": "us", "language": "en"},
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

    # Determine active providers with master keys
    local_ai_setting = await kodewaves_db_client.get_setting("local_ai") or {}
    local_engine_enabled = local_ai_setting.get("enable_local_ai_engine", True)

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

    # Fetch voice catalog for the requested provider or all managed voices
    if provider_key in ("kodewaves", "dograh", "all", "auto"):
        raw_catalog = [dict(v) for v in MANAGED_UNIVERSAL_VOICES]
        if enabled_provs:
            raw_catalog = [v for v in raw_catalog if v.get("provider") in enabled_provs]
    elif provider_key in ("speaches", "piper"):
        # Piper Native Hindi & Indic ONNX Local CPU engine
        local_catalog = UNIVERSAL_VOICE_CATALOG.get("piper") or []
        raw_catalog = [dict(v) for v in local_catalog]
    else:
        norm_key = "google" if provider_key == "gemini" else ("azure" if provider_key == "azure_speech" else provider_key)
        raw_catalog = [dict(v) for v in (UNIVERSAL_VOICE_CATALOG.get(norm_key) or UNIVERSAL_VOICE_CATALOG.get(provider_key) or [])]
        if not raw_catalog:
            raw_catalog = [dict(v) for v in MANAGED_UNIVERSAL_VOICES if v.get("provider") in (norm_key, provider_key)]

    # Annotate with working preview URL
    for v in raw_catalog:
        v_prov = v.get("provider", "speaches")
        v["preview_url"] = f"/api/v1/user/configurations/voices/{v_prov}/{v['voice_id']}/preview"

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
        filtered = [v for v in filtered if v.get("language") == language]
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
    languages = sorted(list({v.get("language") for v in raw_catalog if v.get("language")}))
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
    from api.services.credentials.master_credential_service import master_credential_service
    prov = provider_alias.lower().strip()
    if prov == "gemini":
        prov = "google"
    elif prov == "azure_speech":
        prov = "azure"

    for test_key in ([prov, "google", "gemini"] if prov in ("google", "gemini") else [prov]):
        creds = await master_credential_service.get_master_credential(test_key)
        if creds and (creds.get("api_key") or creds.get("apiKey")):
            return {"api_key": creds.get("api_key") or creds.get("apiKey")}

    env_map = {
        "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "deepgram": ["DEEPGRAM_API_KEY"],
        "cartesia": ["CARTESIA_API_KEY"],
        "elevenlabs": ["ELEVENLABS_API_KEY", "XI_API_KEY"],
        "sarvam": ["SARVAM_API_KEY"],
        "azure": ["AZURE_SPEECH_API_KEY", "AZURE_SPEECH_KEY", "AZURE_API_KEY"],
        "azure_speech": ["AZURE_SPEECH_API_KEY", "AZURE_SPEECH_KEY", "AZURE_API_KEY"],
    }
    for env_var in env_map.get(prov, [f"{prov.upper()}_API_KEY"]):
        val = os.environ.get(env_var)
        if val:
            res = {"api_key": val}
            if prov in ("azure", "azure_speech"):
                res["region"] = os.environ.get("AZURE_SPEECH_REGION", "eastus")
            return res

    if user and getattr(user, "selected_organization_id", None):
        try:
            from api.services.configuration.ai_model_configuration import (
                _get_organization_ai_model_configuration_v2_row,
                _parse_organization_ai_model_configuration_v2,
            )
            row = await _get_organization_ai_model_configuration_v2_row(user.selected_organization_id)
            org_cfg = _parse_organization_ai_model_configuration_v2(row, user.selected_organization_id)
            if org_cfg:
                if org_cfg.byok:
                    if org_cfg.byok.pipeline and org_cfg.byok.pipeline.tts:
                        tts_prov = getattr(org_cfg.byok.pipeline.tts, "provider", "").lower()
                        if tts_prov == prov or (prov in ("google", "gemini") and tts_prov in ("google", "gemini")):
                            key = getattr(org_cfg.byok.pipeline.tts, "api_key", None)
                            if key:
                                return {"api_key": key}
                    if org_cfg.byok.pipeline and org_cfg.byok.pipeline.llm:
                        llm_prov = getattr(org_cfg.byok.pipeline.llm, "provider", "").lower()
                        if llm_prov == prov or (prov in ("google", "gemini") and llm_prov in ("google", "gemini")):
                            key = getattr(org_cfg.byok.pipeline.llm, "api_key", None)
                            if key:
                                return {"api_key": key}
                    if org_cfg.byok.realtime and org_cfg.byok.realtime.realtime:
                        rt_prov = getattr(org_cfg.byok.realtime.realtime, "provider", "").lower()
                        if rt_prov == prov or (prov in ("google", "gemini") and rt_prov in ("google", "gemini")):
                            key = getattr(org_cfg.byok.realtime.realtime, "api_key", None)
                            if key:
                                return {"api_key": key}
                k_cfg = org_cfg.kodewaves or org_cfg.dograh
                if k_cfg and k_cfg.api_key and k_cfg.api_key not in ("sovereign-managed", "sovereign-local-cpu"):
                    return {"api_key": k_cfg.api_key}
        except Exception as org_cfg_err:
            logger.debug(f"[VoicePreview] Org config key check failed: {org_cfg_err}")

        try:
            org_keys = await db_client.get_api_keys_by_organization(user.selected_organization_id)
            for ok in org_keys:
                ok_prov = getattr(ok, "provider", "").lower()
                if (
                    ok_prov == prov
                    or (prov in ("google", "gemini") and ok_prov in ("google", "gemini"))
                    or (prov in ("azure", "azure_speech") and ok_prov in ("azure", "azure_speech"))
                ):
                    extra = getattr(ok, "extra", {}) or {}
                    res = {"api_key": getattr(ok, "api_key", None)}
                    if "region" in extra:
                        res["region"] = extra["region"]
                    return res
        except Exception:
            pass

    # Global DB fallback across all orgs (for single-tenant / local deployments)
    try:
        from api.db.models import OrganizationConfigurationModel
        from api.enums import OrganizationConfigurationKey
        from sqlalchemy.future import select
        async with db_client.async_session() as session:
            result = await session.execute(
                select(OrganizationConfigurationModel).where(
                    OrganizationConfigurationModel.key == OrganizationConfigurationKey.MODEL_CONFIGURATION_V2.value
                )
            )
            rows = result.scalars().all()
            for r in rows:
                if not r.value:
                    continue
                from api.services.configuration.ai_model_configuration import _parse_organization_ai_model_configuration_v2
                org_cfg = _parse_organization_ai_model_configuration_v2(r, r.organization_id)
                if not org_cfg:
                    continue
                if org_cfg.byok:
                    for branch in [
                        org_cfg.byok.pipeline.tts if org_cfg.byok.pipeline else None,
                        org_cfg.byok.pipeline.llm if org_cfg.byok.pipeline else None,
                        org_cfg.byok.realtime.realtime if org_cfg.byok.realtime else None,
                    ]:
                        if branch:
                            b_prov = getattr(branch, "provider", "").lower()
                            if b_prov == prov or (prov in ("google", "gemini") and b_prov in ("google", "gemini")):
                                key = getattr(branch, "api_key", None)
                                if key:
                                    return {"api_key": key}
                k_cfg = org_cfg.kodewaves or org_cfg.dograh
                if k_cfg and k_cfg.api_key and k_cfg.api_key not in ("sovereign-managed", "sovereign-local-cpu"):
                    return {"api_key": k_cfg.api_key}
    except Exception as db_fallback_err:
        logger.debug(f"[VoicePreview] Global org config fallback search failed: {db_fallback_err}")

    return {}


_AUDIO_PREVIEW_CACHE: dict[str, tuple[bytes, str]] = {}
_INSTALLED_PIPER_VOICES_CACHE: set[str] = set()


@router.get("/configurations/voices/{provider}/{voice_id}/preview")
async def preview_voice(
    provider: str,
    voice_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    """Generate or stream audio preview for a given voice with in-memory caching for zero latency."""
    provider_lower = provider.lower()

    # Provider auto-correction based on voice signature to prevent cross-engine mismatch
    if voice_id in ("Journey", "Puck", "Charon", "Aoede", "Fenrir", "Kore"):
        provider_lower = "google"
    elif voice_id in ("alloy", "echo", "fable", "onyx", "nova", "shimmer"):
        provider_lower = "openai"
    elif voice_id.startswith("aura-"):
        provider_lower = "deepgram"
    elif voice_id.startswith(("sonic-", "barbershop", "helpful", "friendly", "brooke")):
        provider_lower = "cartesia"
    elif voice_id in ("arvind", "amol", "amrita", "ananya", "aditi", "abhinav", "meera"):
        provider_lower = "sarvam"
    elif voice_id.startswith(("hi-", "te-", "kn-", "mr-")) and "medium" not in voice_id:
        provider_lower = "navana"

    cache_key = f"{provider_lower}:{voice_id}"
    if cache_key in _AUDIO_PREVIEW_CACHE:
        cached_bytes, cached_mime = _AUDIO_PREVIEW_CACHE[cache_key]
        return Response(
            content=cached_bytes,
            media_type=cached_mime,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    user = None
    try:
        if not request.headers.get("authorization") and token:
            user = await get_user(authorization=f"Bearer {token}")
        else:
            user = await get_user(
                authorization=request.headers.get("authorization"),
                x_api_key=request.headers.get("x-api-key"),
                kodewaves_auth_token=request.cookies.get("kodewaves_auth_token"),
                dograh_auth_token=request.cookies.get("dograh_auth_token"),
                oss_token=request.cookies.get("oss_token"),
            )
    except Exception as auth_err:
        logger.debug(f"[VoicePreview] Auth check deferred to DB lookup: {auth_err}")
    import os
    import aiohttp
    from starlette.responses import Response

    def _cache_and_respond(audio_bytes: bytes, mime_type: str) -> Response:
        if len(_AUDIO_PREVIEW_CACHE) < 500:
            _AUDIO_PREVIEW_CACHE[cache_key] = (audio_bytes, mime_type)
        return Response(
            content=audio_bytes,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # 0. Piper ONNX (OHF-Voice/piper1-gpl HTTP server, local CPU)
    if provider_lower in ("piper", "speaches"):
        piper_url = os.environ.get("PIPER_ENDPOINT", "http://piper:5000").rstrip("/")
        lang_prefix = voice_id.split("_")[0]
        # Concise prompt (<4 words) for rapid local CPU synthesis (<200ms)
        samples = {
            "hi": "नमस्ते, कोडवेव्स में आपका स्वागत है।",
            "te": "నమస్కారం, కోడ్‌వేవ్స్‌కు స్వాగతం.",
            "ml": "നമസ്കാരം, കോഡ്‌വേവ്സിലേക്ക് സ്വാഗതം.",
            "mr": "नमस्कार, कोडवेव्स मध्ये आपले स्वागत आहे.",
            "bn": "নমস্কার, কোডওয়েভসে স্বাগতম।",
        }
        text = samples.get(lang_prefix, "Hello from Kodewaves.")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                # Fast path: direct synthesize first
                try:
                    async with session.post(
                        f"{piper_url}/synthesize",
                        json={"text": text, "voice": voice_id},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            return _cache_and_respond(await resp.read(), "audio/wav")
                except Exception:
                    pass

                # Fallback: check installed list or trigger download if missing
                if voice_id not in _INSTALLED_PIPER_VOICES_CACHE:
                    try:
                        async with session.get(f"{piper_url}/voices", timeout=aiohttp.ClientTimeout(total=3)) as vresp:
                            if vresp.status == 200:
                                installed = await vresp.json()
                                _INSTALLED_PIPER_VOICES_CACHE.update(installed.keys() if isinstance(installed, dict) else installed)
                    except Exception:
                        pass

                if voice_id not in _INSTALLED_PIPER_VOICES_CACHE:
                    try:
                        async with session.post(f"{piper_url}/download", json={"voice": voice_id}, timeout=aiohttp.ClientTimeout(total=60)) as dresp:
                            if dresp.status == 200:
                                _INSTALLED_PIPER_VOICES_CACHE.add(voice_id)
                    except Exception as dl_err:
                        logger.warning(f"[VoicePreview] Piper voice check/download failed: {dl_err}")

                async with session.post(f"{piper_url}/synthesize", json={"text": text, "voice": voice_id}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return _cache_and_respond(await resp.read(), "audio/wav")
                    detail = (await resp.text())[:200]
                    logger.warning(f"[VoicePreview] Piper HTTP {resp.status} for {voice_id}: {detail}")
        except Exception as e:
            logger.warning(f"[VoicePreview] Piper server unreachable at {piper_url}: {e}")
        raise HTTPException(status_code=503, detail="Local Piper TTS server is not reachable or voice is not installed")

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
                    "model": "bulbul:v1",
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
                    "model_id": "sonic-3.5",
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
                payload = {"model": "tts-1", "voice": voice_id, "input": "Hello, this is a sample preview on Kodewaves."}
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
                payload = {"text": "Hello, this is a sample preview on Kodewaves.", "model_id": "eleven_multilingual_v2"}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            return _cache_and_respond(audio_data, "audio/mpeg")
            except Exception as e:
                logger.warning(f"[VoicePreview] ElevenLabs preview failed: {e}")

    # 5. Google / Gemini
    if provider_lower in ("google", "gemini"):
        creds = await _resolve_tts_preview_creds("google", user, db_client)
        api_key = creds.get("api_key")
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Google Gemini API key not found. Please add your GEMINI_API_KEY in Admin > Models or Workspace Settings to preview Gemini voices.",
            )

        gemini_voice = {
            "puck": "Puck",
            "charon": "Charon",
            "kore": "Kore",
            "fenrir": "Fenrir",
            "aoede": "Aoede",
            "journey": "Aoede",
            "zephyr": "Zephyr",
            "leda": "Leda",
            "enceladus": "Enceladus",
        }.get(voice_id.lower(), voice_id if voice_id in ("Puck", "Charon", "Aoede", "Fenrir", "Kore", "Zephyr") else "Puck")

        candidate_endpoints = [
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-flash-preview-tts",
            "gemini-2.0-flash",
            "gemini-2.5-flash",
        ]
        last_error = "Unknown error"
        for mdl in candidate_endpoints:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={api_key}"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                }
                payload = {
                    "contents": [{"parts": [{"text": "Hello! This is a live preview of this Gemini voice on Kodewaves."}]}],
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": gemini_voice
                                }
                            }
                        }
                    }
                }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for part in parts:
                                    inline_data = part.get("inlineData", {})
                                    if inline_data.get("data"):
                                        import base64
                                        import io
                                        import wave
                                        raw_audio = base64.b64decode(inline_data["data"])
                                        mime = inline_data.get("mimeType", "")
                                        if "wav" in mime:
                                            return _cache_and_respond(raw_audio, "audio/wav")
                                        elif "mp3" in mime or "mpeg" in mime:
                                            return _cache_and_respond(raw_audio, "audio/mpeg")
                                        elif "ogg" in mime or "opus" in mime:
                                            return _cache_and_respond(raw_audio, "audio/ogg")
                                        # Format PCM buffer into standard WAV 24kHz 16-bit
                                        wav_buf = io.BytesIO()
                                        with wave.open(wav_buf, "wb") as wf:
                                            wf.setnchannels(1)
                                            wf.setsampwidth(2)
                                            wf.setframerate(24000)
                                            wf.writeframes(raw_audio)
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
