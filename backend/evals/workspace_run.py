"""Workspace retrieval eval: for each question in evals/workspace_questions.yaml, is every passage it needs in the
workspace's top k? HYBRID_SEARCH decides vector-only or hybrid, as it does for chat.

    docker compose exec api python -m evals.workspace_run
    docker compose exec -e HYBRID_SEARCH=true api python -m evals.workspace_run
    docker compose exec api python -m evals.workspace_run --words off   # vectors only, whatever the switch says
    docker compose exec api python -m evals.workspace_run --chat        # what workspace chat would send

Exits 2 on a malformed file, an unknown workspace or paper, or a passage that no chunk of its paper holds: a typo in
the key would otherwise count as a miss forever.
"""

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.core import chat, retrieval
from app.core.retrieval import RetrievedChunk, retrieve
from app.models import Chunk, Paper, Workspace, workspace_papers
from app.providers import embedding
from evals.run import KS, EvalError, normalize

QUESTIONS = Path(__file__).with_name("workspace_questions.yaml")
CHAT = 0  # the "k" of chat mode: every passage chat would send, after its likely papers, pool and budget


class Passage(BaseModel):
    paper: str = Field(min_length=1)  # the exact title, else a title prefix only one workspace paper has
    contains: str = Field(min_length=1)


class Question(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    seen: bool = False  # its retrieval results were looked at before the key was written
    needs: list[list[Passage]]  # every need must be met; a need is met by any one of its passages; [] = not scored

    def model_post_init(self, _context) -> None:
        if any(not need for need in self.needs):
            raise ValueError(f"{self.id}: a need lists no passage")


class QuestionFile(BaseModel):
    workspace: str = Field(min_length=1)
    questions: list[Question] = Field(min_length=1)


@dataclass(frozen=True)
class Result:
    question: Question
    answered: dict[int, bool]  # every need met in the top k
    met: dict[int, int]  # how many of its needs were


def load_questions(path: Path) -> QuestionFile:
    try:
        return QuestionFile.model_validate(yaml.safe_load(path.read_text()))
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise EvalError(f"{path}: {exc}") from exc


def _resolve(title: str, papers: dict[str, uuid.UUID]) -> uuid.UUID:
    """The exact title (ignoring case), else the one title it starts: "ELIQUIS" is also a prefix of "Eliquis, INN"."""
    exact = [pid for t, pid in papers.items() if t.casefold() == title.casefold()]
    matches = exact or [pid for t, pid in papers.items() if t.casefold().startswith(title.casefold())]
    if len(matches) != 1:
        raise EvalError(f"paper {title!r} matches {len(matches)} papers of the workspace; it must match exactly one")
    return matches[0]


async def _key(session: AsyncSession, key: QuestionFile) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """The workspace id and each named paper's id, after checking that every passage is in its paper's text."""
    workspace_id = await session.scalar(select(Workspace.id).where(Workspace.name == key.workspace))
    if workspace_id is None:
        raise EvalError(f"workspace {key.workspace!r} not found")
    members = select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == workspace_id)
    rows = await session.execute(select(Paper.id, Paper.title).where(Paper.id.in_(members)))
    papers = {title: pid for pid, title in rows}
    ids = {p.paper: _resolve(p.paper, papers) for q in key.questions for need in q.needs for p in need}
    texts: dict[uuid.UUID, list[str]] = {}
    chunks = select(Chunk.paper_id, Chunk.text).where(Chunk.paper_id.in_(ids.values()))
    for paper_id, text in await session.execute(chunks):
        texts.setdefault(paper_id, []).append(normalize(text))
    for q in key.questions:
        for p in (p for need in q.needs for p in need):
            if not any(normalize(p.contains) in t for t in texts.get(ids[p.paper], [])):
                raise EvalError(f"{q.id}: no chunk of {p.paper!r} holds {p.contains!r}")
    return workspace_id, ids


def _met(chunks: list[RetrievedChunk], need: list[Passage], ids: dict[str, uuid.UUID]) -> bool:
    return any(c.paper_id == ids[p.paper] and normalize(p.contains) in normalize(c.text) for c in chunks for p in need)


async def evaluate(
    session: AsyncSession, key: QuestionFile, embedder, ks=KS, words: bool | None = None, chat_path: bool = False
) -> list[Result]:
    """One result per scored question (those with needs), in file order. `words` goes to retrieve as is; `chat_path`
    scores the passages workspace chat would send instead of the top k (its one "k" is CHAT)."""
    workspace_id, ids = await _key(session, key)
    if chat_path:
        ks = (CHAT,)
        members = select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == workspace_id)
        ready = list(await session.scalars(members))
    results = []
    for q in (q for q in key.questions if q.needs):
        if chat_path:
            chunks = (await chat._workspace_sources(session, ready, q.question, embedder, chat.FULL_LENS))[0]
        else:
            chunks = await retrieve(
                session, q.question, workspace_id=workspace_id, k=max(ks), embedder=embedder, words=words
            )
        met = {k: sum(_met(chunks[: k or None], need, ids) for need in q.needs) for k in ks}
        results.append(Result(q, answered={k: met[k] == len(q.needs) for k in ks}, met=met))
    return results


async def check_key(session: AsyncSession, key: QuestionFile) -> str:
    """Checks the key against the papers without searching; raises EvalError like evaluate()."""
    await _key(session, key)
    scored = sum(1 for q in key.questions if q.needs)
    passages = sum(len(need) for q in key.questions for need in q.needs)
    return f"key ok: {scored} scored questions, {passages} passages, all in their papers"


async def _check_only(database_url: str, key: QuestionFile) -> int:
    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine) as session:
            print(await check_key(session, key))
    finally:
        await engine.dispose()
    return 0


def _share(results: list[Result], k: int) -> str:
    hits = sum(r.answered[k] for r in results)
    return f"{hits / len(results):.2f} ({hits}/{len(results)})" if results else "n/a (0/0)"


def summary(results: list[Result], k: int) -> str:
    unseen = [r for r in results if not r.question.seen]
    seen = [r for r in results if r.question.seen]
    return f"recall@{k or 'chat'}: {_share(results, k)} · unseen {_share(unseen, k)} · seen {_share(seen, k)}"


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print workspace recall@k for evals/workspace_questions.yaml.")
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--check-key", action="store_true", help="only check the key against the papers; no search")
    parser.add_argument("--words", choices=("on", "off"), help="force the keyword half on or off (default: the switch)")
    parser.add_argument("--chat", action="store_true", help="score what workspace chat would send, not the top k")
    args = parser.parse_args(argv)
    try:
        key = load_questions(args.questions)
        if args.check_key:
            return await _check_only(args.database_url, key)
        embedder = embedding.load()
        if embedder is None:
            raise EvalError(f"no search model in {settings.models_dir}: download it in Settings → Search first")
        engine = create_async_engine(args.database_url)
        try:
            async with AsyncSession(engine) as session:
                words = None if args.words is None else args.words == "on"
                results = await evaluate(session, key, embedder, words=words, chat_path=args.chat)
                hybrid = await retrieval.hybrid_on(session) if words is None else words
        finally:
            await engine.dispose()
    except EvalError as exc:
        print(f"eval error: {exc}", file=sys.stderr)
        return 2

    ks = (CHAT,) if args.chat else KS
    print("search: chat's path (likely papers, hybrid, budget)" if args.chat else
          f"search: {'hybrid' if hybrid else 'vector only'}")
    for r in results:
        cells = "  ".join(f"@{k or 'chat'} {r.met[k]}/{len(r.question.needs)}" for k in ks)
        print(f"  {r.question.id}{' (seen)' if r.question.seen else '       '}  {cells}  {r.question.question[:70]}")
    for k in ks:
        print(summary(results, k))
    unscored = [q.id for q in key.questions if not q.needs]
    print(f"not scored (no source in these papers): {' '.join(unscored) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
