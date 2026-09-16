from app.config import Settings


def test_anthropic_without_a_key_no_longer_stops_the_app(monkeypatch):
    # Keys live in model connections now: a missing ANTHROPIC_API_KEY must not crash the API or the worker.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert Settings(llm_provider="anthropic").anthropic_api_key is None


def test_anthropic_max_tokens_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "8192")

    assert Settings().anthropic_max_tokens == 8192
    assert Settings.model_fields["anthropic_max_tokens"].default == 64_000


def test_discovery_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("DISCOVERY_PROVIDER", "fake")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "secret-key")

    assert (Settings().discovery_provider, Settings().semantic_scholar_api_key) == ("fake", "secret-key")
    assert Settings.model_fields["discovery_provider"].default == "live"
    assert Settings.model_fields["semantic_scholar_api_key"].default == ""
