from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://paperlab:paperlab@db:5432/paperlab"
    redis_url: str = "redis://redis:6379"
    pdf_dir: Path = Path("/data/pdfs")
    # Fixed by the vector(768) column; changing it means a migration and a full re-embed.
    embed_model: str = "nomic-embed-text-v1.5"


settings = Settings()
