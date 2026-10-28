from api.services.workflow.direct_caller_reply import direct_caller_reply


def test_hindi_order_topic_fragment_gets_fast_clarification_even_with_tools():
    assert direct_caller_reply(
        "अः मुझे एक ऑर्डर के देकर बात कर", has_lookup_tools=True
    ) == "ज़रूर, ऑर्डर में क्या मदद चाहिए?"


def test_hindi_help_stt_variant_gets_relevant_fast_question():
    assert direct_caller_reply(
        "मुझे एक हेल्प चाह था", has_lookup_tools=True
    ) == "ज़रूर, किस काम में मदद चाहिए?"


def test_room_booking_without_a_booking_tool_does_not_invent_availability():
    hindi = (
        "माफ़ कीजिए, मैं यहाँ कमरे की उपलब्धता या बुकिंग की पुष्टि नहीं कर सकती। "
        "कृपया सहायता टीम से संपर्क करें।"
    )
    english = (
        "Sorry, I can’t check room availability or make a booking here. "
        "Please contact the support team."
    )
    assert direct_caller_reply("मुझे रूम बुक करना है", has_lookup_tools=False) == hindi
    assert direct_caller_reply("I want to book a room", has_lookup_tools=False) == english
    assert direct_caller_reply("मुझे रूम बुक करना है", has_lookup_tools=True) is None
    assert direct_caller_reply("मुझे रूम बुक नहीं करना है", has_lookup_tools=False) is None


def test_hindi_order_enquiry_is_not_rerouted_to_department():
    assert direct_caller_reply(
        "मुझे अपने ऑर्डर के बारे में बात करनी है", has_lookup_tools=True
    ) == "ज़रूर, ऑर्डर में क्या मदद चाहिए?"


def test_order_status_with_tools_stays_on_lookup_path():
    assert direct_caller_reply(
        "मेरे ऑर्डर का स्टेटस क्या है", has_lookup_tools=True
    ) is None


def test_order_refusal_is_not_mistaken_for_an_enquiry():
    assert direct_caller_reply(
        "मुझे ऑर्डर के बारे में बात नहीं करनी है", has_lookup_tools=True
    ) is None


def test_delayed_order_without_lookup_gets_grounded_fast_reply_in_supported_scripts():
    hindi = (
        "माफ़ कीजिए, मुझे लाइव डिलीवरी स्टेटस नहीं दिखता। "
        "कृपया आधिकारिक ट्रैकिंग लिंक या सपोर्ट से जानकारी लें।"
    )
    english = (
        "I can't see live delivery updates here. Please use your official tracking link "
        "or contact support."
    )
    assert direct_caller_reply(
        "मेरे ऑर्डर की डिलीवरी में देरी हो रही है।", has_lookup_tools=False
    ) == hindi
    assert direct_caller_reply(
        "My order delivery is delayed.", has_lookup_tools=False
    ) == english
    assert direct_caller_reply(
        "Mere order ki delivery mein der ho rahi hai", has_lookup_tools=False
    ) == hindi


def test_delayed_order_stays_on_lookup_path_when_tools_exist():
    assert direct_caller_reply(
        "मेरे ऑर्डर की डिलीवरी में देरी हो रही है।", has_lookup_tools=True
    ) is None


def test_order_delay_negative_statement_is_not_treated_as_a_complaint():
    assert direct_caller_reply(
        "My order delivery is not delayed.", has_lookup_tools=False
    ) is None
    assert direct_caller_reply(
        "मेरे ऑर्डर की डिलीवरी में देरी नहीं हो रही है।", has_lookup_tools=False
    ) is None


def test_address_change_without_order_action_gets_grounded_reply_in_supported_scripts():
    hindi = (
        "माफ़ कीजिए, इस कॉल में ऑर्डर का पता बदलने की सुविधा जुड़ी नहीं है। "
        "कृपया अपने ऑर्डर पेज से पता अपडेट करें या सपोर्ट से संपर्क करें।"
    )
    english = (
        "I can't change an order address in this call. Please update it from your "
        "order page or contact support."
    )
    assert direct_caller_reply(
        "मुझे अपने ऑर्डर का डिलीवरी पता बदलना है।", has_lookup_tools=False
    ) == hindi
    assert direct_caller_reply(
        "I need to change the delivery address for my order.", has_lookup_tools=False
    ) == english
    assert direct_caller_reply(
        "I need to change my order address", has_lookup_tools=False
    ) == english
    assert direct_caller_reply(
        "Mujhe apne order ka delivery address change karna hai.",
        has_lookup_tools=False,
    ) == hindi
    assert direct_caller_reply(
        "Mera order address change karna hai", has_lookup_tools=False
    ) == hindi


def test_address_change_stays_on_workflow_path_when_tool_exists_or_intent_is_not_exact():
    assert direct_caller_reply(
        "I need to change the delivery address for my order.", has_lookup_tools=True
    ) is None
    assert direct_caller_reply(
        "I don't need to change the delivery address for my order.", has_lookup_tools=False
    ) is None
    assert direct_caller_reply(
        "I need to change the delivery address for my order and cancel it.",
        has_lookup_tools=False,
    ) is None


def test_recognized_room_request_with_hesitation_does_not_invent_message_taking():
    text = "अः मुझे ना एक रूम वगैरह बुक करना था"
    reply = direct_caller_reply(text, has_lookup_tools=False)
    assert reply and "बुकिंग की पुष्टि नहीं" in reply
    assert "संदेश" not in reply
    assert direct_caller_reply(text, has_lookup_tools=True) is None


def test_room_fast_reply_does_not_drop_additional_caller_requests():
    for text in (
        "I want to book a room and tell me your opening hours",
        "मुझे एक रूम बुक करना है और आपका समय क्या है",
        "Mujhe ek room book karna hai aur price bataiye",
    ):
        assert direct_caller_reply(text, has_lookup_tools=False) is None
