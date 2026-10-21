"""Background warm-up must not compete with a caller's resident model."""
import pytest

from scripts import warm_local_ollama as warmup


@pytest.mark.parametrize('resident', [{'custom:4b'}, {'default:2b'}])
def test_warmup_never_replaces_a_resident_model(monkeypatch, resident):
    calls = []
    monkeypatch.setattr(warmup, 'MODELS', ('default:2b',))
    monkeypatch.setattr(warmup, '_model_names', lambda path, _: {'default:2b', 'custom:4b'} if path == '/api/tags' else set(resident))
    monkeypatch.setattr(warmup, '_request', lambda *args: calls.append(args))
    monkeypatch.setattr(warmup.time, 'sleep', lambda _: (_ for _ in ()).throw(InterruptedError()))
    with pytest.raises(InterruptedError):
        warmup.keep_models_warm()
    assert calls == []


def test_empty_server_warms_only_one_model_per_pass(monkeypatch):
    calls = []
    monkeypatch.setattr(warmup, 'MODELS', ('first:2b', 'second:4b'))
    monkeypatch.setattr(warmup, '_model_names', lambda path, _: {'first:2b', 'second:4b'} if path == '/api/tags' else set())
    monkeypatch.setattr(warmup, '_request', lambda *args: calls.append(args))
    monkeypatch.setattr(warmup.time, 'sleep', lambda _: (_ for _ in ()).throw(InterruptedError()))
    with pytest.raises(InterruptedError):
        warmup.keep_models_warm()
    assert len(calls) == 1
    assert calls[0][0] == '/api/generate'
    assert calls[0][1]['model'] == 'first:2b'
