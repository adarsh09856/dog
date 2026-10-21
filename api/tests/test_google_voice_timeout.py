from api.services.pipecat import service_factory as factory


def test_google_voice_bounds_connection_and_sdk_retries_without_changing_model(monkeypatch):
    received = {}
    def capture(self, **kwargs): received.update(kwargs)
    monkeypatch.setattr(factory.GoogleLLMService, '__init__', capture)
    factory.KodewavesGoogleLLMService(api_key='synthetic', model='selected-model')
    assert received['model'] == 'selected-model'
    assert received['http_options'].timeout == 12000
    assert received['http_options'].retry_options.attempts == 1
    assert received['stream_idle_timeout_secs'] == 12
    assert received['retry_on_timeout'] is False


def test_explicit_internal_google_http_configuration_is_preserved(monkeypatch):
    received = {}
    def capture(self, **kwargs): received.update(kwargs)
    monkeypatch.setattr(factory.GoogleLLMService, '__init__', capture)
    options = object()
    factory.KodewavesGoogleLLMService(api_key='synthetic', http_options=options, stream_idle_timeout_secs=7)
    assert received['http_options'] is options
    assert received['stream_idle_timeout_secs'] == 7
