from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from api.services.workflow.tools import booking
from api.services.workflow.tools.custom_tool import tool_to_function_schema
from api.schemas.tool import CreateToolRequest


def arguments(**overrides):
    return {"customer_name": "Test Caller", "customer_phone": "+15550100000",
            "start_time": "2035-10-20T10:00:00+05:30", "confirmed_by_caller": True, **overrides}


def test_latest_caller_phone_correction_overrides_old_details_and_model_readback():
    messages = [
        {'role': 'user', 'content': 'My phone is +15555550123.'},
        {'role': 'assistant', 'content': 'I heard +155555500123.'},
        {'role': 'user', 'content': 'Correction: +15555550124. I confirm the appointment.'},
    ]
    assert booking.caller_phone_matches_booking('+15555550124', messages)
    assert not booking.caller_phone_matches_booking('+15555550123', messages)
    assert not booking.caller_phone_matches_booking('+155555500123', messages)


@pytest.mark.parametrize('reply', ['haan', 'ji haan', 'haan confirm kar do', 'book kar dijiye', 'हाँ बुक कर दो'])
def test_hinglish_confirmation_requires_a_preceding_booking_readback(reply):
    assert booking.caller_confirmed_booking([
        {'role': 'assistant', 'content': 'Appointment kal 10 AM IST hai. Kya details sahi hain?'},
        {'role': 'user', 'content': reply}])
    assert not booking.caller_confirmed_booking([
        {'role': 'assistant', 'content': 'Would you like appointment information?'},
        {'role': 'user', 'content': reply}])


def test_hinglish_negation_never_authorizes_booking():
    assert not booking.caller_confirmed_booking([
        {'role': 'assistant', 'content': 'Your appointment is at 10 AM. Confirm?'},
        {'role': 'user', 'content': 'Main confirm nahi karta hu.'}])


def test_full_hinglish_confirmation_with_details_authorizes_booking():
    assert booking.caller_confirmed_booking([
        {'role': 'assistant', 'content': 'Do you confirm the appointment for 16 October at 4 PM?'},
        {'role': 'user', 'content': (
            'Haan, confirm hai. Mera naam Local Test, phone +919000000002. '
            'Date 16 October 2026, 4 PM IST, timezone Asia/Kolkata. Book kar dijiye.'
        )},
    ])


@pytest.mark.asyncio
async def test_model_altered_phone_digits_never_reach_calendar_persistence(monkeypatch):
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
    engine = NS(active_agent=NS(), _get_organization_id=AsyncMock(return_value=7),
                context=NS(get_messages=lambda: [
                    {'role': 'user', 'content': 'I confirm the appointment. Phone +15555550123.'}]))
    save = AsyncMock()
    monkeypatch.setattr(booking, 'execute_booking', save)
    callback = AsyncMock()
    await CustomToolManager(engine)._create_booking_handler()(NS(
        arguments=arguments(customer_phone='+155555500123'), result_callback=callback))
    save.assert_not_awaited()
    assert callback.call_args.args[0]['booked'] is False


@pytest.mark.asyncio
async def test_booking_success_requires_persisted_identifier_and_trusted_workspace(monkeypatch):
    save = AsyncMock(return_value={"id": "persisted-id", "status": "confirmed"})
    monkeypatch.setattr(booking.appointments, "save_appointment", save)
    result = await booking.execute_booking(arguments(), 7)
    assert result["booked"] is True and result["appointment_id"] == "persisted-id"
    assert save.call_args.args[0] == 7
    assert "confirmed_by_caller" not in save.call_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"confirmed_by_caller": False}, {"start_time": "2035-10-20T10:00:00"},
    {"start_time": "2000-10-20T10:00:00Z"}, {"organization_id": 99},
    {"end_time": "2035-10-20T09:00:00+05:30"}, {"customer_name": " "},
])
async def test_invalid_or_unconfirmed_booking_never_writes(monkeypatch, changes):
    save = AsyncMock()
    monkeypatch.setattr(booking.appointments, "save_appointment", save)
    result = await booking.execute_booking(arguments(**changes), 7)
    assert result["booked"] is False
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_conflict_cannot_return_success(monkeypatch):
    monkeypatch.setattr(booking.appointments, "save_appointment", AsyncMock(side_effect=FileExistsError()))
    result = await booking.execute_booking(arguments(), 7)
    assert result["status"] == "conflict" and result["booked"] is False
    assert "appointment_id" not in result


def test_tool_creation_and_llm_schema_share_the_booking_contract():
    request = CreateToolRequest(name="Book Appointment", definition={"type": "book_appointment"})
    assert request.category == "book_appointment"
    schema = tool_to_function_schema(NS(name=request.name, description=None, tool_uuid="test", definition=request.definition.model_dump()))
    assert schema["function"]["name"] == "book_appointment"
    assert "confirmed_by_caller" in schema["function"]["parameters"]["required"]
    assert "organization_id" not in schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_runtime_dispatches_native_booking_and_surfaces_persistence_failure(monkeypatch):
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    engine = NS(active_agent=NS(), _get_organization_id=AsyncMock(return_value=7), context=NS(
        get_messages=lambda: [{'role': 'user', 'content': 'I confirm the appointment.'}]))
    manager = CustomToolManager(engine)
    tool = NS(category="book_appointment")
    handler, timeout = manager._create_handler(tool, "book_appointment")
    assert timeout == 10.0
    monkeypatch.setattr(booking.appointments, "save_appointment", AsyncMock(side_effect=RuntimeError("Synthetic unavailable database")))
    callback = AsyncMock()
    await handler(NS(arguments=arguments(), result_callback=callback))
    result = callback.call_args.args[0]
    assert result["booked"] is False and result["status"] == "error"
    assert "Synthetic unavailable database" not in result["error"]


@pytest.mark.asyncio
async def test_handler_recovers_missing_confirmation_only_from_actual_caller(monkeypatch):
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
    engine = NS(active_agent=NS(), _get_organization_id=AsyncMock(return_value=7), context=NS(get_messages=lambda: [
        {'role': 'user', 'content': 'मैं राहुल अपॉइंटमेंट की पुष्टि करता हूँ।'}]))
    execute = AsyncMock(return_value={'booked': True, 'appointment_id': 'actual'})
    monkeypatch.setattr(booking, 'execute_booking', execute)
    supplied = arguments(); supplied.pop('confirmed_by_caller')
    await CustomToolManager(engine)._create_booking_handler()(NS(arguments=supplied, result_callback=AsyncMock()))
    assert execute.await_args.args[0]['confirmed_by_caller'] is True
    assert execute.await_args.args[1] == 7


@pytest.mark.asyncio
async def test_model_confirmation_boolean_cannot_replace_caller_consent(monkeypatch):
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
    engine = NS(active_agent=NS(), _get_organization_id=AsyncMock(return_value=7), context=NS(get_messages=lambda: [
        {'role': 'user', 'content': 'What appointment slots do you have?'}]))
    save = AsyncMock(); monkeypatch.setattr(booking.appointments, 'save_appointment', save)
    callback = AsyncMock()
    await CustomToolManager(engine)._create_booking_handler()(NS(arguments=arguments(), result_callback=callback))
    save.assert_not_awaited()
    assert callback.call_args.args[0]['booked'] is False


def test_short_yes_only_confirms_after_readback_confirmation_question():
    assert booking.caller_confirmed_booking([
        {'role': 'assistant', 'content': 'आपकी अपॉइंटमेंट कल सुबह दस बजे है। क्या ये विवरण सही हैं?'},
        {'role': 'user', 'content': 'हाँ।'}])
    assert not booking.caller_confirmed_booking([
        {'role': 'assistant', 'content': 'Would you like information about appointment availability?'},
        {'role': 'user', 'content': 'Yes.'}])


@pytest.mark.asyncio
async def test_saved_hindi_booking_speaks_actual_result_without_second_generation(monkeypatch):
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
    engine = NS(active_agent=NS(user_config=NS(tts=NS(language='hi'))),
                _get_organization_id=AsyncMock(return_value=7),
                context=NS(get_messages=lambda: [{'role': 'user', 'content': 'I confirm the appointment.'}]),
                queue_speech=AsyncMock(), _is_realtime=False)
    monkeypatch.setattr(booking, 'execute_booking', AsyncMock(return_value={
        'booked': True, 'appointment_id': 'persisted-id', 'start_time': '2035-10-20T10:00:00+05:30'}))
    callback = AsyncMock()
    await CustomToolManager(engine)._create_booking_handler()(NS(arguments=arguments(), result_callback=callback))
    properties = callback.call_args.kwargs['properties']
    assert properties.run_llm is False
    engine.queue_speech.assert_not_awaited()
    await properties.on_context_updated()
    speech = engine.queue_speech.call_args.args[0]
    assert 'persisted-id' in speech and 'बुक हो गई' in speech
    assert engine.queue_speech.call_args.kwargs['append_to_context'] is True


@pytest.mark.parametrize("reply", ["ok", "okay", "yes", "ok please"])
def test_natural_permission_after_full_readback_is_booking_consent(reply):
    assert booking.caller_confirmed_booking([
        {"role": "assistant", "content": "Your appointment is October 16, 2026 at 8 AM IST. Shall I go ahead and book this for you?"},
        {"role": "user", "content": reply},
    ])


def test_timezone_confirmation_alone_does_not_authorize_booking():
    assert not booking.caller_confirmed_booking([
        {"role": "user", "content": "I want an appointment tomorrow"},
        {"role": "assistant", "content": "Just to confirm, you mean Indian Standard Time (IST), right?"},
        {"role": "user", "content": "yes"},
    ])


@pytest.mark.asyncio
async def test_short_incomplete_phone_never_creates_appointment(monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(booking.appointments, "save_appointment", save)
    result = await booking.execute_booking(arguments(customer_phone="12346"), 7)
    assert result["booked"] is False
    assert "complete phone" in result["error"]
    save.assert_not_awaited()


@pytest.mark.parametrize("reply", ["ok", "हाँ", "theek hai", "ठीक है"])
def test_hindi_readback_permission_accepts_natural_confirmation(reply):
    assert booking.caller_confirmed_booking([
        {"role": "assistant", "content": "ठीक है, तो मैं आपका अपॉइंटमेंट कल, यानी 16 अक्टूबर 2026 को शाम 4:40 PM (Indian Standard Time) के लिए बुक कर दूँ?"},
        {"role": "user", "content": reply},
    ])



def test_hindi_confirm_loanword_permission_is_recognized():
    assert booking.caller_confirmed_booking([
        {"role": "assistant", "content": "कल, 16 अक्टूबर 2026 को शाम 4:40 बजे IST पर आपका अपॉइंटमेंट कन्फर्म कर दूँ?"},
        {"role": "user", "content": "ok"},
    ])
