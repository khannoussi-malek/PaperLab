"""A regex-level BibTeX reader: enough to gate structure. Bare numbers (year = 2016), quoted values, nested braces and
an indented or same-line closing brace all parse (the source tool missed all three). Reuses the key finder from
manuscript_missing_keys (S2P B2)."""

import re
from dataclasses import dataclass, field

from app.core.manuscript_missing_keys import ENTRY, NOT_ENTRIES

FIELD = re.compile(r"(\w[\w-]*)\s*=\s*")
BARE = re.compile(r"[^,\n]*")


@dataclass(frozen=True)
class BibEntry:
    key: str
    kind: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)


def _brace_end(text: str, open_at: int) -> int:
    """Index just past the brace group opening at `open_at` (end of text when it never closes)."""
    depth, i = 0, open_at
    while i < len(text):
        if text[i] == "\\":
            i += 1
        elif text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _fields(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    pos = 0
    while (m := FIELD.search(body, pos)) is not None:
        i = m.end()
        if body[i : i + 1] == "{":
            end = _brace_end(body, i)
            value, pos = body[i + 1 : end - 1], end
        elif body[i : i + 1] == '"':
            end = i + 1
            while end < len(body) and not (body[end] == '"' and body[end - 1] != "\\"):
                end += 1
            value, pos = body[i + 1 : end], end + 1
        else:
            bare = BARE.match(body, i)
            value, pos = bare.group().strip(), bare.end()
        out.setdefault(m.group(1).lower(), value.strip())
    return out


def parse_bib(text: str) -> list[BibEntry]:
    entries = []
    for m in ENTRY.finditer(text):
        kind = m.group(1).lower()
        if kind in NOT_ENTRIES:
            continue
        at = text.index("@", m.start())
        open_at = text.index("{", at)
        body = text[m.end() : _brace_end(text, open_at) - 1]
        entries.append(BibEntry(m.group(2), kind, text.count("\n", 0, at) + 1, _fields(body)))
    return entries
