"""blueprint.json: a manuscript's plan (S2P B10). Parsing, section ids and word counts; the checks live in
manuscript_checks/blueprint.py. Pure string work, no model."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core import manuscript_templates
from app.core.manuscript_checks.latex_hygiene import blank_math, line_of
from app.core.manuscript_sentences import _blank_comments, _brace_end
from app.core.manuscript_template_spec import Band, _check_band

PATH = "blueprint.json"
MAX_CONTRIBUTIONS, MAX_NOTATION = 12, 100
# ponytail: a title with nested braces is skipped
_SECTION = re.compile(r"\\section\*?\s*(?:\[[^\]]*\]\s*)?\{([^{}]*)\}")
_END = re.compile(r"\\(?:bibliography(?:style)?\{|printbibliography|appendix\b|end\{document\})")
_FLOATS = re.compile(r"\\begin\{(table\*?|figure\*?|tabular\*?|longtable)\}.*?\\end\{\1\}", re.S)
_INPUTS = re.compile(r"\\(?:input|include)\s*\{")
_DROP_ARGS = re.compile(
    r"\\(?:cite\w*|[cC]?ref|eqref|label|begin|end|includegraphics|input|include|url|bibliographystyle)\*?"
    r"(?:\[[^\]]*\])*\{[^}]*\}")
_COMMAND = re.compile(r"\\[A-Za-z]+\*?")
_WORD = re.compile(r"[A-Za-z0-9][\w'-]*")


class Symbol(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1)
    meaning: str = Field(min_length=1)


class BlueprintSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = ""
    contributions: list[str] = Field(default_factory=list, max_length=MAX_CONTRIBUTIONS)
    notation: list[Symbol] = Field(default_factory=list, max_length=MAX_NOTATION)
    target_words: dict[str, Band] = Field(default_factory=dict)

    @field_validator("target_words")
    @classmethod
    def _bands(cls, v: dict[str, Band]) -> dict[str, Band]:
        return {k: _check_band(b) for k, b in v.items()}


def parse(text: str) -> BlueprintSpec:
    """Raises ValueError (pydantic's ValidationError and json errors are both) on anything but a valid plan."""
    return BlueprintSpec.model_validate_json(text)


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


@dataclass(frozen=True)
class SectionWords:
    id: str
    title: str
    path: str
    line: int
    words: int
    measurable: bool = True  # False when the body pulls text in with \input: its words are not in this file


def _count(body: str) -> int:
    body = blank_math(_FLOATS.sub(" ", _blank_comments(body)))  # tables and figures are not prose
    return len(_WORD.findall(_COMMAND.sub(" ", _DROP_ARGS.sub(" ", body))))


def sections(files: Mapping[str, str]) -> list[SectionWords]:
    """Every \\section in every .tex file with its word count. ponytail: a section ends at the next \\section or the
    bibliography in the same file; \\input inside a section is not followed. Add that if a layout needs it."""
    out = []
    for path in sorted(p for p in files if p.endswith(".tex")):
        text = _blank_comments(files[path])
        end = m.start() if (m := _END.search(text)) else len(text)
        heads = [h for h in _SECTION.finditer(text) if h.start() < end]
        for h, nxt in zip(heads, [*(x.start() for x in heads[1:]), end]):
            body = text[h.end():nxt]
            out.append(SectionWords(slug(h.group(1)), h.group(1), path, line_of(text, h.start()),
                                    _count(body), not _INPUTS.search(body)))
    return out


def band(spec: BlueprintSpec, section_id: str, template: str) -> Band | None:
    if section_id in spec.target_words:
        return spec.target_words[section_id]
    t = manuscript_templates.get(template)
    return next((s.words for s in t.sections if s.id == section_id), None) if t else None


_TITLE = re.compile(r"\\title\s*(?:\[[^\]]*\]\s*)?\{")
_THANKS = re.compile(r"\\thanks\s*\{")
_BREAK = re.compile(r"\\\\|\\newline\b")
_ESCAPED = re.compile(r"\\([%&$#_])")
_LETTERS = re.compile(r"\\[A-Za-z]+\*?")


def latex_title(tex: str) -> str | None:
    """The paper's \\title as plain text for the blueprint, or None. Mirrors latexTitle in blueprint.ts."""
    text = _blank_comments(tex)
    m = _TITLE.search(text)
    if m is None:
        return None
    end = _brace_end(text, m.end() - 1)
    body = text[m.end():end - 1] if end <= len(text) and text[end - 1] == "}" else ""
    while (t := _THANKS.search(body)) is not None:  # footnotes in the title are not part of it
        body = body[:t.start()] + " " + body[_brace_end(body, t.end() - 1):]
    body = _LETTERS.sub("", _ESCAPED.sub(r"\1", _BREAK.sub(" ", body)))
    plain = " ".join(body.replace("{", "").replace("}", "").split())
    return plain or None
