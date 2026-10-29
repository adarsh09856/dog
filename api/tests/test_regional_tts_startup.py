import io
from types import SimpleNamespace

import pytest

from api.local_models.indic_vits import app as tts


def prepare_startup(monkeypatch, tmp_path):
    for filename in ("model.onnx", "tokens.txt"):
        (tmp_path / filename).touch()
    monkeypatch.setattr(tts, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(tts, "INDUS_ENDPOINT", "http://indus/v1")
    monkeypatch.setattr(tts, "RASA_MODEL", None)
    monkeypatch.setattr(tts, "INDUS_READY", False)
    monkeypatch.setattr(tts, "sherpa_onnx", SimpleNamespace(
        OfflineTtsConfig=lambda **kw: kw,
        OfflineTtsModelConfig=lambda **kw: kw,
        OfflineTtsVitsModelConfig=lambda **kw: kw,
        OfflineTts=lambda config: object(),
    ))
    monkeypatch.setattr(tts.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(
        b'{"data":[{"id":"indus-pocket-tts","installed":true}]}'
    ))


def test_startup_primes_every_regional_speaker_before_returning(monkeypatch, tmp_path):
    prepare_startup(monkeypatch, tmp_path)
    warmed = []
    monkeypatch.setattr(tts, "_warm_streaming_voice", lambda text, voice: warmed.append((voice, text)))
    tts._load()
    assert warmed == [(voice, tts.PREVIEWS[spec[1]]) for voice, spec in tts.RASA_SPEAKERS.items()]
    assert len(warmed) == 20


@pytest.mark.asyncio
async def test_failed_regional_warmup_prevents_application_startup(monkeypatch, tmp_path):
    prepare_startup(monkeypatch, tmp_path)

    def warm(text, voice):
        if voice == "ASM_F":
            raise RuntimeError("regional synthesis failed")

    monkeypatch.setattr(tts, "_warm_streaming_voice", warm)
    with pytest.raises(RuntimeError, match="regional synthesis failed"):
        async with tts.lifespan(None):
            pytest.fail("Application became ready despite failed voice warmup")
