import logging
from datetime import datetime, timedelta
from typing import List, Literal, Optional, TypedDict, Union

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from api.db import db_client
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
    "dograh",
]


UNIVERSAL_VOICE_CATALOG: dict[str, list[dict]] = {
    "speaches": [
        {"voice_id": "af_heart", "name": "Heart (Warm & Natural)", "description": "Natural sounding American female voice, ideal for conversational agents.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "am_adam", "name": "Adam (Clear Professional)", "description": "Confident American male voice suitable for business, banking, and support.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "bf_emma", "name": "Emma (Expressive British)", "description": "Refined British female voice with excellent diction and warmth.", "gender": "female", "accent": "gb", "language": "en"},
        {"voice_id": "bm_george", "name": "George (Authoritative British)", "description": "Distinguished British male voice for corporate and authoritative personas.", "gender": "male", "accent": "gb", "language": "en"},
        {"voice_id": "af_nicole", "name": "Nicole (Friendly Guide)", "description": "Engaging, friendly female guide for real estate and appointments.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "am_michael", "name": "Michael (Calm Narrator)", "description": "Calm, reassuring American male voice great for healthcare inquiries.", "gender": "male", "accent": "us", "language": "en"},
        {"voice_id": "af_bella", "name": "Bella (Conversational Warmth)", "description": "Bubbly and warm female persona for sales and retail.", "gender": "female", "accent": "us", "language": "en"},
        {"voice_id": "af_sarah", "name": "Sarah (Corporate Support)", "description": "Polite and responsive female voice designed for customer service.", "gender": "female", "accent": "us", "language": "en"},
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
for p_key in ["elevenlabs", "cartesia", "openai", "deepgram", "google", "azure", "sarvam", "navana", "speaches", "smallest", "lmnt", "rime"]:
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
    provider: TTSProvider,
    model: Optional[str] = None,
    language: Optional[str] = None,
    q: Optional[str] = None,
    gender: Optional[str] = None,
    accent: Optional[str] = None,
    provider_filter: Optional[str] = None,
    user: UserModel = Depends(get_user),
) -> VoicesResponse:
    """Get available voices for a TTS provider with 0ms in-memory latency and zero cloud locks."""
    provider_key = provider.lower()
    raw_catalog = UNIVERSAL_VOICE_CATALOG.get(provider_key) or MANAGED_UNIVERSAL_VOICES

    # Filter managed voices by active platform master keys
    if provider_key in ("kodewaves", "dograh", "all"):
        enabled_provs = {"speaches"}
        for p in ["elevenlabs", "cartesia", "openai", "deepgram", "google", "gemini", "azure", "sarvam", "navana", "smallest", "lmnt", "rime"]:
            try:
                creds = await master_credential_service.get_master_credential(p)
                if creds and (creds.get("api_key") or creds.get("auth_token")):
                    enabled_provs.add(p)
                    if p in ("google", "gemini"):
                        enabled_provs.add("google")
                        enabled_provs.add("gemini")
            except Exception:
                pass
        if len(enabled_provs) > 1:
            raw_catalog = [v for v in raw_catalog if v.get("provider") in enabled_provs]

    filtered = raw_catalog
    if provider_filter and provider_filter != "__all__":
        filtered = [v for v in filtered if v.get("provider") == provider_filter]
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

    # Calculate facets dynamically from full provider catalog
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
