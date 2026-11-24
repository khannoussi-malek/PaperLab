"""Reading and editing evidence cards: one card, the owner's edits, a workspace's cards and their CSV."""

import copy
import csv
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notes.evidence_cards import _SHAPES, CAPS, CardView, _Effect, _Item, _Sample, _view
from app.domain.errors import Conflict, InvalidInput, NotFound
from app.models import EvidenceCard, Paper, Workspace, workspace_papers

_EDITABLE = {"research_question": _Item, "design": _Item, "sample": _Sample, "findings": _Item,
             "effect_sizes": _Effect, "limitations": _Item}


async def get_card(session: AsyncSession, paper_id: uuid.UUID) -> CardView:
    card = await session.scalar(select(EvidenceCard).where(EvidenceCard.paper_id == paper_id))
    if card is None:
        raise NotFound("card_not_found", detail=f"Paper {paper_id} has no evidence card.")
    return _view(card)


def _edited(fields: dict, change: dict) -> dict:
    """A copy of `fields` with one change applied: {field, index (lists), values: {key: new value}}."""
    name, values = change.get("field"), change.get("values") or {}
    if name not in _EDITABLE:
        raise InvalidInput("unknown_field", fields=list(_EDITABLE))
    keys = _SHAPES[_EDITABLE[name]][0]
    if not values or set(values) - set(keys):
        raise InvalidInput("not_editable", editable=list(keys))  # quotes and pages are the evidence
    out = copy.deepcopy(fields)
    if name in CAPS:
        index = change.get("index", 0)
        if type(index) is not int or not 0 <= index < len(out[name]):
            raise InvalidInput("unknown_item", field=name, index=index)
        item = out[name][index]
    else:
        item = out[name]
    if not item.get("quote"):
        raise InvalidInput("item_has_no_evidence", field=name)  # a dropped item has nothing to back an edit
    if "n" in values and values["n"] is not None and type(values["n"]) is not int:
        raise InvalidInput("not_editable", editable=list(keys), detail="n must be a whole number")
    for key, value in values.items():
        item[key] = value if value is None else (value if key == "n" else str(value))
    item["flags"] = sorted({*item["flags"], "edited"})
    return out


async def edit_card(session: AsyncSession, paper_id: uuid.UUID, changes: list[dict]) -> CardView:
    """Changes item values (never quotes or pages), flags each `edited` and marks the card `llm_edited`."""
    card = await session.scalar(select(EvidenceCard).where(EvidenceCard.paper_id == paper_id))
    if card is None:
        raise NotFound("card_not_found", detail=f"Paper {paper_id} has no evidence card.")
    if card.status != "ready":
        raise Conflict("card_not_ready")
    fields = card.fields
    for change in changes:
        fields = _edited(fields, change)
    if changes:
        card.fields, card.provenance, card.updated_at = fields, "llm_edited", datetime.now(UTC)
        await session.commit()
    return _view(card)


@dataclass(frozen=True)
class CardRow:
    paper_id: uuid.UUID
    title: str
    year: int | None
    first_author: str | None
    card: CardView | None


async def workspace_cards(session: AsyncSession, workspace_id: uuid.UUID) -> list[CardRow]:
    """One row per workspace paper (by title), with its card or None. NotFound for an unknown workspace."""
    if await session.get(Workspace, workspace_id) is None:
        raise NotFound("workspace_not_found", detail=f"Workspace {workspace_id} does not exist.")
    rows = await session.execute(
        select(Paper, EvidenceCard)
        .join(workspace_papers, workspace_papers.c.paper_id == Paper.id)
        .outerjoin(EvidenceCard, EvidenceCard.paper_id == Paper.id)
        .where(workspace_papers.c.workspace_id == workspace_id)
        .order_by(Paper.title, Paper.id)
    )
    return [
        CardRow(p.id, p.title, p.year, (p.authors or [None])[0], None if c is None else _view(c)) for p, c in rows
    ]


def _shown(name: str, item: dict) -> str:
    """The item's value as one cell, or "" when it holds none (a dropped or cleared item)."""
    if name == "sample":
        parts = [item.get("n"), item.get("population")]
    else:
        parts = [item.get("value"), item.get("ci"), item.get("p")] if name == "effect_sizes" else [item.get("value")]
    return "; ".join(str(v) for v in parts if v not in (None, ""))


@dataclass(frozen=True)
class CardSummary:
    """A card for Claude: only items that hold a value (each with its quote and page); dropped ones are counted."""

    paper_id: uuid.UUID
    status: str
    error: str | None
    provenance: str
    model: str | None
    prompt_version: int | None
    updated_at: datetime | None
    fields: dict
    left_out: dict  # field -> how many items had no usable quote or numbers (never shown as facts)


def summarize(view: CardView) -> CardSummary:
    kept, left_out = {}, {}
    for name in _EDITABLE:
        value = view.fields.get(name)
        items = value if isinstance(value, list) else [value] if value else []
        shown = [i for i in items if i.get("quote") and _shown(name, i)]
        kept[name] = shown if isinstance(value, list) else (shown[0] if shown else None)
        dropped = [i for i in items if not _shown(name, i) and {"unsupported", "number_not_in_source"} & {*i["flags"]}]
        if dropped:
            left_out[name] = len(dropped)
    return CardSummary(
        view.paper_id, view.status, view.error, view.provenance, view.model, view.prompt_version, view.updated_at,
        kept if view.status == "ready" else {}, left_out,
    )


def _cell(text) -> str:
    """Text for a CSV cell that a spreadsheet will not run as a formula."""
    text = str(text)
    return "'" + text if text[:1] in tuple("=+-@\t\r") else text


CSV_HEADER = ["paper", "year", "field", "value", "quote", "page", "author", "edited"]


async def workspace_csv(session: AsyncSession, workspace_id: uuid.UUID) -> str:
    """Every kept item of every ready card in the workspace, one row each, UTF-8 BOM for Excel. Items without a
    value (dropped as unsupported, or cleared) are left out: they are not facts."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_HEADER)
    for row in await workspace_cards(session, workspace_id):
        if row.card is None or row.card.status != "ready":
            continue
        for name in _EDITABLE:
            value = row.card.fields.get(name)
            for item in value if isinstance(value, list) else [value]:
                if not item or not item.get("quote") or not (shown := _shown(name, item)):
                    continue
                writer.writerow([
                    _cell(row.title), row.year or "", name, _cell(shown), _cell(item["quote"]), item["page"] or "",
                    _cell(row.first_author or ""),
                    "yes" if "edited" in item["flags"] else "no",
                ])
    return "\ufeff" + out.getvalue()
