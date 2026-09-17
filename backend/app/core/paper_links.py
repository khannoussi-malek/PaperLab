"""The links the owner draws between two papers, with their own label (P6, D110).

The one stored link kind: nothing can derive "builds on" or "contradicts". One link per pair whichever way it was
drawn, enforced by the unique index on (least, greatest) as well as here.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.papers import get_paper
from app.models import PaperLink

LABEL_MAX_CHARS = 80

ALREADY_LINKED = "These papers are already linked. Edit that link instead."
EMPTY_LABEL = 'A link needs a short label, like "builds on".'
LABEL_TOO_LONG = "Keep the label under 80 characters."
SAME_PAPER = "A link goes between two different papers."


def _clean_label(label: str) -> str:
    """Raises InvalidInput with the message the dialog shows."""
    cleaned = label.strip()
    if not cleaned:
        raise InvalidInput(EMPTY_LABEL)
    if len(cleaned) > LABEL_MAX_CHARS:
        raise InvalidInput(LABEL_TOO_LONG)
    return cleaned


async def get(session: AsyncSession, link_id: uuid.UUID) -> PaperLink:
    """Raises NotFound."""
    link = await session.get(PaperLink, link_id)
    if link is None:
        raise NotFound(f"link {link_id} not found")
    return link


async def create(session: AsyncSession, from_paper: uuid.UUID, to_paper: uuid.UUID, label: str) -> PaperLink:
    """Raises NotFound (either paper), InvalidInput (the same paper twice, or a bad label), Conflict (the pair is
    already linked, whichever way round it was drawn)."""
    cleaned = _clean_label(label)
    if from_paper == to_paper:
        raise InvalidInput(SAME_PAPER)
    await get_paper(session, from_paper)
    await get_paper(session, to_paper)
    pair = (from_paper, to_paper)
    existing = select(PaperLink.id).where(PaperLink.from_paper.in_(pair), PaperLink.to_paper.in_(pair))
    if await session.scalar(existing.limit(1)) is not None:
        raise Conflict(ALREADY_LINKED)
    link = PaperLink(from_paper=from_paper, to_paper=to_paper, label=cleaned)
    session.add(link)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise Conflict(ALREADY_LINKED)
    return link


async def set_label(session: AsyncSession, link_id: uuid.UUID, label: str) -> PaperLink:
    """Raises NotFound, InvalidInput. Only the label changes: the pair and its direction stay as drawn."""
    cleaned = _clean_label(label)
    link = await get(session, link_id)
    link.label = cleaned
    await session.commit()
    return link


async def remove(session: AsyncSession, link_id: uuid.UUID) -> None:
    """Raises NotFound."""
    await get(session, link_id)
    await session.execute(delete(PaperLink).where(PaperLink.id == link_id))
    await session.commit()
