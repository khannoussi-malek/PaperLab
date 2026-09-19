from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

from app.providers.search_model import SHIPPED


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://paperlab:paperlab@db:5432/paperlab"
    redis_url: str = "redis://redis:6379"
    pdf_dir: Path = Path("/data/pdfs")
    # The name chunks record with their vectors (D137). It follows the built-in search model's shipped variant
    # (providers/search_model.py) and is not meant to be set; tests set it to "test". vector(768) fixes the size.
    embed_model: str = SHIPPED.name
    # Where the built-in search model is downloaded (the `models` volume). Empty of it until the user downloads it.
    models_dir: Path = Path("/models")
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
    # Sent as `x-api-key` to Semantic Scholar (Similar papers, arXiv lookups, free PDF links). Empty uses its shared,
    # often busy pool.
    semantic_scholar_api_key: str = ""
    # `fake` serves Find papers and Similar from three offline papers (the E2E stack), as LLM_PROVIDER=fake does chat.
    discovery_provider: Literal["live", "fake"] = "live"
    # The folder `docker compose up` ran in, from `PAPERLAB_DIR: ${PWD:-}` in docker-compose.yml (Compose uses its own
    # working directory when the shell exports no PWD). Empty outside Compose. Connect Claude prefills with it.
    paperlab_dir: str = ""


settings = Settings()
