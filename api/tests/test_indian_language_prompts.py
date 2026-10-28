import pytest
from api.services.configuration.language_normalizer import normalize_language_code, speech_language_instruction, get_default_piper_voice_for_language
from api.services.pipecat.service_factory import _speaches_transcription_prompt


@pytest.mark.parametrize('name,code', [
    ('Assamese','as'),('Bengali','bn'),('Bodo','brx'),('Dogri','doi'),('Gujarati','gu'),
    ('Hindi','hi'),('Kannada','kn'),('Kashmiri','ks'),('Konkani','kok'),('Maithili','mai'),
    ('Malayalam','ml'),('Manipuri','mni'),('Marathi','mr'),('Nepali','ne'),('Odia','or'),
    ('Punjabi','pa'),('Sanskrit','sa'),('Santali','sat'),('Sindhi','sd'),('Tamil','ta'),
    ('Telugu','te'),('Urdu','ur'),
])
def test_every_scheduled_indian_language_has_a_code_switching_prompt(name,code):
    assert normalize_language_code(name) == code
    instruction = speech_language_instruction(code)
    assert name in instruction
    assert 'English' in instruction
    assert 'only one language' in instruction or 'only hindi' in instruction.casefold()
    assert "Match the caller's language" in instruction


def test_hindi_agent_answers_english_in_english_and_never_claims_hindi_only():
    instruction = speech_language_instruction('hi')
    assert 'answer English in English' in instruction
    assert 'never claim that you understand or speak only hindi' in instruction.casefold()


@pytest.mark.parametrize('language', ['multi','auto','default',None,'en','ta','bn'])
def test_automatic_and_other_local_recognition_is_not_biased_to_hindi(language):
    prompt = _speaches_transcription_prompt(language, ['Kodewaves'])
    assert 'Hindi and English conversation' not in prompt
    assert 'language switches' in prompt
    assert 'Kodewaves' in prompt


@pytest.mark.parametrize('language', ['brx','doi','kok','sa','sd','ur','gu','kn'])
def test_missing_local_language_voice_does_not_silently_select_american_english(language):
    with pytest.raises(ValueError, match='No Piper voice'):
        get_default_piper_voice_for_language(language)
