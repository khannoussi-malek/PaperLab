"""Retrieval eval: recall@k for the questions in evals/questions.yaml.

    docker compose exec api python -m evals.run [--variant int8|full]
    cd backend && uv run python -m evals.run --database-url postgresql+asyncpg://paperlab:paperlab@localhost:5433/paperlab

A question is a hit at k when one of its top-k chunks is on an expected page and contains that entry's
phrase, ignoring case and whitespace. Exits 2 on a malformed questions file or an ambiguous/unknown paper.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.core.retrieval import RetrievedChunk, retrieve
from app.models import Paper
from app.providers import embedding, search_model

QUESTIONS = Path(__file__).with_name("questions.yaml")
KS = (4, 8)


class Expected(BaseModel):
    page: int = Field(ge=1)
    contains: str = Field(min_length=1)


class Question(BaseModel):
    paper: str = Field(min_length=1)  # title prefix: uploads don't keep the original filename
    question: str = Field(min_length=1)
    expected: list[Expected] = Field(min_length=1)


class QuestionFile(BaseModel):
    questions: list[Question] = Field(min_length=1)


class EvalError(Exception):
    pass


def load_questions(path: Path) -> list[Question]:
    try:
        return QuestionFile.model_validate(yaml.safe_load(path.read_text())).questions
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise EvalError(f"{path}: {exc}") from exc


def normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def is_hit(chunks: list[RetrievedChunk], expected: list[Expected]) -> bool:
    return any(c.page == e.page and normalize(e.contains) in normalize(c.text) for c in chunks for e in expected)


async def resolve_papers(session: AsyncSession, questions: list[Question]) -> dict[str, uuid.UUID]:
    ids = {}
    for prefix in sorted({q.paper for q in questions}):
        matches = list(await session.scalars(select(Paper.id).where(Paper.title.istartswith(prefix))))
        if len(matches) != 1:
            raise EvalError(f"paper {prefix!r} matches {len(matches)} papers; it must match exactly one")
        ids[prefix] = matches[0]
    return ids


async def evaluate(session: AsyncSession, questions: list[Question], embedder, ks=KS) -> dict[int, list[Question]]:
    """The questions missed at each k."""
    paper_ids = await resolve_papers(session, questions)
    missed = {k: [] for k in ks}
    for q in questions:
        chunks = await retrieve(session, q.question, paper_ids=[paper_ids[q.paper]], k=max(ks), embedder=embedder)
        for k in ks:
            if not is_hit(chunks[:k], q.expected):
                missed[k].append(q)
    return missed


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print retrieval recall@k for evals/questions.yaml.")
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--variant", choices=sorted(search_model.VARIANTS), help="default: the one PaperLab ships")
    args = parser.parse_args(argv)
    try:
        questions = load_questions(args.questions)
        embedder = embedding.load(search_model.VARIANTS.get(args.variant))
        if embedder is None:
            raise EvalError(f"no search model in {settings.models_dir}: download it in Settings → Search first")
        engine = create_async_engine(args.database_url)
        try:
            async with AsyncSession(engine) as session:
                missed = await evaluate(session, questions, embedder)
        finally:
            await engine.dispose()
    except EvalError as exc:
        print(f"eval error: {exc}", file=sys.stderr)
        return 2

    total = len(questions)
    for k, misses in missed.items():
        print(f"recall@{k}: {(total - len(misses)) / total:.2f} ({total - len(misses)}/{total})")
    for q in missed[max(missed)]:
        print(f"  missed@{max(missed)}: [{q.paper}] {q.question}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
