"""A workspace package's chat answers (M35b2): the workspace's own chat answers, exported with the passages they cited
(answers.json), and written back on import as chat answers of the new workspace.

An answer keeps its M33 snapshot, so its citations still open after import. Its citation slots get fresh random ids:
no passage with those ids exists here, so each citation takes the snapshot's fallback (chat.snapshot_passages)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills import FULL
from app.models import LLMOutput


async def export_rows(session: AsyncSession, workspace_id: uuid.UUID, keys: dict[uuid.UUID, str]) -> tuple[list, int]:
    """The workspace's chat answers as answers.json rows, and how many were left out. An answer saved before M33 has no
    snapshot, so nothing its citations could open from: it is counted, not exported. A paper's own answers stay out."""
    query = select(LLMOutput).where(LLMOutput.workspace_id == workspace_id, LLMOutput.kind == "chat")
    outputs = list(await session.scalars(query.order_by(LLMOutput.created_at)))
    kept = [output for output in outputs if output.source_snapshot is not None]
    return [_row(output, keys) for output in kept], len(outputs) - len(kept)


def _row(output: LLMOutput, keys: dict[uuid.UUID, str]) -> dict:
    position = {chunk_id: number for number, chunk_id in enumerate(output.source_chunks, start=1)}
    return {
        "question": output.question,
        "content": output.content,
        "model": output.model,
        "connection_name": output.connection_name,
        "prompt_version": output.prompt_version,
        "skill_label": output.skill_label,
        "skill_version": output.skill_version,
        "lens": output.lens,
        "whole_paper": output.whole_paper,
        "notes_used": output.notes_used,
        "notes_total": output.notes_total,
        "created_at": output.created_at.isoformat(),
        "slots": len(output.source_chunks),
        "cited": [f"C{position[chunk_id]}" for chunk_id in output.cited_chunks if chunk_id in position],
        # ponytail: a snapshot passage of a paper that left the workspace has no package key, so it is left out.
        "snapshot": [
            {
                "label": entry["label"],
                "paper": keys[uuid.UUID(entry["paper_id"])],
                "page": entry["page"],
                "section": entry["section"],
                "text": entry["text"],
                "from_abstract": entry["from_abstract"],
            }
            for entry in output.source_snapshot
            if uuid.UUID(entry["paper_id"]) in keys
        ],
    }


def _aware(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _snapshot_entry(entry: dict, ids: dict[str, uuid.UUID]) -> dict:
    return {
        "label": entry["label"],
        "paper_id": str(ids[entry["paper"]]),
        "page": entry["page"],
        "section": entry["section"],
        "text": entry["text"],
        "from_abstract": entry["from_abstract"],
    }


async def write_rows(
    session: AsyncSession, workspace_id: uuid.UUID, rows: list[dict], ids: dict[str, uuid.UUID]
) -> int:
    """Each answer as a chat answer of the new workspace, with the package's time. `ids` maps each package paper key to
    the paper here; a snapshot passage of a key the package does not list is dropped."""
    for row in rows:
        slots = [uuid.uuid4() for _ in range(row["slots"])]
        session.add(
            LLMOutput(
                workspace_id=workspace_id,
                kind="chat",
                question=row["question"],
                content=row["content"],
                model=row["model"],
                connection_name=row["connection_name"],
                prompt_version=row["prompt_version"],
                skill_label=row["skill_label"],
                skill_version=row["skill_version"],
                lens=row.get("lens", FULL),  # a package from before lens chat has none
                whole_paper=row["whole_paper"],
                notes_used=row["notes_used"],
                notes_total=row["notes_total"],
                source_chunks=slots,
                cited_chunks=[slots[int(label[1:]) - 1] for label in row["cited"]],
                source_snapshot=[_snapshot_entry(e, ids) for e in row["snapshot"] if e["paper"] in ids],
                source_notes=[],
                created_at=_aware(row["created_at"]),
            )
        )
    await session.flush()
    return len(rows)
