from types import SimpleNamespace as NS
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from api.services.workflow.tools import booking
from api.services.workflow.tools.custom_tool import tool_to_function_schema
from api.schemas.tool import CreateToolRequest


@pytest.fixture(autouse=True)
def allow_saas_appointment_feature_in_unit_tests(monkeypatch):
    monkeypatch.setattr(booking, "enforce_saas_feature", AsyncMock())


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
@pytest.mark.parametrize("allowed", [False, True])
async def test_client_booking_requires_signed_appointments_grant(monkeypatch, allowed):
    from api.services import client_worker_entitlements as entitlements
    from api.services.installation_license import InstallationLicense

    monkeypatch.setattr(entitlements, "runtime_edition", lambda: "client")
    license_data = InstallationLicense(
        "client-1", "customer-1", "client", ("example.com",), 2**31,
        frozenset({"voice", "appointments"} if allowed else {"voice"}), {},
    )
    monkeypatch.setattr(entitlements, "load_license", lambda: license_data)
    monkeypatch.setattr(entitlements, "validate_installation_license", lambda _: None)
    owner_status = AsyncMock()
    monkeypatch.setattr(entitlements, "require_current_owner_status", owner_status)
    save = AsyncMock(return_value={"id": "saved-id", "status": "confirmed"})
    monkeypatch.setattr(booking.appointments, "save_appointment", save)

    result = await booking.execute_booking(arguments(), 7)
    assert result["booked"] is allowed
    if allowed:
        owner_status.assert_awaited_once_with(license_data)
        save.assert_awaited_once()
        assert result["appointment_id"] == "saved-id"
    else:
        save.assert_not_awaited()


@pytest.mark.asyncio
async def test_booking_does_not_write_when_client_owner_status_is_denied(monkeypatch):
    from api.services.installation_license import InstallationLicenseError

    monkeypatch.setattr(
        booking, "require_client_worker_features",
        AsyncMock(side_effect=InstallationLicenseError("Installation license was revoked")),
    )
    save = AsyncMock()
    monkeypatch.setattr(booking.appointments, "save_appointment", save)
    result = await booking.execute_booking(arguments(), 7)
    assert result["booked"] is False
    save.assert_not_awaited()


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


# Full booking dialogue: name -> phone readback/confirm -> date -> time ->
# exact slot readback. The clarification turns push the original "mujhe
# appointment book karna hai" request more than five dialogue messages back
# from the caller's final "haan theek hai", reproducing the caller-reported
# stale phone prompt after an exact English date/time readback.
_FULL_HINDI_BOOKING_DIALOGUE = [
    {"role": "user", "content": "मुझे अपॉइंटमेंट बुक करना है"},
    {"role": "assistant", "content": "अपॉइंटमेंट किस नाम से बुक करूँ?"},
    {"role": "user", "content": "आदर्श"},
    {"role": "assistant", "content": "मोबाइल नंबर बताइए।"},
    {"role": "user", "content": "नाइन फाइव थ्री आठ थ्री डबल जीरो नाइन फोर वन"},
    {"role": "assistant", "content": "मैंने नंबर पढ़ा है। क्या यह सही है?"},
    {"role": "user", "content": "हाँ सही है"},
    {"role": "assistant", "content": "किस तारीख और समय के लिए बुक करना चाहेंगे?"},
    {"role": "user", "content": "कल का"},
    {"role": "assistant", "content": "कल का समय क्या है?"},
    {"role": "user", "content": "It's ten a.m."},
    {"role": "assistant", "content": "Thank you Aradhya ji. Is 10:00 AM on November 9th confirmed?"},
    {"role": "user", "content": "हाँ ठीक है"},
]
_STAGED_STATE = {
    "caller_name": "आदर्श",
    "caller_phone": "9538300941",
    "reply_language": "Hindi",
    "booking_time_question_date": "2026-11-09",
    "booking_confirmation_slot": "2026-11-09T10:00",
}
_STAGED_CONTACT = {"customer_name": "आदर्श", "customer_phone": "9538300941"}


@pytest.mark.asyncio
async def test_full_dialogue_replay_books_without_reasking_confirmed_phone(monkeypatch):
    """Replay the full booking exchange through the real consent handler.

    The staged-slot parser already builds valid arguments for this dialogue
    (see test_affirmative_after_model_worded_slot_confirmation_uses_staged_booking
    in test_voice_contact_regressions.py). The native handler must not then
    reject consent and fall back to asking for the already-confirmed phone
    number again.
    """
    from api.services.workflow import contact_context
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 8, 12, 0, tzinfo=tz)

    monkeypatch.setattr(contact_context, "datetime", FrozenDateTime)
    monkeypatch.setattr(booking, "datetime", FrozenDateTime)

    staged_arguments = contact_context.confirmed_staged_booking_arguments(
        _FULL_HINDI_BOOKING_DIALOGUE, dict(_STAGED_STATE), _STAGED_CONTACT,
    )
    assert staged_arguments is not None, "staged-slot parser must recognize this exact readback"

    save = AsyncMock(return_value={"id": "appt-1", "status": "confirmed"})
    monkeypatch.setattr(booking.appointments, "save_appointment", save)
    engine = NS(
        active_agent=NS(),
        _get_organization_id=AsyncMock(return_value=7),
        context=NS(get_messages=lambda: _FULL_HINDI_BOOKING_DIALOGUE),
        _contact_conversation_state=dict(_STAGED_STATE),
    )
    callback = AsyncMock()
    await CustomToolManager(engine)._create_booking_handler()(
        NS(arguments=staged_arguments, result_callback=callback)
    )
    result = callback.call_args.args[0]
    assert result["booked"] is True, result
    save.assert_awaited_once()
    saved_phone = save.call_args.args[1]["customer_phone"]
    assert saved_phone == "9538300941", "must reuse the already-confirmed phone, not re-ask for it"


@pytest.mark.asyncio
async def test_full_dialogue_replay_honors_a_late_refusal(monkeypatch):
    """A clear refusal at the final turn must never be booked."""
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    dialogue = [*_FULL_HINDI_BOOKING_DIALOGUE[:-1], {"role": "user", "content": "नहीं, अभी मत करो।"}]
    save = AsyncMock()
    monkeypatch.setattr(booking.appointments, "save_appointment", save)
    engine = NS(
        active_agent=NS(),
        _get_organization_id=AsyncMock(return_value=7),
        context=NS(get_messages=lambda: dialogue),
        _contact_conversation_state=dict(_STAGED_STATE),
    )
    callback = AsyncMock()
    # Even if a prior step mistakenly staged confirmed_by_caller=True, the
    # handler must recompute consent from the actual caller turn and refuse.
    await CustomToolManager(engine)._create_booking_handler()(NS(
        arguments=arguments(customer_name="आदर्श", customer_phone="9538300941"),
        result_callback=callback,
    ))
    save.assert_not_awaited()
    assert callback.call_args.args[0]["booked"] is False


def test_full_dialogue_replay_does_not_stage_a_changed_slot():
    """A changed time at the final turn must not confirm the stale staged slot."""
    from api.services.workflow import contact_context

    dialogue = [
        *_FULL_HINDI_BOOKING_DIALOGUE[:-1],
        {"role": "user", "content": "No wait, make it 11 AM instead."},
    ]
    assert contact_context.confirmed_staged_booking_arguments(
        dialogue, dict(_STAGED_STATE), _STAGED_CONTACT,
    ) is None
    assert not booking.caller_confirmed_booking(dialogue)


def test_full_dialogue_replay_phone_confirmation_is_not_booking_consent():
    """A caller's "yes" to the phone readback must not itself grant booking consent."""
    from api.services.workflow import contact_context

    dialogue = _FULL_HINDI_BOOKING_DIALOGUE[:7]  # ends at "हाँ सही है" (phone confirmation)
    assert not booking.caller_confirmed_booking(dialogue)
    state_before_slot = {
        "caller_name": "आदर्श", "caller_phone": "9538300941", "reply_language": "Hindi",
    }
    assert contact_context.confirmed_staged_booking_arguments(
        dialogue, state_before_slot, _STAGED_CONTACT,
    ) is None


def test_late_generic_booking_question_does_not_confirm_unread_slot():
    """A generic offer cannot bypass the recent booking guard without a slot readback."""
    dialogue = [
        {"role": "user", "content": "I want an appointment"},
        {"role": "assistant", "content": "What is your name?"},
        {"role": "user", "content": "Adarsh"},
        {"role": "assistant", "content": "What is your phone number?"},
        {"role": "user", "content": "9538300941"},
        {"role": "assistant", "content": "What time works for you?"},
        {"role": "user", "content": "Tomorrow at 10 AM"},
        {"role": "assistant", "content": "I still need to check availability. Should I book it?"},
        {"role": "user", "content": "Yes"},
    ]
    assert not booking.caller_confirmed_booking(dialogue)
