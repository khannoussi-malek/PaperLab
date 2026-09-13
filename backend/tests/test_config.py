import pytest
from pydantic import ValidationError

from app.config import Settings


def test_anthropic_provider_needs_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="LLM_PROVIDER=anthropic needs ANTHROPIC_API_KEY"):
        Settings(llm_provider="anthropic")
    assert Settings(llm_provider="anthropic", anthropic_api_key="sk-test").anthropic_api_key == "sk-test"
