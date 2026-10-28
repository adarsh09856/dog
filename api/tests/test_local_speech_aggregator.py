import pytest
from api.services.pipecat.local_speech_aggregator import LocalSpeechAggregator


@pytest.mark.asyncio
@pytest.mark.parametrize("first,tail", [
    ("I cannot see your order details,", " please contact the seller."),
    ("ನಾನು ನಿಮ್ಮ ಆರ್ಡರ್ ನೋಡಲು ಸಾಧ್ಯವಿಲ್ಲ,", " ದಯವಿಟ್ಟು ಮಾರಾಟಗಾರರನ್ನು ಸಂಪರ್ಕಿಸಿ."),
    ("मैं आपके ऑर्डर की स्थिति नहीं देख सकता,", " कृपया विक्रेता से संपर्क करें।"),
    ("میں آپ کے آرڈر کی تفصیل نہیں دیکھ سکتا،", " براہ کرم فروخت کنندہ سے رابطہ کریں۔"),
])
async def test_optional_first_clause_streams_before_sentence_without_losing_text(first, tail):
    aggregator = LocalSpeechAggregator(first_clause_characters=24)
    emitted = []
    for character in first:
        emitted.extend([part.text async for part in aggregator.aggregate(character)])
    assert emitted == []  # punctuation needs whitespace lookahead
    emitted.extend([part.text async for part in aggregator.aggregate(" ")])
    assert emitted == [first + " "]
    emitted.extend([part.text async for part in aggregator.aggregate(tail.lstrip())])
    final = await aggregator.flush()
    if final:
        emitted.append(final.text)
    assert "".join(emitted).strip() == (first + tail).strip()


@pytest.mark.asyncio
async def test_first_clause_never_splits_numeric_commas_or_survives_interruption():
    aggregator = LocalSpeechAggregator(first_clause_characters=24)
    text = "Your current total is 12,345, please"
    assert [part async for part in aggregator.aggregate(text)] == []
    await aggregator.handle_interruption()
    assert await aggregator.flush() is None
    phrase = "This is the replacement answer, "
    emitted = [part.text async for part in aggregator.aggregate(phrase)]
    assert emitted == [phrase]
    assert "".join(emitted).strip() == phrase.strip()


@pytest.mark.asyncio
@pytest.mark.parametrize("sentence", [
    "Please tell me which order you need help with so I can explain the next step clearly",
    "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆರ್ಡರ್ ಬಗ್ಗೆ ಇನ್ನಷ್ಟು ಮಾಹಿತಿ ನೀಡಿ ನಾನು ನಿಮಗೆ ಮುಂದಿನ ಹಂತವನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ಹೇಳುತ್ತೇನೆ",
])
async def test_first_long_phrase_releases_before_sentence_ends(sentence):
    aggregator = LocalSpeechAggregator(first_phrase_characters=48)
    parts = []
    for word in sentence.split(" "):
        parts.extend([part.text async for part in aggregator.aggregate(word + " ")])
    assert parts and len(parts[0]) >= 48
    remaining = await aggregator.flush()
    assert "".join([*parts, remaining.text if remaining else ""]).strip() == sentence


@pytest.mark.asyncio
async def test_first_complete_indic_sentence_releases_early_and_later_chunks_stay_batched():
    aggregator = LocalSpeechAggregator(min_characters=48, first_chunk_characters=24)
    first = 'मैं आपके ऑर्डर की जानकारी नहीं देख सकता।'
    assert [part.text.strip() async for part in aggregator.aggregate(first + ' अ')] == [first]
    assert [part.text async for part in aggregator.aggregate('गला सवाल। फिर')] == []
    tail = await aggregator.flush()
    assert tail.text == 'अगला सवाल। फिर'
    # A new response gets the same low initial threshold.
    assert [part.text.strip() async for part in aggregator.aggregate(first + ' अ')] == [first]
    await aggregator.handle_interruption()
    assert await aggregator.flush() is None


@pytest.mark.asyncio
async def test_short_adjacent_sentences_start_synthesis_before_response_ends():
    aggregator = LocalSpeechAggregator(min_characters=24)
    emitted = [
        part.text async for part in aggregator.aggregate(
            'Yes. I can help with your account. What'
        )
    ]
    assert [part.strip() for part in emitted] == ['Yes. I can help with your account.']
    tail = await aggregator.flush()
    if tail: emitted.append(tail.text)
    assert [part.strip() for part in emitted] == ['Yes. I can help with your account.', 'What']
    assert await aggregator.flush() is None


@pytest.mark.asyncio
async def test_long_sentence_streams_before_response_ends():
    aggregator = LocalSpeechAggregator()
    sentence = 'Please tell me what happened when you tried to access your account.'
    emitted = [part.text async for part in aggregator.aggregate(sentence + ' Next')]
    assert [part.strip() for part in emitted] == [sentence]
    assert (await aggregator.flush()).text == 'Next'


@pytest.mark.asyncio
@pytest.mark.parametrize('clear', ['reset', 'handle_interruption'])
async def test_interruption_discards_both_pending_sentence_and_partial_tail(clear):
    aggregator = LocalSpeechAggregator()
    assert [part async for part in aggregator.aggregate('Yes. Old unfinished')] == []
    assert aggregator.text.text == 'Yes. Old unfinished'
    await getattr(aggregator, clear)()
    assert await aggregator.flush() is None
    assert [part async for part in aggregator.aggregate('New answer.')] == []
    assert (await aggregator.flush()).text == 'New answer.'

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('model', 'expected_calls'),
    [
        ('kokoro', ['Yes. I can help with your account.', 'What happened?']),
        ('indus-pocket-tts', ['Yes. I can help with your account.', 'What happened?']),
    ],
)
async def test_local_tts_releases_streaming_indus_sentence_early(monkeypatch, model, expected_calls):
    from pipecat.frames.frames import LLMFullResponseStartFrame, LLMTextFrame, LLMFullResponseEndFrame, TTSAudioRawFrame, TTSTextFrame
    from pipecat.services.speaches.tts import SpeachesTTSService, SpeachesTTSSettings
    from pipecat.tests.utils import run_test
    from api.services.pipecat.speaches_tts import SpeachesLiveTTSService

    calls = []
    async def synthesize(self, text, context_id):
        calls.append(text)
        yield TTSAudioRawFrame(b'\x01\x02' * 1600, self.sample_rate, 1, context_id=context_id)
    monkeypatch.setattr(SpeachesTTSService, 'run_tts', synthesize)
    service = SpeachesLiveTTSService(api_key='test', sample_rate=16000,
        settings=SpeachesTTSSettings(model=model, voice='hf_alpha'))
    text = 'Yes. I can help with your account. What happened?'
    frames, _ = await run_test(service, frames_to_send=[
        LLMFullResponseStartFrame(), LLMTextFrame(text), LLMFullResponseEndFrame(),
    ])
    assert [call.strip() for call in calls] == expected_calls
    assert "".join(calls).strip() == text
    assert [frame.text for frame in frames if isinstance(frame, TTSTextFrame)] == calls
    assert sum(len(frame.audio) for frame in frames if isinstance(frame, TTSAudioRawFrame)) == 3200 * len(expected_calls)
