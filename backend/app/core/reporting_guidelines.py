"""Reporting-guideline checklists as data (S2P B5). Items are written in our own words; one JSON file per guideline."""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator

from app.core.errors import InvalidInput

DIR = Path(__file__).resolve().parent.parent / "reporting_guidelines"
ORDER = ("prisma2020", "strobe", "consort", "ml")  # the picker's order; a new file goes at the end until listed here


def _clean(v: str) -> str:
    if not v.strip() or ":" in v:
        raise ValueError("blank or contains ':'")
    return v


class Item(BaseModel):
    id: str
    section: str
    text: str

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return _clean(v)

    @field_validator("section", "text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("blank")
        return v


class Guideline(BaseModel):
    id: str
    label: str
    applies_to: str
    source: str
    items: tuple[Item, ...]

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return _clean(v)

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [i.id for i in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate item id")
        return self


@lru_cache(maxsize=1)
def _load() -> dict[str, Guideline]:
    found = {g.id: g for g in (Guideline.model_validate_json(p.read_text()) for p in DIR.glob("*.json"))}
    rank = lambda gid: (ORDER.index(gid) if gid in ORDER else len(ORDER), gid)  # noqa: E731
    return {gid: found[gid] for gid in sorted(found, key=rank)}


_load()  # a bad data file fails at import, like templates


def all_guidelines() -> list[Guideline]:
    return list(_load().values())


def get(guideline_id: str) -> Guideline:
    try:
        return _load()[guideline_id]
    except KeyError:
        raise InvalidInput("unknown_guideline") from None


class ItemView(Item):
    ticked: bool


class ChecklistView(BaseModel):
    guideline: str | None
    items: list[ItemView]
    done: int
    total: int


def _key(guideline_id: str, item_id: str) -> str:
    return f"{guideline_id}:{item_id}"


def view(checklist: dict) -> ChecklistView:
    chosen = checklist.get("guideline")
    g = _load().get(chosen) if isinstance(chosen, str) else None
    if g is None:
        return ChecklistView(guideline=None, items=[], done=0, total=0)
    items = [ItemView(**i.model_dump(), ticked=checklist.get(_key(g.id, i.id)) is True) for i in g.items]
    return ChecklistView(guideline=g.id, items=items, done=sum(i.ticked for i in items), total=len(items))


def apply(checklist: dict, guideline: str | None = None, tick=(), untick=()) -> dict:
    """A new checklist dict; the input is not touched. guideline=None keeps the current one. Ticks of other guidelines
    and final-step keys stay."""
    out = dict(checklist)
    if guideline is not None:
        out["guideline"] = get(guideline).id
    if not (tick or untick):
        return out
    chosen = out.get("guideline")
    if not isinstance(chosen, str) or chosen not in _load():
        raise InvalidInput("unknown_guideline")
    available = [i.id for i in get(chosen).items]
    if bad := [i for i in (*tick, *untick) if i not in available]:
        raise InvalidInput("unknown_item", available=available, unknown=bad)
    for i in untick:
        out.pop(_key(chosen, i), None)
    for i in tick:
        out[_key(chosen, i)] = True
    return out
