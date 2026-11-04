import pytest

from api.services.pipecat.speaches_tts import SpeachesLiveTTSService
from api.services.pipecat.local_speech_aggregator import LocalSpeechAggregator
from pipecat.services.speaches.tts import SpeachesTTSSettings


@pytest.mark.asyncio
async def test_long_followup_releases_a_coherent_phrase_before_sentence_end():
    service = SpeachesLiveTTSService(
        api_key='test', base_url='http://localhost:8000/v1',
        settings=SpeachesTTSSettings(model='indic-vits-rasa-13', voice='HIN_F'),
    )
    aggregator = service._text_aggregator
    try:
        sentence = (
            'आपका नाम मिल गया है। कृपया अपना पूरा मोबाइल नंबर एक साथ बताइए ताकि संपर्क की सही जानकारी मिल सके '
            'और मैं आपकी बुकिंग के लिए आवश्यक जानकारी सही तरीके से दर्ज कर सकूँ। '
        )
        parts = []
        for word in sentence.split(' '):
            parts.extend([part async for part in aggregator.aggregate(word + ' ')])
        tail = await aggregator.flush()
        if tail:
            parts.append(tail)
        assert len(parts) >= 2
        assert all(len(part.text.strip()) >= 24 for part in parts[:-1])
        assert ''.join(part.text for part in parts).strip() == sentence.strip()
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_first_phrase_releases_at_16_chars_on_a_safe_word_boundary():
    aggregator = LocalSpeechAggregator(
        min_characters=24,
        first_chunk_characters=12,
        first_phrase_characters=16,
    )
    emitted = []
    for word in "I can help you today, please tell me your name.".split(" "):
        emitted.extend([part.text async for part in aggregator.aggregate(word + " ")])
        if emitted:
            break

    assert emitted == ["I can help you today, "]


@pytest.mark.asyncio
async def test_first_phrase_starts_early_and_followups_batch_to_a_coherent_segment():
    service = SpeachesLiveTTSService(
        api_key='test', base_url='http://localhost:8000/v1',
        settings=SpeachesTTSSettings(model='indic-vits-rasa-13', voice='HIN_F'),
    )
    aggregator = service._text_aggregator
    try:
        assert aggregator._streaming_phrase_characters == 48
        first = [part async for part in aggregator.aggregate("I can help you today, ")]
        assert first == []

        followup = [
            part async for part in aggregator.aggregate("please tell me your name and number ")
        ]
        assert [part.text for part in followup] == ["I can help you today, please "]
        assert len(followup[0].text.strip()) >= 24
        first_followup = followup

        followup = [
            part async for part in aggregator.aggregate("so I can find the right appointment for you ")
        ]
        assert [part.text for part in followup] == [
            "tell me your name and number so I can find the right "
        ]
        tail = await aggregator.flush()
        assert tail is not None
        assert tail.text == "appointment for you"
        assert "".join([*(part.text for part in first_followup), *(part.text for part in followup), tail.text]).strip() == (
            "I can help you today, please tell me your name and number so I can find the right appointment for you"
        )
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_streamed_numbers_and_dates_stay_in_one_synthesis_phrase():
    examples = (
        ("Please confirm the number nine five three eight three double zero nine four one.",
         "nine five three eight three double zero nine four one"),
        ("The appointment is on October twenty seven twenty twenty six at ten thirty AM.",
         "October twenty seven twenty twenty six"),
        ("कृपया मोबाइल नंबर बताइए नाइन फाइव थ्री एट थ्री डबल जीरो नाइन फोर वन।",
         "नाइन फाइव थ्री एट थ्री डबल जीरो नाइन फोर वन"),
        ("Please confirm the appointment date 27 10 2026 at 10 30 AM.",
         "27 10 2026"),
        ("Please confirm the number nine, five, three, eight, three, double zero.",
         "nine, five, three, eight, three, double zero"),
        ("தயவுசெய்து உங்கள் தொலைபேசி எண்ணை உறுதிப்படுத்துங்கள் ஒன்பது எட்டு ஏழு ஆறு ஐந்து நான்கு மூன்று இரண்டு ஒன்று பூஜ்யம்.",
         "ஒன்பது எட்டு ஏழு ஆறு ஐந்து நான்கு மூன்று இரண்டு ஒன்று பூஜ்யம்"),
        ("Please confirm the digits নম্বর নয় আট সাত ছয় পাঁচ চার তিন দুই এক শূন্য.",
         "নয় আট সাত ছয় পাঁচ চার তিন দুই এক শূন্য"),
    )
    for text, sequence in examples:
        aggregator = LocalSpeechAggregator(
            min_characters=24, first_chunk_characters=12,
            first_clause_characters=24, first_phrase_characters=16,
            streaming_phrase_characters=48,
        )
        phrases = []
        for word in text.split(" "):
            phrases.extend([part.text async for part in aggregator.aggregate(word + " ")])
        tail = await aggregator.flush()
        if tail:
            phrases.append(tail.text)
        assert any(sequence in phrase for phrase in phrases), phrases
        assert "".join(phrases).strip() == text


@pytest.mark.asyncio
async def test_number_group_survives_character_stream_and_later_phrase():
    text = (
        "Your details are confirmed. Please carefully verify your registered telephone "
        "number nine and five three eight three double zero nine four one."
    )
    sequence = "nine and five three eight three double zero nine four one"
    aggregator = LocalSpeechAggregator(
        min_characters=24, first_chunk_characters=12,
        first_clause_characters=24, first_phrase_characters=16,
        streaming_phrase_characters=48,
    )
    phrases = []
    for character in text:
        phrases.extend([part.text async for part in aggregator.aggregate(character)])
    tail = await aggregator.flush()
    if tail:
        phrases.append(tail.text)
    assert any(sequence in phrase for phrase in phrases), phrases
    assert "".join(phrases).strip() == text


@pytest.mark.asyncio
async def test_interruption_discards_a_pending_number():
    aggregator = LocalSpeechAggregator(first_chunk_characters=12, first_phrase_characters=16)
    async for _ in aggregator.aggregate("Please confirm the number nine five three "):
        pass
    await aggregator.handle_interruption()
    output = [part.text async for part in aggregator.aggregate("Hello, how can I help?")]
    tail = await aggregator.flush()
    if tail:
        output.append(tail.text)
    assert "".join(output).strip() == "Hello, how can I help?"


@pytest.mark.asyncio
async def test_hindi_spoken_day_month_and_year_are_not_split_between_requests():
    examples = (
        ("आपकी बुकिंग की तारीख अगले महीने सत्ताईस अक्टूबर दो हज़ार छब्बीस है।",
         "सत्ताईस अक्टूबर दो हज़ार छब्बीस"),
        ("आपके अगले अपॉइंटमेंट की तारीख तेईस नवंबर दो हज़ार छब्बीस है।",
         "तेईस नवंबर दो हज़ार छब्बीस"),
        ("कृपया अपनी तारीख ध्यान से सुनिए अट्ठाईस अक्टूबर दो हजार इकतीस।",
         "अट्ठाईस अक्टूबर दो हजार इकतीस"),
    )
    for text, sequence in examples:
        for width in (1, 2, 3, 7, 13, 36, 64):
            aggregator = LocalSpeechAggregator(
                min_characters=24, first_chunk_characters=12,
                first_clause_characters=24, first_phrase_characters=16,
                streaming_phrase_characters=48,
            )
            phrases = []
            for index in range(0, len(text), width):
                phrases.extend([part.text async for part in aggregator.aggregate(text[index:index + width])])
            tail = await aggregator.flush()
            if tail:
                phrases.append(tail.text)
            assert any(sequence in phrase for phrase in phrases), (width, phrases)
            assert "".join(phrases).strip() == text
