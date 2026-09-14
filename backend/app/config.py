from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://paperlab:paperlab@db:5432/paperlab"
    redis_url: str = "redis://redis:6379"
    pdf_dir: Path = Path("/data/pdfs")
    # Fixed by the vector(768) column; changing it means a migration and a full re-embed.
    # Keep the org prefix: "nomic-embed-text-v1.5" alone is not a Hugging Face repo.
    embed_model: str = "nomic-ai/nomic-embed-text-v1.5"
    llm_provider: Literal["ollama", "anthropic", "fake"] = "ollama"
    llm_model: str = "qwen3:8b"
    ollama_url: str = "http://host.docker.internal:11434"
    anthropic_api_key: str | None = None

    @model_validator(mode="after")
    def anthropic_needs_a_key(self) -> Self:
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("LLM_PROVIDER=anthropic needs ANTHROPIC_API_KEY")
        return self


settings = Settings()
