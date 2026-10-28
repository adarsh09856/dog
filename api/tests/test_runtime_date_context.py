from datetime import datetime
from types import SimpleNamespace as NS

from api.services.workflow import pipecat_engine_context_composer as composer


def test_node_prompt_uses_india_local_time_without_asking_for_timezone(monkeypatch):
    now = datetime.fromisoformat("2026-10-16T02:00:00+05:30")
    monkeypatch.setattr(composer, "datetime", NS(now=lambda tz: now))
    result = composer.compose_system_prompt_for_node(
        node=NS(prompt="Book appointments", out_edges=[], add_global_prompt=False),
        workflow=NS(global_node_id=None), format_prompt=lambda text: text,
        has_recordings=False,
    )
    assert "2026-10-16T02:00+05:30" in result.text
    assert "IST, Asia/Kolkata" in result.text
    assert "never ask the caller for a timezone" in result.text
    assert "Never invent the current date" in result.text


def test_node_prompt_stays_stable_within_same_india_minute(monkeypatch):
    node = NS(prompt="Answer callers", out_edges=[], add_global_prompt=False)
    workflow = NS(global_node_id=None)
    prompts = []

    for second in (5, 55):
        now = datetime.fromisoformat(f"2026-10-16T02:00:{second:02d}+05:30")
        monkeypatch.setattr(composer, "datetime", NS(now=lambda tz, value=now: value))
        result = composer.compose_system_prompt_for_node(
            node=node,
            workflow=workflow,
            format_prompt=lambda text: text,
            has_recordings=False,
        )
        prompts.append(result.text)

    assert prompts[0] == prompts[1]


def test_shared_runtime_guidance_is_service_neutral_and_speech_friendly():
    assert "configured tool for actions" in composer.ACTION_GROUNDING_INSTRUCTIONS
    assert "naturally pause" in composer.ACTION_GROUNDING_INSTRUCTIONS
    assert "ask them to repeat" in composer.ACTION_GROUNDING_INSTRUCTIONS
    assert "booking" not in composer.ACTION_GROUNDING_INSTRUCTIONS.lower()


def test_no_tool_guidance_does_not_turn_custom_agent_into_order_support():
    result = composer.compose_system_prompt_for_node(
        node=NS(prompt="Help learners practice spoken English", out_edges=[], add_global_prompt=False),
        workflow=NS(global_node_id=None), format_prompt=lambda text: text,
        has_recordings=False,
    )
    assert "Help learners practice spoken English" in result.text
    assert "No external lookup or action tools are connected" in result.text
    assert "live orders" not in result.text.lower()
    assert "track shipments" not in result.text.lower()
    assert "merchant" not in result.text.lower()


def test_non_scheduling_prompt_stays_stable_across_minute_changes(monkeypatch):
    node = NS(prompt="Handle deliveries", add_global_prompt=False,
              out_edges=[NS(get_function_name=lambda: "support", condition="Needs help")])
    results = []
    for minute in (1, 2):
        now = datetime.fromisoformat(f"2026-10-19T16:{minute:02d}:00+05:30")
        monkeypatch.setattr(composer, "datetime", NS(now=lambda tz, value=now: value))
        results.append(composer.compose_system_prompt_for_node(
            node=node, workflow=NS(global_node_id=None), format_prompt=lambda text: text,
            has_recordings=False, speech_instructions="Match caller language. Use feminine grammar.",
        ).text)
    assert results[0] == results[1]
    assert "Current India local time:" not in results[0]
    assert "support: Needs help" in results[0]
    assert "Match caller language. Use feminine grammar." in results[0]


def test_scheduling_prompt_receives_current_india_time(monkeypatch):
    now = datetime.fromisoformat("2026-10-16T02:00:00+05:30")
    monkeypatch.setattr(composer, "datetime", NS(now=lambda tz: now))
    result = composer.compose_system_prompt_for_node(
        node=NS(prompt="Help callers book a time slot", out_edges=[], add_global_prompt=False),
        workflow=NS(global_node_id=None), format_prompt=lambda text: text,
        has_recordings=False,
    )
    assert "Current India local time: 2026-10-16T02:00+05:30" in result.text
    assert "Never invent the current date" in result.text
