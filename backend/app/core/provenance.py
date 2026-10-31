"""Which source last filled each group of a paper's details: papers.field_sources, {group: source} (R22).

Every writer stamps the groups it actually wrote, in the same UPDATE; a field its guard dropped, or a blank, claims
nothing. A hand edit is never stamped: manual_fields tells it. No backfill: a paper from before 0053 starts with {}.
"""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import case, func, literal, or_
from sqlalchemy.dialects.postgresql import JSONB

from app.core.source_types import PROVENANCE_SOURCES
from app.models import Paper

FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "bibliographic": ("title", "authors", "year", "venue", "issn", "type"),
    "identifiers": ("doi", "openalex_id", "pmid", "pmcid"),
    "citation": ("volume", "issue", "pages", "editors"),
    "abstract": ("abstract",),
    "source_type": ("source_type", "peer_reviewed"),
    "published": ("published_doi", "published_venue"),
}
_GROUP_OF = {field: group for group, fields in FIELD_GROUPS.items() for field in fields}


def groups_of(fields: Iterable[str]) -> set[str]:
    return {_GROUP_OF[field] for field in fields if field in _GROUP_OF}


def _checked(source: str) -> str:
    if source not in PROVENANCE_SOURCES:
        raise ValueError(f"unknown provenance source {source!r}")
    return source


def sources_of(values: dict[str, Any], source: str) -> dict[str, str]:
    """{group: source} for each group `values` gives a value to. A blank (None, "", []) fills nothing."""
    filled = (field for field, value in values.items() if value not in (None, "", []))
    return dict.fromkeys(sorted(groups_of(filled)), _checked(source))


def stamp(values: dict[str, Any], source: str, skip: Iterable[str] = ()) -> dict[str, Any]:
    """`values` for an UPDATE of papers, plus field_sources merged with their groups (but those in `skip`). A jsonb
    `||` in the UPDATE, so writers stamping other groups at the same time don't clobber each other."""
    sources = {g: s for g, s in sources_of(values, source).items() if g not in skip}
    return {**values, "field_sources": Paper.field_sources.op("||")(literal(sources, JSONB))} if sources else values


def stamp_edited(fields: Iterable[str]) -> dict[str, Any]:
    """field_sources for the owner's correction: every group it touches is "manual", a field cleared to blank too.
    manual_fields can't tell an edit from a lock the app sets itself (a search result's title), so edits say so here."""
    edited = dict.fromkeys(sorted(groups_of(fields)), "manual")
    return {"field_sources": Paper.field_sources.op("||")(literal(edited, JSONB))} if edited else {}


def stamp_filled(fields: Iterable[str], source: str) -> dict[str, Any]:
    """field_sources for an UPDATE that fills only NULL columns (COALESCE): a group of `fields` is claimed when one of
    its fields was NULL before the UPDATE, which is what a SET expression reads."""
    groups: dict[str, list[str]] = {}
    for field in fields:
        if group := _GROUP_OF.get(field):
            groups.setdefault(group, []).append(field)
    if not groups:
        return {}
    pairs = []
    for group, names in groups.items():
        pairs += [group, case((or_(*(getattr(Paper, name).is_(None) for name in names)), _checked(source)))]
    return {"field_sources": Paper.field_sources.op("||")(func.jsonb_strip_nulls(func.jsonb_build_object(*pairs)))}
