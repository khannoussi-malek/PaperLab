from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://paperlab:paperlab@db:5432/paperlab"
    redis_url: str = "redis://redis:6379"
    pdf_dir: Path = Path("/data/pdfs")
    # Fixed by the vector(768) column; changing it means a migration and a full re-embed.
    # Keep the org prefix: "nomic-embed-text-v1.5" alone is not a Hugging Face repo.
    embed_model: str = "nomic-ai/nomic-embed-text-v1.5"
    # `fake` swaps every provider call made through a model connection for a scripted one (the E2E stack).
    # With LLM_MODEL, OLLAMA_URL and ANTHROPIC_API_KEY it also seeds the first connection while there are none;
    # after that the database decides which model answers.
    llm_provider: Literal["ollama", "anthropic", "fake"] = "ollama"
    llm_model: str = "qwen3:8b"
    ollama_url: str = "http://host.docker.internal:11434"
    anthropic_api_key: str | None = None
    # Streaming, so a generous cap costs nothing when unused and never truncates a long answer.
    anthropic_max_tokens: int = 64_000
    # Sent as `mailto` on every OpenAlex request. Empty turns OpenAlex off: enrichment then uses only the PDF.
    openalex_mailto: str = ""


settings = Settings()
