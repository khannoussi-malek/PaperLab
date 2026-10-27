"""Read and rewrite the `\\input{sections/<slug>}` lines of a manuscript's main file. Pure text, no database."""

import re
import unicodedata
from dataclasses import dataclass

from app.core.errors import InvalidInput

MAX_TITLE = 200
SECTIONS_DIR = "sections"
_INPUT = re.compile(r"\\(input|include)\s*\{\s*([^{}]*?)\s*\}")
_SECTION = re.compile(r"\\section(\*?)\s*(?:\[[^\]]*\]\s*)?\{")  # an optional [short title] first
END_MARKERS = ("\\bibliographystyle", "\\bibliography{", "\\printbibliography", "\\appendix", "\\end{document}")


@dataclass(frozen=True)
class InputLine:
    index: int
    target: str


def _code(line: str) -> str:
    """The line without its comment: a comment is a `%` not preceded by a backslash."""
    m = re.search(r"(?<!\\)%", line)
    return line[: m.start()] if m else line


def _tex(target: str) -> str:
    return target if target.endswith(".tex") else target + ".tex"


def _line_inputs(line: str) -> list[re.Match]:
    return list(_INPUT.finditer(_code(line)))


def _begin_index(lines: list[str]) -> int | None:
    return next((i for i, ln in enumerate(lines) if "\\begin{document}" in _code(ln)), None)


def _end_index(lines: list[str]) -> int | None:
    """The first end marker after `\\begin{document}` (a preamble `\\bibliographystyle` is not one)."""
    begin = _begin_index(lines)
    start = 0 if begin is None else begin + 1
    return next((i for i in range(start, len(lines)) if any(k in _code(lines[i]) for k in END_MARKERS)), None)


def _slots(lines: list[str]) -> list[tuple[int, re.Match]]:
    """The section `\\input`s: those in the body, before the first end marker. A main without `\\begin{document}`
    (an `\\input`-ed preamble style) counts them all."""
    begin = _begin_index(lines)
    if begin is None:
        lo, hi = 0, len(lines)
    else:
        end = _end_index(lines)
        lo, hi = begin + 1, len(lines) if end is None else end
    return [(i, m) for i in range(lo, hi) for m in _line_inputs(lines[i])]


def input_lines(main: str) -> list[InputLine]:
    return [InputLine(i, _target(m)) for i, m in _slots(main.splitlines())]


def _target(m: re.Match) -> str:
    return _tex(m.group(2))


def _canonical(path: str, command: str = "input") -> str:
    return f"\\{command}{{" + path.removesuffix(".tex") + "}"


def _require(main: str, path: str) -> None:
    if path not in {x.target for x in input_lines(main)}:
        raise InvalidInput("not_a_section")


def _replace_slots(lines: list[str], slots: list[tuple[int, re.Match]], texts: list[str | None]) -> str:
    """Rewrite each slot's span with its text (None removes it); lines left blank by a removal go away."""
    out = list(lines)
    for (i, m), text in sorted(zip(slots, texts), key=lambda p: (p[0][0], -p[0][1].start())):
        out[i] = out[i][: m.start()] + (text or "") + out[i][m.end():]
        if text is None and not out[i].strip():
            out[i] = None
    return "".join(ln for ln in out if ln is not None)


def _keep_ends(main: str) -> list[str]:
    return main.splitlines(keepends=True)


def section_path(title: str, taken: set[str]) -> str:
    ascii_ = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:40].strip("-") or "section"
    path, n = f"{SECTIONS_DIR}/{slug}.tex", 2
    while path in taken:
        path, n = f"{SECTIONS_DIR}/{slug}-{n}.tex", n + 1
    return path


def check_title(title: str) -> str:
    title = title.strip()
    depth = 0
    for ch in title:
        depth += (ch == "{") - (ch == "}")
        if depth < 0:
            break
    lone_backslash = (len(title) - len(title.rstrip("\\"))) % 2  # `Results\` would eat the closing brace
    if not title or len(title) > MAX_TITLE or depth != 0 or lone_backslash or re.search(r"[\r\n]|(?<!\\)%", title):
        raise InvalidInput("bad_title")
    return title


def insert_input(main: str, path: str, after: str | None) -> str:
    lines = _keep_ends(main)
    if after is not None:
        _require(main, after)
        at = max(i for i, m in _slots(lines) if _target(m) == after) + 1
    elif slots := _slots(lines):
        at = slots[-1][0] + 1
    elif (at := _end_index(lines)) is None:
        raise InvalidInput("no_end_document")
    if at and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    return "".join([*lines[:at], _canonical(path) + "\n", *lines[at:]])


def move_input(main: str, path: str, to: int) -> str:
    _require(main, path)
    lines = _keep_ends(main)
    slots = _slots(lines)
    texts = [m.group(0) for _, m in slots]  # each slot moves as written: \include stays \include
    moved = texts.pop([_target(m) for _, m in slots].index(path))
    texts.insert(max(0, min(to, len(texts))), moved)
    return _replace_slots(lines, slots, texts)


def retarget_input(main: str, old: str, new: str) -> str:
    _require(main, old)
    lines = _keep_ends(main)
    slots = _slots(lines)
    texts = [_canonical(new, m.group(1)) if _target(m) == old else m.group(0) for _, m in slots]  # \include stays
    return _replace_slots(lines, slots, texts)


def drop_input(main: str, path: str) -> str:
    _require(main, path)
    lines = _keep_ends(main)
    slots = _slots(lines)
    return _replace_slots(lines, slots, [None if _target(m) == path else m.group(0) for _, m in slots])


def _title_span(code: str) -> tuple[int, int] | None:
    """Span of the balanced title in `\\section{...}` on one line, braces excluded."""
    m = _SECTION.search(code)
    if not m:
        return None
    depth = 1
    for j in range(m.end(), len(code)):
        depth += (code[j] == "{") - (code[j] == "}")
        if depth == 0:
            return m.end(), j
    return None


def set_title(text: str, title: str) -> str:
    lines = _keep_ends(text)
    for i, line in enumerate(lines):
        if span := _title_span(_code(line)):
            lines[i] = line[: span[0]] + title + line[span[1]:]
            return "".join(lines)
    return f"\\section{{{title}}}\n{text}"


def split(main: str) -> tuple[str, dict[str, str]]:
    lines = _keep_ends(main)
    end = _end_index(lines)
    end = len(lines) if end is None else end
    starts = [i for i in range(end) if _SECTION.search(_code(lines[i]))]
    if not starts:
        raise InvalidInput("no_sections")
    files: dict[str, str] = {}
    for a, b in zip(starts, [*starts[1:], end]):
        span = _title_span(_code(lines[a]))
        path = section_path(lines[a][span[0]:span[1]] if span else "", set(files))
        files[path] = "".join(lines[a:b])
    inputs = [_canonical(p) + "\n" for p in files]
    return "".join([*lines[: starts[0]], *inputs, *lines[end:]]), files
