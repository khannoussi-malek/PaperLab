"""Skills: a named task the reader picks for a chat question. Bundled ones are versioned files; the reader's changes
are rows (M17, spec §3). This module holds the loader, the pure merge and prompt composition."""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from sqlalchemy import select, text
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.prompts import PROMPTS_DIR
from app.models import Skill

logger = logging.getLogger(__name__)

Scope = Literal["paper", "workspace", "both"]
ChatKind = Literal["paper", "workspace"]
SCOPES = ("paper", "workspace", "both")
ORDER = ("study-type", "check-evaluation", "check-validation", "unstated-limits", "llm-reporting", "plain-explanation")
REQUIRED = ("slug", "label", "description", "scope", "version")
FILE_NAME = re.compile(r"(?P<slug>[a-z0-9-]+)\.v(?P<version>\d+)\.md")
FRONTMATTER = re.compile(r"---\n(?P<meta>.*?)\n---\n(?P<body>.*)", re.DOTALL)


@dataclass(frozen=True)
class BundledSkill:
    slug: str
    label: str
    description: str
    scope: Scope
    version: int
    instructions: str


@dataclass(frozen=True)
class SkillRow:
    """One `skills` row: the reader's changes to a bundled skill (builtin_slug set) or a custom skill."""

    id: uuid.UUID
    builtin_slug: str | None
    label: str | None
    description: str | None
    scope: str | None
    instructions: str | None
    version: int
    is_listed: bool
    is_paper_default: bool
    is_workspace_default: bool
    created_at: datetime


@dataclass(frozen=True)
class SkillView:
    id: str  # builtin:<slug> or custom:<uuid>
    label: str
    description: str
    scope: Scope
    instructions: str
    version: int
    is_listed: bool
    is_paper_default: bool
    is_workspace_default: bool
    state: Literal["builtin", "edited", "custom"]


def _split(path: Path) -> tuple[dict, str]:
    match = FRONTMATTER.fullmatch(path.read_text())
    if match is None:
        raise ValueError(f"{path.name}: expected YAML frontmatter between --- lines")
    meta = yaml.safe_load(match["meta"]) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path.name}: frontmatter must be a mapping")
    return meta, match["body"].strip()


def _read_bundled(path: Path) -> BundledSkill:
    name = FILE_NAME.fullmatch(path.name)
    if name is None:
        raise ValueError(f"{path.name}: expected <slug>.v<N>.md")
    meta, body = _split(path)
    missing = [key for key in REQUIRED if key not in meta]
    if missing:
        raise ValueError(f"{path.name}: missing frontmatter field {missing[0]}")
    if meta["slug"] != name["slug"] or str(meta["version"]) != name["version"]:
        raise ValueError(f"{path.name}: the name does not match its frontmatter slug and version")
    if meta["scope"] not in SCOPES:
        raise ValueError(f"{path.name}: scope must be one of {', '.join(SCOPES)}")
    if not body:
        raise ValueError(f"{path.name}: the instruction body is empty")
    return BundledSkill(
        slug=meta["slug"],
        label=meta["label"],
        description=meta["description"],
        scope=meta["scope"],
        version=int(meta["version"]),
        instructions=body,
    )


def load_bundled(folder: Path = PROMPTS_DIR / "skills") -> tuple[BundledSkill, ...]:
    """One file per slug, in ORDER, then any other slugs by name. Raises ValueError on a bad or duplicate file."""
    found: dict[str, BundledSkill] = {}
    for path in sorted(folder.glob("*.md")):
        skill = _read_bundled(path)
        if skill.slug in found:
            raise ValueError(f"{path.name}: slug {skill.slug} is already bundled")
        found[skill.slug] = skill
    rank = {slug: position for position, slug in enumerate(ORDER)}
    return tuple(sorted(found.values(), key=lambda skill: (rank.get(skill.slug, len(ORDER)), skill.slug)))


BUNDLED = load_bundled()
_warned: set[str] = set()


def _warn_gone_once(slug: str) -> None:
    if slug not in _warned:
        _warned.add(slug)
        logger.warning("skill row for %s ignored: no bundled skill has that slug", slug)


def _bundled_view(skill: BundledSkill, row: SkillRow | None) -> SkillView:
    if row is None:
        return SkillView(
            id=f"builtin:{skill.slug}",
            label=skill.label,
            description=skill.description,
            scope=skill.scope,
            instructions=skill.instructions,
            version=skill.version,
            is_listed=True,
            is_paper_default=False,
            is_workspace_default=False,
            state="builtin",
        )
    edited = row.instructions is not None
    return SkillView(
        id=f"builtin:{skill.slug}",
        label=row.label if row.label is not None else skill.label,
        description=row.description if row.description is not None else skill.description,
        scope=row.scope if row.scope is not None else skill.scope,
        instructions=row.instructions if edited else skill.instructions,
        version=row.version if edited else skill.version,
        is_listed=row.is_listed,
        is_paper_default=row.is_paper_default,
        is_workspace_default=row.is_workspace_default,
        state="edited" if edited else "builtin",
    )


def _custom_view(row: SkillRow) -> SkillView:
    return SkillView(
        id=f"custom:{row.id}",
        label=row.label or "",
        description=row.description or "",
        scope=row.scope,
        instructions=row.instructions or "",
        version=row.version,
        is_listed=row.is_listed,
        is_paper_default=row.is_paper_default,
        is_workspace_default=row.is_workspace_default,
        state="custom",
    )


def merge(
    bundled: tuple[BundledSkill, ...] | list[BundledSkill],
    rows: list[SkillRow],
    kind: ChatKind | None = None,
    include_hidden: bool = True,
) -> list[SkillView]:
    """Bundled skills in file order, each with its row applied; then custom rows, newest first (spec §3.4)."""
    by_slug = {row.builtin_slug: row for row in rows if row.builtin_slug is not None}
    known = {skill.slug for skill in bundled}
    for slug in sorted(set(by_slug) - known):
        _warn_gone_once(slug)
    views = [_bundled_view(skill, by_slug.get(skill.slug)) for skill in bundled]
    custom = sorted((row for row in rows if row.builtin_slug is None), key=lambda row: row.created_at, reverse=True)
    views.extend(_custom_view(row) for row in custom)
    if kind is not None:
        views = [view for view in views if view.scope in (kind, "both")]
    if not include_hidden:
        views = [view for view in views if view.is_listed]
    return views


def compose(base_system: str, skill: SkillView | None) -> str:
    """The base prompt unchanged with no skill; else the base prompt, then the skill under a fixed heading."""
    if skill is None:
        return base_system
    return f"{base_system}\n\nYour task for this question:\n{skill.instructions}"


# Service (async, real rows). Spec §6 and the plan's Task 2 interfaces.

LABEL_MAX, DESCRIPTION_MAX, INSTRUCTIONS_MAX = 80, 200, 8000
EDITABLE = ("label", "description", "scope", "instructions", "is_listed")
COVERED_KINDS = {"paper": ("paper", "both"), "workspace": ("workspace", "both")}


def _clean(
    label: str | None = None,
    description: str | None = None,
    scope: str | None = None,
    instructions: str | None = None,
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
    return cleaned


async def _rows(session: AsyncSession) -> list[SkillRow]:
    orm_rows = (await session.execute(select(Skill))).scalars().all()
    return [
        SkillRow(
            id=row.id,
            builtin_slug=row.builtin_slug,
            label=row.label,
            description=row.description,
            scope=row.scope,
            instructions=row.instructions,
            version=row.version,
            is_listed=row.is_listed,
            is_paper_default=row.is_paper_default,
            is_workspace_default=row.is_workspace_default,
            created_at=row.created_at,
        )
        for row in orm_rows
    ]


async def _views(session: AsyncSession, kind: ChatKind | None = None, include_hidden: bool = True) -> list[SkillView]:
    return merge(BUNDLED, await _rows(session), kind=kind, include_hidden=include_hidden)


async def list_skills(
    session: AsyncSession, kind: ChatKind | None = None, include_hidden: bool = False
) -> list[SkillView]:
    return await _views(session, kind, include_hidden)


async def get_view(session: AsyncSession, skill_id: str) -> SkillView:
    """Raises NotFound("skill_not_found") for an unknown, removed or malformed id."""
    for view in await _views(session):
        if view.id == skill_id:
            return view
    raise NotFound("skill_not_found")


async def resolve(session: AsyncSession, skill_id: str | None, kind: ChatKind) -> SkillView | None:
    """The skill a question runs with. Hidden skills still resolve. Raises Conflict("skill_scope") when the skill's
    scope excludes this chat kind."""
    if skill_id is None:
        return None
    view = await get_view(session, skill_id)
    if view.scope not in COVERED_KINDS[kind]:
        raise Conflict("skill_scope")
    return view


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
        row = Skill(builtin_slug=skill_id.removeprefix("builtin:"), version=1, is_listed=True)
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


async def create(session: AsyncSession, *, label: str, description: str, scope: str, instructions: str) -> SkillView:
    await _lock(session)
    cleaned = _clean(label=label, description=description, scope=scope, instructions=instructions)
    await _refuse_taken(session, cleaned["label"])
    row = Skill(
        label=cleaned["label"],
        description=cleaned["description"],
        scope=cleaned["scope"],
        instructions=cleaned["instructions"],
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
    for key in ("label", "description", "scope"):
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
    row.label = row.description = row.scope = row.instructions = None
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
