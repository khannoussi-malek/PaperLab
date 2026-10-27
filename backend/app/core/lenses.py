"""Reading lenses (M16 spec §2): named sets of section roles, defined once here. The API returns them, so the frontend
never hard-codes which roles a lens reads."""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import sections
from app.core.errors import InvalidInput
from app.core.sections import Role, Section

LensId = Literal["full", "key_ideas", "critical", "method", "related"]
# Key ideas' position fallback: this many non-back chunks from each end of the paper.
POSITION_CHUNKS = 3


@dataclass(frozen=True)
class Lens:
    id: LensId
    label: str
    roles: tuple[Role, ...] | None  # None: every chunk


LENSES: dict[str, Lens] = {
    lens.id: lens
    for lens in (
        Lens("full", "Full paper", None),
        Lens("key_ideas", "Key ideas", ("abstract", "intro", "conclusion")),  # D122: the abstract stays
        Lens("critical", "Critical check", ("method", "results", "limitations")),
        Lens("method", "How they did it", ("method",)),
        Lens("related", "Related work", ("related",)),
    )
}


@dataclass(frozen=True)
class LensChunks:
    chunk_ids: list[uuid.UUID]  # in reading order; empty: the paper has no sections for the lens
    positional_fallback: bool
    missing_roles: list[Role]  # the lens's own roles no section has, in the lens's order


def _position(ordered: list[tuple[uuid.UUID, Role]], missing: list[Role]) -> LensChunks:
    # ponytail: with no References heading detected, the last chunks can be references (spec §3.4).
    body = [chunk_id for chunk_id, role in ordered if role != "back"]
    if not body:  # back matter only: no start or end to show, so no fallback to announce
        return LensChunks([], False, missing)
    ids = body if len(body) <= 2 * POSITION_CHUNKS else body[:POSITION_CHUNKS] + body[-POSITION_CHUNKS:]
    return LensChunks(ids, True, missing)


def pick(ordered: list[tuple[uuid.UUID, Role]], lens: Lens) -> LensChunks:
    """The lens's chunks from (chunk id, role) pairs in reading order. Pure.

    Key ideas reads the discussion when there is no conclusion, and falls back to the first and last POSITION_CHUNKS
    non-back chunks when there is no introduction and no conclusion or discussion either (spec §2)."""
    if lens.roles is None:
        return LensChunks([chunk_id for chunk_id, _ in ordered], False, [])
    if not ordered:  # R1: no sections (a paper without a PDF): nothing to show, and no fallback to announce
        return LensChunks([], False, list(lens.roles))
    present = {role for _, role in ordered}
    missing = [role for role in lens.roles if role not in present]
    roles = set(lens.roles)
    if lens.id == "key_ideas" and "conclusion" not in present:
        if "intro" not in present and "discussion" not in present:
            return _position(ordered, missing)
        roles = (roles - {"conclusion"}) | {"discussion"}
    return LensChunks([chunk_id for chunk_id, role in ordered if role in roles], False, missing)


def ordered_roles(found: list[Section]) -> list[tuple[uuid.UUID, Role]]:
    """Every chunk with its section's role, in reading order (sections are runs, so their chunks follow on)."""
    return [(chunk_id, section.role) for section in found for chunk_id in section.chunk_ids]


async def lens_chunks(session: AsyncSession, paper_id: uuid.UUID, lens: str) -> LensChunks:
    """One lens's chunks for a paper, in reading order. Raises InvalidInput("unknown_lens") or NotFound."""
    if lens not in LENSES:
        raise InvalidInput("unknown_lens")
    return pick(ordered_roles(await sections.paper_sections(session, paper_id)), LENSES[lens])


async def paper_lenses(
    session: AsyncSession, paper_id: uuid.UUID
) -> tuple[list[Section], list[tuple[Lens, LensChunks]]]:
    """Every section and every lens with its chunks, from one read: what the sections route returns. Raises NotFound."""
    found = await sections.paper_sections(session, paper_id)
    ordered = ordered_roles(found)
    return found, [(lens, pick(ordered, lens)) for lens in LENSES.values()]
