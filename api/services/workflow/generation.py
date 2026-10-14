"""Generate bounded, validated conversation graphs with the selected organization LLM."""

import asyncio
import json
import re
import unicodedata

from fastapi import HTTPException
from pipecat.processors.aggregators.llm_context import LLMContext

from api.services.configuration.ai_model_configuration import (
    get_effective_ai_model_configuration_for_workflow,
    get_resolved_ai_model_configuration,
)
from api.services.configuration.language_normalizer import (
    resolve_agent_speech_language,
    speech_language_instruction,
)
from api.services.pipecat.service_factory import create_llm_service
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph


async def generate_voice_workflow(
    organization_id: int, name: str, description: str, instructions: str | None = None,
) -> tuple[dict, str, str]:
    configuration = await get_effective_ai_model_configuration_for_workflow(
        organization_id=organization_id,
        workflow_configurations=None,
    )
    if configuration.llm is None:
        raise HTTPException(
            status_code=400,
            detail="No active LLM is configured. Select an administrator-provided, BYOK, or enabled local model first.",
        )
    provider = str(getattr(configuration.llm.provider, "value", configuration.llm.provider))
    user_key = getattr(configuration.llm, "api_key", None)
    if provider in ("kodewaves", "dograh") and user_key == "sovereign-managed":
        resolved = await get_resolved_ai_model_configuration(organization_id=organization_id)
        configuration = resolved.effective
    if configuration.llm is None:
        raise HTTPException(status_code=400, detail="No active LLM is configured for this organization")
    provider = str(getattr(configuration.llm.provider, "value", configuration.llm.provider))
    model = configuration.llm.model
    selected_language = resolve_agent_speech_language(configuration)
    llm = create_llm_service(configuration, usage_context="agent_builder")
    language = speech_language_instruction(selected_language)

    system_prompt = """Design a short voice-agent conversation plan. Return only one JSON object:
{"greeting":{"prompt":"opening instructions","completion_condition":"when to proceed"},"steps":[{"name":"step name","prompt":"conversation instructions","completion_condition":"when this step is complete"}],"closing":{"prompt":"closing instructions"}}.
Use one or two steps. Keep each prompt to one or two short sentences suited to a spoken conversation. Each completion_condition must describe what the caller must provide or confirm before moving on; never use unconditional true. Do not invent tools, integrations, credentials, booking confirmations, or template variables. For bookings, collect and confirm the requested details; never claim a reservation was saved without a configured booking tool. Return JSON only, without markdown."""
    if language:
        system_prompt += "\n" + language
    user_prompt = (
        f"Create a voice agent named {name!r}.\nPurpose: {description}\n"
        f"Additional instructions: {instructions or 'None'}"
    )
    try:
        context = LLMContext()
        context.set_messages([{"role": "user", "content": user_prompt}])
        # Builder generation may load a CPU-hosted model from cold; this is
        # separate from the interactive call response latency budget.
        async with asyncio.timeout(120):
            raw = await llm.run_inference(
                context, system_instruction=system_prompt, max_tokens=1000,
            )
        text = (raw or "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("The selected model did not return a conversation plan")
        plan = json.loads(text[start:end + 1])
        if not isinstance(plan, dict):
            raise ValueError("The conversation plan must be an object")
        steps = plan.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
            raise ValueError("The conversation plan requires one to three steps")
        segments = [plan.get("greeting"), *steps, plan.get("closing")]
        nodes, edges = [], []
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                raise ValueError("Each conversation step must be an object")
            prompt = segment.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
                raise ValueError("Each step requires a bounded conversation prompt")
            if "{{" in prompt:
                raise ValueError("Generated prompts cannot invent template variables")
            words = re.findall(r"\w+", prompt.casefold())
            if len(words) > 6 and len(set(words)) / len(words) < 0.45:
                raise ValueError("Generated prompt is repetitive and needs regeneration")
            expected_language = {
                "hi": "devanagari",
                "ja": "hiragana",
                "zh": "han",
                "ko": "hangul",
                "ru": "cyrillic",
                "ar": "arabic",
                "bn": "bengali",
                "ta": "tamil",
                "te": "telugu",
                "th": "thai",
            }.get((selected_language or "").split("-")[0].lower())
            if expected_language and any(char.isalpha() for char in prompt) and not any(
                expected_language in unicodedata.name(char, "").lower()
                for char in prompt
            ):
                raise ValueError("Generated prompt does not use the selected language script")
            is_start, is_end = index == 0, index == len(segments) - 1
            step_name = segment.get("name") or ("Greeting" if is_start else "Closing" if is_end else f"Step {index}")
            if not isinstance(step_name, str) or len(step_name) > 120:
                raise ValueError("Conversation step names must be bounded strings")
            node_id = f"generated-{index}"
            nodes.append({
                "id": node_id,
                "type": "startCall" if is_start else "endCall" if is_end else "agentNode",
                "position": {"x": 240, "y": index * 220},
                "data": {
                    "name": step_name, "prompt": prompt.strip(),
                    "is_start": is_start, "is_end": is_end,
                    "allow_interrupt": True, "add_global_prompt": False,
                    "extraction_enabled": False,
                },
            })
            if not is_end:
                condition = segment.get("completion_condition")
                if not isinstance(condition, str) or not condition.strip() or condition.strip().lower() == "true":
                    raise ValueError("Each transition requires conversational completion criteria")
                if len(condition) > 1000:
                    raise ValueError("Transition criteria exceed the supported size")
                edges.append({
                    "id": f"generated-edge-{index}", "source": node_id,
                    "target": f"generated-{index + 1}",
                    "data": {"label": f"continue_to_step_{index + 1}", "condition": condition.strip()},
                })
        dto = ReactFlowDTO.model_validate({"nodes": nodes, "edges": edges})
        WorkflowGraph(dto)
        definition = json.loads(dto.model_dump_json(exclude_none=True))
        definition["viewport"] = {"x": 0, "y": 0, "zoom": 0.8}
        return definition, provider, model
    finally:
        await llm.cleanup()
