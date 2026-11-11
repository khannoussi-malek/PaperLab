from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from app.core.errors import InvalidInput
from app.core.manuscript_template_spec import TemplateSpec

DIR = Path(__file__).resolve().parent.parent / "manuscript_templates"


@lru_cache(maxsize=1)
def specs() -> dict[str, TemplateSpec]:
    found = [TemplateSpec.model_validate_json(p.read_text()) for p in DIR.glob("*/template.json")]
    return {t.name: t for t in sorted(found, key=lambda t: (t.order, t.name))}


class TemplateSummary(TypedDict):
    name: str
    label: str
    official: bool
    provenance: str
    page_limit: int | None
    references_count: bool
    section_words: dict[str, tuple[int, int]]


def summaries() -> list[TemplateSummary]:
    """Every template in order, as the API and the MCP tool list them: limits and each section's word band."""
    return [
        TemplateSummary(
            name=t.name, label=t.label, official=t.official, provenance=t.provenance, page_limit=t.page_limit,
            references_count=t.references_count, section_words={s.id: s.words for s in t.sections},
        )
        for t in specs().values()
    ]


def get(name: str | None) -> TemplateSpec | None:
    return specs().get(name) if name else None


TEMPLATES = {name: t.label for name, t in specs().items()}  # import fails on a bad template.json: the startup lint


def files(template: str) -> dict[str, str]:
    if template not in TEMPLATES:
        raise InvalidInput("unknown_template")
    root = DIR / template
    return {str(f.relative_to(root)): f.read_text() for f in sorted(root.rglob("*.tex"))}
