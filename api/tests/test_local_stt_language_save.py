"""Local recognizer settings must match the installed service inventory."""

from api.services.configuration.stt_capabilities import local_stt_language_error


def test_installed_language_aliases_and_auto_are_accepted():
    manifest = {"supports_auto_detect": True, "languages": ["hi-IN", "en_IN", "ta"]}
    for language in ("Hindi", "hi", "en-IN", "en_IN", "ta", "multi", "auto"):
        assert local_stt_language_error(language, manifest) is None


def test_missing_languages_and_unavailable_auto_are_rejected():
    manifest = {"supports_auto_detect": True, "languages": ["hi", "en"]}
    for language in ("ur", "te", ""):
        assert local_stt_language_error(language, manifest)
    assert local_stt_language_error("multi", {"supports_auto_detect": True, "languages": []})
    assert local_stt_language_error("auto", {"supports_auto_detect": False, "languages": ["hi"]})
