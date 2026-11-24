"""Changing skills: creating, editing, deleting and resetting one, and choosing each chat's default."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers.lenses import LENSES
from app.core.platform.skills import (
    BUNDLED,
    COVERED_KINDS,
    DESCRIPTION_MAX,
    FULL,
    INSTRUCTIONS_MAX,
    LABEL_MAX,
    SCOPES,
    ChatKind,
    SkillView,
    _views,
    get_view,
)
from app.domain.errors import Conflict, InvalidInput
from app.models import Skill

EDITABLE = ("label", "description", "scope", "instructions", "is_listed", "lens")


def _clean(
    label: str | None = None,
    description: str | None = None,
    scope: str | None = None,
    instructions: str | None = None,
    lens: str | None = None,
) -> dict[str, str]:
    """The stripped values of the fields that were given, after the field limits (InvalidInput)."""
    cleaned: dict[str, str] = {}
    if label is not None:
        cleaned["label"] = label.strip()
        if not 1 <= len(cleaned["label"]) <= LABEL_MAX:
            raise InvalidInput("skill_label_length", max=LABEL_MAX)
    if description is not None:
        cleaned["description"] = description.strip()
        if len(cleaned["description"]) > DESCRIPTION_MAX:
            raise InvalidInput("skill_description_length", max=DESCRIPTION_MAX)
    if scope is not None:
        if scope not in SCOPES:
            raise InvalidInput("skill_scope_invalid", scopes=list(SCOPES))
        cleaned["scope"] = scope
    if instructions is not None:
        cleaned["instructions"] = instructions.strip()
        if not 1 <= len(cleaned["instructions"]) <= INSTRUCTIONS_MAX:
            raise InvalidInput("skill_instructions_length", max=INSTRUCTIONS_MAX)
    if lens is not None:
        if lens not in LENSES:
            raise InvalidInput("skill_lens_invalid", lenses=list(LENSES))
        cleaned["lens"] = lens
    return cleaned


async def _row_for(session: AsyncSession, skill_id: str) -> Skill | None:
    if skill_id.startswith("builtin:"):
        query = select(Skill).where(Skill.builtin_slug == skill_id.removeprefix("builtin:"))
        return (await session.execute(query)).scalar_one_or_none()
    if skill_id.startswith("custom:"):
        try:
            key = uuid.UUID(skill_id.removeprefix("custom:"))
        except ValueError:
            return None
        return await session.get(Skill, key)
    return None


async def _row_or_insert(session: AsyncSession, skill_id: str) -> Skill:
    """A bundled skill's first touch inserts its row; the id has already been checked by get_view."""
    row = await _row_for(session, skill_id)
    if row is None:
        # the row starts at the shipped version, so its first text edit is a version the shipped text never had
        shipped = next(b.version for b in BUNDLED if b.slug == skill_id.removeprefix("builtin:"))
        row = Skill(builtin_slug=skill_id.removeprefix("builtin:"), version=shipped, is_listed=True)
        session.add(row)
        await session.flush()
    return row


async def _refuse_taken(session: AsyncSession, label: str, exclude_id: str | None = None) -> None:
    taken = {view.label.casefold() for view in await _views(session) if view.id != exclude_id}
    if label.casefold() in taken:
        raise Conflict("skill_label_taken")


def _clear_uncovered_defaults(row: Skill, scope: str) -> None:
    if scope not in COVERED_KINDS["paper"]:
        row.is_paper_default = False
    if scope not in COVERED_KINDS["workspace"]:
        row.is_workspace_default = False


async def _lock(session: AsyncSession) -> None:
    """Every skill write takes this first, so writes run one at a time and always lock in the same order: two tabs
    can't both pass the label check or meet the default index's error, and no two writes can deadlock."""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('skills'))"))


async def create(
    session: AsyncSession, *, label: str, description: str, scope: str, instructions: str, lens: str | None = None
) -> SkillView:
    await _lock(session)
    cleaned = _clean(label=label, description=description, scope=scope, instructions=instructions, lens=lens)
    await _refuse_taken(session, cleaned["label"])
    row = Skill(
        label=cleaned["label"],
        description=cleaned["description"],
        scope=cleaned["scope"],
        instructions=cleaned["instructions"],
        lens=cleaned.get("lens", FULL),
        version=1,
        is_listed=True,
        is_paper_default=False,
        is_workspace_default=False,
        created_at=datetime.now(timezone.utc),  # newest first: now() would tie within one transaction
    )
    session.add(row)
    await session.flush()
    skill_id = f"custom:{row.id}"
    await session.commit()
    return await get_view(session, skill_id)


async def update(session: AsyncSession, skill_id: str, **fields) -> SkillView:
    """Changes only the fields sent. `version` bumps when instructions change. Hiding clears both defaults."""
    await _lock(session)
    if set(fields) - set(EDITABLE):
        raise InvalidInput("skill_field_unknown", fields=sorted(set(fields) - set(EDITABLE)))
    if any(value is None for value in fields.values()):
        raise InvalidInput("skill_field_required")
    current = await get_view(session, skill_id)
    cleaned = _clean(**{key: value for key, value in fields.items() if key != "is_listed"})
    if "label" in cleaned:
        await _refuse_taken(session, cleaned["label"], exclude_id=skill_id)
    row = await _row_or_insert(session, skill_id)
    for key in ("label", "description", "scope", "lens"):
        if key in cleaned:
            setattr(row, key, cleaned[key])
    if "scope" in cleaned:
        _clear_uncovered_defaults(row, cleaned["scope"])
    if "instructions" in cleaned:
        if cleaned["instructions"] != current.instructions:
            row.version += 1
        row.instructions = cleaned["instructions"]
    if "is_listed" in fields:
        row.is_listed = bool(fields["is_listed"])
        if not row.is_listed:
            row.is_paper_default = False
            row.is_workspace_default = False
    await session.flush()
    await session.commit()
    return await get_view(session, skill_id)


async def delete(session: AsyncSession, skill_id: str) -> None:
    """Custom skills only. Raises NotFound, or Conflict("builtin_skill") for a bundled one."""
    await _lock(session)
    await get_view(session, skill_id)
    if skill_id.startswith("builtin:"):
        raise Conflict("builtin_skill")
    row = await _row_for(session, skill_id)
    await session.delete(row)
    await session.commit()


async def reset(session: AsyncSession, skill_id: str) -> SkillView:
    """Bundled skills only: the text, label, description and scope go back to the shipped values. The row stays, so
    hidden and default state survive. Raises Conflict("custom_skill") for a custom one."""
    await _lock(session)
    await get_view(session, skill_id)
    if skill_id.startswith("custom:"):
        raise Conflict("custom_skill")
    row = await _row_for(session, skill_id)
    if row is None:
        return await get_view(session, skill_id)
    if row.label is not None:  # the shipped label comes back: refuse it when another skill has taken it since
        shipped = next(b.label for b in BUNDLED if b.slug == row.builtin_slug)
        await _refuse_taken(session, shipped, exclude_id=skill_id)
    row.label = row.description = row.scope = row.instructions = row.lens = None
    row.version += 1
    await session.flush()
    _clear_uncovered_defaults(row, (await get_view(session, skill_id)).scope)
    await session.commit()
    return await get_view(session, skill_id)


async def set_default(session: AsyncSession, skill_id: str, kind: ChatKind, on: bool) -> SkillView:
    """Moves the default of one chat kind in one transaction: the old holder is unset first, as llm_connections
    set_default does, so the partial unique index never sees two. Raises Conflict("skill_scope")."""
    await _lock(session)
    view = await get_view(session, skill_id)
    if view.scope not in COVERED_KINDS[kind]:
        raise Conflict("skill_scope")
    row = await _row_or_insert(session, skill_id)
    flag = "is_paper_default" if kind == "paper" else "is_workspace_default"
    if on:
        await session.execute(sql_update(Skill).where(getattr(Skill, flag), Skill.id != row.id).values({flag: False}))
    setattr(row, flag, on)
    if on:
        row.is_listed = True  # a default the picker hid would never be applied; hiding clears defaults, so both agree
    await session.flush()
    await session.commit()
    return await get_view(session, skill_id)
