from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Band = tuple[int, int]


def _check_band(band: Band) -> Band:
    lo, hi = band
    if not 0 <= lo <= hi:
        raise ValueError("band must satisfy 0 <= min <= max")
    return band


class SectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    title: str
    words: Band

    @field_validator("words")
    @classmethod
    def _words_band(cls, v: Band) -> Band:
        return _check_band(v)


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    order: int
    official: bool
    provenance: str
    page_limit: int | None = Field(default=None, ge=1)
    references_count: bool
    abstract_words: Band
    citation_style: Literal["numeric", "author_year"]
    sections: list[SectionSpec]

    @field_validator("abstract_words")
    @classmethod
    def _abstract_band(cls, v: Band) -> Band:
        return _check_band(v)

    @model_validator(mode="after")
    def _sections_are_unique(self):
        ids = [s.id for s in self.sections]
        if not ids:
            raise ValueError("at least one section is required")
        if len(set(ids)) != len(ids):
            raise ValueError("section ids must be unique")
        return self


def lint(root: Path) -> list[str]:
    path = root / "template.json"
    if not path.is_file():
        return ["template.json is missing"]
    try:
        t = TemplateSpec.model_validate_json(path.read_text())
    except ValidationError as e:
        return [f"template.json is invalid: {e}"]
    out = []
    if t.name != root.name:
        out.append(f"name {t.name!r} differs from the folder name {root.name!r}")
    main = root / "main.tex"
    main_text = main.read_text() if main.is_file() else None
    if main_text is None:
        out.append("main.tex is missing")
    listed = {s.id for s in t.sections}
    for s in t.sections:
        f = root / "sections" / f"{s.id}.tex"
        if not f.is_file():
            out.append(f"sections/{s.id}.tex is missing")
        elif not f.read_text().lstrip().startswith(f"\\section{{{s.title}}}"):
            out.append(f"sections/{s.id}.tex does not start with \\section{{{s.title}}}")
        if main_text is not None and f"\\input{{sections/{s.id}}}" not in main_text:
            out.append(f"main.tex has no \\input{{sections/{s.id}}}")
    out += [f"sections/{p.name} is not listed in template.json"
            for p in sorted((root / "sections").glob("*.tex")) if p.stem not in listed]
    return out
