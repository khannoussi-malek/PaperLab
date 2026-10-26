import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from app.providers.search_model import SHIPPED

# A compose project whose name ends in this is a test stack (scripts/e2e-stack.sh): the only place fakes run (D273).
TEST_STACK_SUFFIX = "-e2e"


logger = logging.getLogger(__name__)

DEFAULT_EMBED_THREADS = min(4, os.cpu_count() or 1)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://paperlab:paperlab@db:5432/paperlab"
    redis_url: str = "redis://redis:6379"
    pdf_dir: Path = Path("/data/pdfs")
    # The name chunks record with their vectors (D137). It follows the built-in search model's shipped variant
    # (providers/search_model.py) and is not meant to be set; tests set it to "test". vector(768) fixes the size.
    embed_model: str = SHIPPED.name
    # Where the built-in search model is downloaded (the `models` volume). Empty of it until the user downloads it.
    models_dir: Path = Path("/models")
    # Threads the built-in search model's ONNX session may use (EMBED_THREADS). Unset, it takes up to four cores: left
    # to itself it takes every core, which on a busy machine is slower than a few. Below 1 or not a whole number: the
    # default, with a warning.
    embed_threads: int = DEFAULT_EMBED_THREADS
    # How many candidates the HNSW index considers for a workspace or library search (HNSW_EF_SEARCH). pgvector's
    # default 40 missed ~4% of a 146-paper workspace's true top 8; 100 brought it to ≥ 0.99 for ~13 ms at p95
    # (M8 step 2). A single paper never uses the index: it sorts that paper's chunks exactly.
    hnsw_ef_search: int = Field(100, ge=1, le=1000)
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
    # The built frontend's folder (the release image sets /app/web). Empty: the API serves no page, as in development,
    # where Vite serves the frontend on :5180.
    frontend_dist: str = ""
    # The compose project this process belongs to, from `PAPERLAB_STACK: ${COMPOSE_PROJECT_NAME}` in the compose
    # files. Fake providers run only on a test stack, whose name ends in -e2e (D273): the owner's library lives in
    # `paperlab` (or `paperlab-app`) and must never hold a fake model's rows.
    paperlab_stack: str = ""
    # The Tectonic binary that compiles manuscripts (TECTONIC_BIN), whether it may only use its cached bundle (-C), and
    # where that cache lives. TECTONIC_USER names the unprivileged account it runs as in the images (None on the host).
    tectonic_bin: str = "tectonic"
    tectonic_only_cached: bool = False
    tectonic_cache_dir: Path | None = None
    tectonic_user: str | None = None

    @field_validator("embed_threads", mode="before")
    @classmethod
    def _embed_threads_at_least_one(cls, value):
        try:
            threads = int(str(value).strip())
        except ValueError:
            threads = 0
        if threads < 1:
            logger.warning("EMBED_THREADS=%r is not a whole number from 1 up; using %d", value, DEFAULT_EMBED_THREADS)
            return DEFAULT_EMBED_THREADS
        return threads

    @model_validator(mode="after")
    def _fake_only_on_a_test_stack(self):
        fake = "fake" in (self.llm_provider, self.discovery_provider)
        if fake and not self.paperlab_stack.endswith(TEST_STACK_SUFFIX):
            raise ValueError(
                "Fake providers run only on a test stack, and this is "
                f"{self.paperlab_stack or 'not a compose stack'!r}. "
                "Start the test stack with scripts/e2e-stack.sh up. If your shell or .env sets "
                "LLM_PROVIDER or DISCOVERY_PROVIDER to fake, unset it."
            )
        return self


settings = Settings()
