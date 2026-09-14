import math
import os
import random
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db import get_session
from app.main import create_app

# The compose Postgres, published on the host. Every test runs inside a transaction that is
# rolled back afterwards, so tests can share the dev database without leaving rows behind.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://paperlab:paperlab@localhost:5433/paperlab"
)

BODY_TEXT = "The quick brown fox jumps over the lazy dog near the river bank today. " * 3


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def database_url():
    return TEST_DATABASE_URL


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # create_savepoint: a service's session.commit() only releases a savepoint.
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as test_session:
            yield test_session
        await transaction.rollback()
    await engine.dispose()


class FakeArq:
    """Records enqueued jobs instead of talking to Redis (ASGITransport skips the lifespan)."""

    def __init__(self):
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name: str, *args) -> None:
        self.jobs.append((name, *args))


@pytest.fixture
def arq():
    return FakeArq()


def unit_vector(seed: str) -> list[float]:
    """A fixed pseudo-random 768-d unit vector per seed."""
    rng = random.Random(seed)
    vector = [rng.gauss(0, 1) for _ in range(768)]
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector]


class FakeEmbedder:
    """Stands in for SentenceTransformer: records every encode call instead of running a model.

    A text embeds to `vectors[text]` when a test set one, otherwise to `unit_vector(text)`.
    """

    def __init__(self):
        self.calls: list[tuple[list[str], dict]] = []
        self.vectors: dict[str, list[float]] = {}

    def encode(self, texts: list[str], **kwargs):
        self.calls.append((list(texts), kwargs))
        return np.array([self.vectors.get(t) or unit_vector(t) for t in texts], dtype=np.float32)


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def pdf_dir(tmp_path, monkeypatch):
    directory = tmp_path / "pdfs"
    monkeypatch.setattr(settings, "pdf_dir", directory)
    return directory


@pytest.fixture
def app(session, arq, pdf_dir):
    """The app bound to the test session. Tests add their own dependency_overrides (e.g. the LLM)."""
    application = create_app()
    application.dependency_overrides[get_session] = lambda: session
    application.state.arq = arq
    return application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def _write_pdf(path: Path, pages: list[list[tuple]], metadata: dict[str, str] | None = None) -> Path:
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page()
        for kind, *args in items:
            if kind == "text":
                point, text, size, bold = args
                page.insert_text(point, text, fontsize=size, fontname="hebo" if bold else "helv")
            elif kind == "box":
                rect, text = args
                page.insert_textbox(pymupdf.Rect(*rect), text, fontsize=11)
            elif kind == "rotated":
                point, text = args
                page.insert_text(point, text, fontsize=11, rotate=90)
    if metadata:
        doc.set_metadata(metadata)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_pdf(tmp_path) -> Path:
    """Two pages: a bold 18pt title and a bold section heading, body prose, and an arXiv-style rotated stamp."""
    stamp = ("rotated", (40, 700), "arXiv:1234.5678v1 sidebar stamp")
    return _write_pdf(
        tmp_path / "sample.pdf",
        [
            [("text", (72, 72), "Deep Paper Title", 18, True), ("box", (72, 100, 520, 300), BODY_TEXT), stamp],
            [("text", (72, 72), "2 Method", 11, True), ("box", (72, 100, 520, 300), BODY_TEXT), stamp],
        ],
    )


@pytest.fixture
def titled_pdf(tmp_path) -> Path:
    return _write_pdf(
        tmp_path / "titled.pdf",
        [[("text", (72, 72), "Largest Font Line", 18, True), ("box", (72, 100, 520, 300), BODY_TEXT)]],
        metadata={"title": "Title From Metadata"},
    )


BERT_TITLE_LINES = ("BERT: Pre-training of Deep Bidirectional Transformers for", "Language Understanding")


@pytest.fixture
def arxiv_pdf(tmp_path) -> Path:
    """BERT's first page as arXiv serves it: a two-line title whose second line is its own block (K1), the authors,
    the rotated arXiv stamp, and no DOI or embedded metadata."""
    return _write_pdf(
        tmp_path / "arxiv.pdf",
        [
            [
                ("text", (72, 72), BERT_TITLE_LINES[0], 14, True),
                ("text", (190, 100), BERT_TITLE_LINES[1], 14, True),
                ("text", (72, 130), "Jacob Devlin  Ming-Wei Chang  Kenton Lee  Kristina Toutanova", 11, False),
                ("box", (72, 160, 520, 360), BODY_TEXT),
                ("rotated", (40, 700), "arXiv:1810.04805v2 [cs.CL] 24 May 2019"),
            ]
        ],
    )


@pytest.fixture
def doi_pdf(tmp_path) -> Path:
    """A journal-style first page that prints its DOI, with an embedded author, keywords and creation date."""
    return _write_pdf(
        tmp_path / "doi.pdf",
        [
            [
                ("text", (72, 72), "A Paper With a Printed DOI", 14, True),
                ("box", (72, 100, 520, 300), BODY_TEXT),
                ("text", (72, 760), "https://doi.org/10.18653/v1/N19-1423.", 8, False),
            ]
        ],
        metadata={
            "author": "Jacob Devlin; Ming-Wei Chang",
            "keywords": "language models, pre-training",
            "creationDate": "D:20190528000751Z",
        },
    )


@pytest.fixture
def blank_pdf(tmp_path) -> Path:
    """Stands in for a scanned PDF: a page with no text layer."""
    return _write_pdf(tmp_path / "blank.pdf", [[]])
