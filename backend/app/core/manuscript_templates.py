from pathlib import Path

from app.core.errors import InvalidInput

DIR = Path(__file__).resolve().parent.parent / "manuscript_templates"
TEMPLATES = {
    "article": "Plain article",
    "ieee": "IEEE conference",
    "acm": "ACM (sigconf)",
    "lncs": "Springer LNCS",
    "elsevier": "Elsevier",
}


def files(template: str) -> dict[str, str]:
    if template not in TEMPLATES:
        raise InvalidInput("unknown_template")
    return {"main.tex": (DIR / f"{template}.tex").read_text()}
