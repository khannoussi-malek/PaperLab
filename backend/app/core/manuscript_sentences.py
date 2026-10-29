"""A manuscript's LaTeX source as prose sentences with exact offsets, hashes and cite keys (M27d)."""

import hashlib
import re
from dataclasses import dataclass

from pylatexenc.latex2text import LatexNodes2Text

from app.core.manuscript_bib import CITE, COMMENT

LATEX = LatexNodes2Text()
FLOAT_ENVS = "tabular|table|figure|tikzpicture|axis|lstlisting|verbatim|minted|thebibliography"
MATH_ENVS = "equation|align|gather|multline|eqnarray|displaymath"
# Masked with BOUNDARY (a sentence never crosses it), MATH (invisible to sentence ends: the sentence runs on through
# it) or IGNORED (a space).
BOUNDARY, MATH, IGNORED = "\0", "\1", " "
FLOATS = re.compile(rf"\\begin\{{({FLOAT_ENVS})(\*?)\}}.*?\\end\{{\1\2\}}", re.S)
DISPLAY_MATH = [
    re.compile(rf"\\begin\{{({MATH_ENVS})(\*?)\}}.*?\\end\{{\1\2\}}", re.S),
    re.compile(r"(?<!\\)\$\$.*?(?<!\\)\$\$", re.S),
    re.compile(r"\\\[.*?\\\]", re.S),
]
INLINE_MATH = [re.compile(r"(?<!\\)\$[^$]*?(?<!\\)\$", re.S), re.compile(r"\\\(.*?\\\)", re.S)]
TOKENS = [
    re.compile(r"\\(?:begin|end)\{[^}]*\}(?:\[[^\]]*\])?"),
    re.compile(r"\\item\b(?:\s*\[[^\]]*\])?"),
    re.compile(r"\\(?:maketitle|bibliographystyle\{[^}]*\})"),
]
ARG_COMMANDS = re.compile(
    r"\\(?:(part|chapter|(?:sub)*section|(?:sub)?paragraph|caption|input|include|bibliography|usepackage|documentclass"
    r"|label|ref))\*?(?:\s*\[[^\]]*\])?\s*\{"
)
IGNORED_COMMANDS = {"label", "ref"}
ABBREVIATIONS = {
    "al",
    "e.g",
    "i.e",
    "cf",
    "vs",
    "Fig",
    "Figs",
    "Eq",
    "Eqs",
    "Sec",
    "Tab",
    "Ref",
    "No",
    "Dr",
    "approx",
    "resp",
}
INITIALISM = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]")
WS = " \t\r\n" + MATH
LAST_WORD = re.compile(r"[A-Za-z][A-Za-z.]*$")
BLANK_LINE = re.compile(r"\n[ \t]*\n")
CLOSERS = (")", '"', "''", "}")
MIN_WORDS = 4


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    raw: str
    norm: str
    hash: str
    plain: str
    keys: tuple[str, ...]


def claim_hash(raw: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", raw.strip()).encode()).hexdigest()


def to_plain(raw: str) -> str:
    text = COMMENT.sub("", raw)
    for pattern in DISPLAY_MATH:
        text = pattern.sub(" [math] ", text)
    text = re.sub(r"~?\s*" + CITE.pattern, "", text)
    text = re.sub(r"\\(?:label|ref)\{[^}]*\}", "", text).replace("~", " ")
    return " ".join(LATEX.latex_to_text(text).split())


def _blank_comments(text: str) -> str:
    return COMMENT.sub(lambda m: " " * len(m.group()), text)


def _brace_end(text: str, open_at: int) -> int:
    """Index just past the brace group opening at `open_at` (the end of text when it never closes)."""
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


def _mask(text: str) -> str:
    """The comment-blanked text with every non-prose piece overwritten (same length, so offsets stay valid)."""
    chars = list(text)

    def put(a: int, b: int, fill: str) -> None:
        chars[a:b] = fill * (b - a)

    begin = text.find("\\begin{document}")
    if begin >= 0:
        put(0, begin + len("\\begin{document}"), BOUNDARY)
    end = text.find("\\end{document}")
    if end >= 0:
        put(end, len(text), BOUNDARY)

    def run(pattern: re.Pattern, fill: str) -> None:
        for m in pattern.finditer("".join(chars)):
            put(m.start(), m.end(), fill)

    run(FLOATS, BOUNDARY)
    for pattern in DISPLAY_MATH:
        run(pattern, MATH)
    for pattern in TOKENS:
        run(pattern, BOUNDARY)
    for m in ARG_COMMANDS.finditer("".join(chars)):
        put(m.start(), _brace_end(text, m.end() - 1), IGNORED if m.group(1) in IGNORED_COMMANDS else BOUNDARY)
    for pattern in INLINE_MATH:
        run(pattern, MATH)
    return "".join(chars)


def _chunk_ends(chunk: str):
    """Yield the (exclusive) end offset of each sentence in a chunk free of blank lines and boundaries."""
    for m in re.finditer(r"[.?!]", chunk):
        i = m.end()
        while (c := next((c for c in CLOSERS if chunk.startswith(c, i)), None)) is not None:
            i += len(c)
        if i < len(chunk) and not chunk[i].isspace():
            continue
        word = LAST_WORD.search(chunk[: m.start()]) if m.group() == "." else None
        word = word.group() if word else ""
        if word in ABBREVIATIONS or (len(word) == 1 and word.isupper()):
            continue
        if i < len(chunk) and INITIALISM.fullmatch(word):  # U.S. in mid-text; at a chunk end it does end
            continue
        yield i
    yield len(chunk)


def split_sentences(text: str) -> list[Sentence]:
    blanked = _blank_comments(text)
    masked = _mask(blanked)
    found: list[Sentence] = []
    for segment in re.finditer(r"[^\0]+", masked):
        base = segment.start()
        cuts = [(0, 0)] + [(m.start(), m.end()) for m in BLANK_LINE.finditer(segment.group())]
        bounds = [(c[1], n[0]) for c, n in zip(cuts, cuts[1:] + [(len(segment.group()),) * 2])]
        for a, b in bounds:
            chunk, pos = segment.group()[a:b], 0
            for stop in _chunk_ends(chunk):
                piece = chunk[pos:stop]
                lead = len(piece) - len(piece.lstrip(WS))
                start, end = base + a + pos + lead, base + a + pos + len(piece.rstrip(WS))
                pos = stop
                raw = text[start:end]
                if not raw.strip():
                    continue
                plain = to_plain(raw)
                if len(plain.split()) < MIN_WORDS:
                    continue
                keys = tuple(
                    dict.fromkeys(
                        k.strip() for g in CITE.findall(blanked[start:end]) for k in g.split(",") if k.strip()
                    )
                )
                found.append(Sentence(start, end, raw, " ".join(raw.split()), claim_hash(raw), plain, keys))
    return found


def in_range(sentences: list[Sentence], start: int, end: int) -> list[Sentence]:
    """The sentences overlapping [start, end); an empty range gives the one containing `start`."""
    if start >= end:
        return [s for s in sentences if s.start <= start <= s.end][:1]
    return [s for s in sentences if s.start < end and s.end > start]


def cite_spans(text: str) -> list[tuple[str, int]]:
    """Every cited key with the 1-based line of its command (comments ignored)."""
    blanked = _blank_comments(text)
    return [
        (key.strip(), blanked.count("\n", 0, m.start()) + 1)
        for m in CITE.finditer(blanked)
        for key in m.group(1).split(",")
        if key.strip()
    ]
