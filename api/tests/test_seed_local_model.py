from unittest.mock import patch

from scripts.seed_platform import seed_local_ai_model


def test_cached_local_model_skips_network_pull():
    class Installed:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    with patch("urllib.request.urlopen", return_value=Installed()) as request:
        seed_local_ai_model()

    assert request.call_count == 1
    assert request.call_args.args[0].full_url.endswith("/api/show")
