"""Skills: a named task the reader picks for a chat question. Bundled ones are versioned files; the reader's changes
are rows (M17, spec §3). This module holds the loader, the pure merge and prompt composition."""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers.lenses import LENSES
from app.core.platform.prompts import PROMPTS_DIR
from app.domain.errors import Conflict, NotFound
from app.models import Skill

logger = logging.getLogger(__name__)

Scope = Literal["paper", "workspace", "both"]
ChatKind = Literal["paper", "workspace"]
SCOPES = ("paper", "workspace", "both")
ORDER = ("study-type", "check-evaluation", "check-validation", "unstated-limits", "llm-reporting", "plain-explanation")
REQUIRED = ("slug", "label", "description", "scope", "version", "lens")
FULL = "full"  # the lens that is the whole paper: no lens at all
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
    lens: str  # a LENSES id: the lens the skill's answers read through


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
    lens: str | None


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
    lens: str


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
    if meta["lens"] not in LENSES:
        raise ValueError(f"{path.name}: lens must be one of {', '.join(LENSES)}")
    if not body:
        raise ValueError(f"{path.name}: the instruction body is empty")
    return BundledSkill(
        slug=meta["slug"],
        label=meta["label"],
        description=meta["description"],
        scope=meta["scope"],
        version=int(meta["version"]),
        instructions=body,
        lens=meta["lens"],
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
            lens=skill.lens,
        )
    text_edited = row.instructions is not None  # the version counts text changes only, so a lens change keeps it
    return SkillView(
        id=f"builtin:{skill.slug}",
        label=row.label if row.label is not None else skill.label,
        description=row.description if row.description is not None else skill.description,
        scope=row.scope if row.scope is not None else skill.scope,
        instructions=row.instructions if text_edited else skill.instructions,
        version=row.version if text_edited else skill.version,
        is_listed=row.is_listed,
        is_paper_default=row.is_paper_default,
        is_workspace_default=row.is_workspace_default,
        state="edited" if text_edited or row.lens is not None else "builtin",
        lens=row.lens if row.lens is not None else skill.lens,
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
        lens=row.lens if row.lens is not None else FULL,
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
COVERED_KINDS = {"paper": ("paper", "both"), "workspace": ("workspace", "both")}


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
            lens=row.lens,
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


