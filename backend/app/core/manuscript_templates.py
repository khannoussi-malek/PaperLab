from functools import lru_cache
from pathlib import Path

from app.core.errors import InvalidInput
from app.core.manuscript_template_spec import TemplateSpec

DIR = Path(__file__).resolve().parent.parent / "manuscript_templates"


@lru_cache(maxsize=1)
def specs() -> dict[str, TemplateSpec]:
    found = [TemplateSpec.model_validate_json(p.read_text()) for p in DIR.glob("*/template.json")]
    return {t.name: t for t in sorted(found, key=lambda t: (t.order, t.name))}


def get(name: str | None) -> TemplateSpec | None:
    return specs().get(name) if name else None


TEMPLATES = {name: t.label for name, t in specs().items()}  # import fails on a bad template.json: the startup lint


def files(template: str) -> dict[str, str]:
    if template not in TEMPLATES:
        raise InvalidInput("unknown_template")
    root = DIR / template
    return {str(f.relative_to(root)): f.read_text() for f in sorted(root.rglob("*.tex"))}
