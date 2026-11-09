"""Overfull/Underfull \\hbox lines from a compile log (P9). Pure: a string in, boxes out.

Real Tectonic 0.17.0 output (captured in tests/fixtures/tectonic): nested .tex files are logged without
their extension, `(sections/a`; stderr repeats each box as `warning: sections/a:3: Overfull ...` with no
box body; a 79-column line is wrapped and its tail sits on the next line.
"""

import re
from dataclasses import dataclass, replace
from typing import Literal

WRAP = 79  # TeX hard-wraps log lines at 79 columns
_HEADER = re.compile(
    r"^(?:warning: (?:(?P<wfile>[^\s:]+):\d+: )?)?(?P<kind>Overfull|Underfull) \\hbox "
    r"\((?:(?P<pt>[\d.]+)pt too wide|badness (?P<bad>\d+))\) "
    r"(?:in (?:paragraph|alignment) at lines (?P<a>\d+)--(?P<b>\d+)|detected at line (?P<c>\d+))"
)
_TOKEN = re.compile(r"\((?P<open>[^\s()]+)|(?P<close>\))")
_SKIP = ("warning:", "note:", "error:", "info:")  # stderr chatter: never touches the file stack; box headers match first


@dataclass(frozen=True)
class Box:
    kind: Literal["overfull", "underfull"]
    amount: float  # points too wide (overfull) or badness (underfull)
    first_line: int
    last_line: int
    file: str | None


def _tex_name(raw: str) -> str | None:
    """Tectonic drops .tex from nested names; other extensions (.sty, .cls, .fd) are not TeX sources."""
    name = raw.removeprefix("./")
    if "." not in name.rsplit("/", 1)[-1]:
        return name + ".tex"
    return name if name.endswith(".tex") else None


def _unwrap(lines: list[str]) -> list[str]:
    """Rejoin a line TeX hard-wrapped at WRAP columns with the line that follows it."""
    out: list[str] = []
    for line in lines:
        # ponytail: a 79-column line that is not a wrap is joined too; harmless, box bodies are skipped and tokens match anywhere
        if out and len(out[-1]) == WRAP and line and not _starts_block(line):
            out = [*out[:-1], out[-1] + line]
        else:
            out.append(line)
    return out


def _starts_block(line: str) -> bool:
    return line.startswith("warning:") or _HEADER.match(line) is not None


def _box(m: re.Match[str], top: str | None) -> Box:
    overfull = m["kind"] == "Overfull"
    amount = float(m["pt"] if m["pt"] else m["bad"])
    first, last = (int(m["a"]), int(m["b"])) if m["a"] else (int(m["c"]), int(m["c"]))
    file = _tex_name(m["wfile"]) if m["wfile"] else top
    return Box("overfull" if overfull else "underfull", amount, first, last, file)


def _same(a: Box, b: Box) -> bool:
    key = (a.kind, a.amount, a.first_line, a.last_line)
    return key == (b.kind, b.amount, b.first_line, b.last_line) and (
        a.file is None or b.file is None or a.file == b.file)


def _fold(found: list[Box], box: Box) -> list[Box]:
    """The stderr copy and the log copy of one box are one box; the known file wins."""
    for i, old in enumerate(found):
        if _same(old, box):
            return [*found[:i], replace(old, file=old.file or box.file), *found[i + 1:]]
    return [*found, box]


def boxes(log: str) -> list[Box]:
    found: list[Box] = []
    stack: list[str | None] = []  # open files; None for a non-TeX file
    in_body = False  # inside an overfull/underfull body, which can hold stray parens
    for line in _unwrap(log.splitlines()):
        if in_body and line.strip() and not _starts_block(line):
            continue
        in_body = False
        m = _HEADER.match(line)
        if m:
            found = _fold(found, _box(m, stack[-1] if stack else None))
            in_body = True
            continue
        if line.startswith(_SKIP):
            continue
        for tok in _TOKEN.finditer(line):
            if tok["open"]:
                stack.append(_tex_name(tok["open"]))
            elif stack:
                stack.pop()
    return found
