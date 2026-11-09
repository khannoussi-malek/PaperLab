"""A regex-level BibTeX reader: enough to gate structure. Bare numbers (year = 2016), quoted values, nested braces and
an indented or same-line closing brace all parse (the source tool missed all three). Reuses the key finder from
manuscript_missing_keys (S2P B2). Linear in the file size: an entry never runs past the next entry's start, and the
parse is cached so the three reference checks share one pass."""

import functools
import re
from dataclasses import dataclass, field

from app.core.manuscript_missing_keys import ENTRY, NOT_ENTRIES

FIELD = re.compile(r"(\w[\w-]*)\s*=\s*")
BARE = re.compile(r"[^,\n]*")
CACHE_SIZE = 8  # the checks read one .bib text each; a few are kept for the next save


@dataclass(frozen=True)
class BibEntry:
    key: str
    kind: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)  # shared by the cache: read it, never mutate it


def _close(text: str, open_at: int, limit: int) -> int | None:
    """Index of the brace closing the group opened at `open_at`, or None when it does not close before `limit`."""
    depth, i = 0, open_at
    while i < limit:
        if text[i] == "\\":
            i += 1
        elif text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _fields(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    pos = 0
    while (m := FIELD.search(body, pos)) is not None:
        i = m.end()
        if body[i : i + 1] == "{":
            close = _close(body, i, len(body))
            end = len(body) if close is None else close
            value, pos = body[i + 1 : end], end + 1
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


@functools.lru_cache(maxsize=CACHE_SIZE)
def parse_bib(text: str) -> tuple[BibEntry, ...]:
    matches = list(ENTRY.finditer(text))
    entries = []
    line, counted = 1, 0  # running line count: the entries are in file order
    for i, m in enumerate(matches):
        kind = m.group(1).lower()
        if kind in NOT_ENTRIES:
            continue
        at = text.index("@", m.start())
        line += text.count("\n", counted, at)
        counted = at
        limit = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        close = _close(text, text.index("{", at), limit)
        body = text[m.end() : limit if close is None else close]
        entries.append(BibEntry(m.group(2), kind, line, _fields(body)))
    return tuple(entries)
