"""Answer-level check with the default model (chosen in Settings). recall@k can't see prompt truncation or a model
that ignores the citation rules; this can. Manual, never in CI:

    docker compose exec api python -m evals.answer_check --paper "Attention Is All You Need" --workspace "Thesis"

Asks the default model one question about a small paper and one about a workspace, prints each answer, and
says whether its citations are valid: at least one [C…], and no [C…]/[N…] label beyond the sources the prompt had.
Exits 0 when both are valid, 1 when one isn't (or the LLM failed), 2 for an unknown paper or workspace.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.core import chat, llm_connections
from app.core.errors import DomainError
from app.models import Paper, Workspace
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm

DEFAULT_QUESTION = "What method does this work propose, and what does it improve on? Cite your sources."


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask the default model a question on a paper and on a workspace.")
    parser.add_argument("--paper", required=True, help="title prefix matching exactly one small, ready paper")
    parser.add_argument("--workspace", required=True, help="exact workspace name")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--database-url", default=settings.database_url)
    return parser.parse_args(argv)


def citation_problems(content: str, prepared: chat.Prepared) -> list[str]:
    labels = list(dict.fromkeys(chat._CITATION.findall(content)))
    limits = {"C": len(prepared.sources), "N": len(prepared.notes)}
    problems = [f"[{kind}{n}] is not one of the sources" for kind, n in labels if not 1 <= int(n) <= limits[kind]]
    return problems if any(kind == "C" for kind, _ in labels) else ["cites no passage", *problems]


async def ask(session: AsyncSession, scope: chat.Scope, name: str, question: str) -> bool:
    connection, model = await llm_connections.resolve(session, None)
    llm = build_llm(connection, model.name)
    prepared = await chat.prepare(session, scope, question)
    await session.commit()
    content = "".join([text async for text in llm.stream(prepared.system, prepared.prompt)])
    problems = citation_problems(content, prepared)
    print(f"== {name}: {llm.model} on {llm.connection_name}, {len(prepared.sources)} passages, "
          f"{len(prepared.notes)} notes\n{content}")
    print(f"-> {'; '.join(problems) or 'citations valid'}\n")
    return not problems


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    engine = create_async_engine(args.database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            papers = list(await session.scalars(select(Paper).where(Paper.title.istartswith(args.paper))))
            workspace = await session.scalar(select(Workspace).where(Workspace.name == args.workspace))
            if len(papers) != 1 or workspace is None:
                print(f"need exactly one paper {args.paper!r} ({len(papers)} found) and workspace {args.workspace!r}")
                return 2
            valid = [
                await ask(session, chat.Scope(paper_id=papers[0].id), papers[0].title, args.question),
                await ask(session, chat.Scope(workspace_id=workspace.id), workspace.name, args.question),
            ]
    except (DomainError, LLMError, LLMUnavailable) as exc:
        print(f"answer check failed: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    return 0 if all(valid) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
