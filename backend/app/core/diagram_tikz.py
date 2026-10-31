"""Checks a generated TikZ picture before it is compiled or inserted (M27e). Pure text; no web framework.

The code comes from a model and is compiled, so this is a security boundary: strict allowlists, no clever parsing.
"""

import re

ALLOWED_LIBRARIES: tuple[str, ...] = (
    "arrows.meta",
    "positioning",
    "shapes.geometric",
    "shapes.misc",
    "shapes.multipart",
    "fit",
    "calc",
    "backgrounds",
    "chains",
    "matrix",
    "decorations.pathreplacing",
    "decorations.markings",
)  # must equal the \usetikzlibrary set in manuscript_templates/warm-diagram.tex (a test checks)
MAX_CHARS = 20_000
# A control-sequence name is denied when it is one of these, or contains any of DENIED_PARTS (case ignored), so the
# `@`, expl3, XeTeX and pgf spellings of the same operations are caught too (`\@@input`, `\file_get:nnN`,
# `\XeTeXpdffile`, `\pgfimage`). Names are read twice, from the raw code (comments included) and with comments
# stripped the way TeX does (a comment can join `\inp%⏎ut` back into `\input`), with any whitespace after the backslash.
DENIED = (
    "usepackage",
    "RequirePackage",
    "documentclass",
    "include",
    "includegraphics",
    "immediate",
    "directlua",
    "scantokens",
    "special",
    "caption",
    "label",
    "ref",
    "endinput",
    "UseName",
    "usetikzlibrary",
    "usepgflibrary",
    "usepgfmodule",
    "gdef",
    "xdef",
    "global",
    "AtEndDocument",
    "AtBeginDocument",
)  # ponytail: a denylist over TeX can't be complete; the compile sandbox (latex_compile) is the real wall
DENIED_PARTS = (
    "input",
    "file",
    "image",
    "write",
    "read",
    "open",
    "csname",
    "catcode",
    "makeat",
    "explsyntax",
    "xetex",
    "hook",
    "pdfobj",
)
_CS = re.compile(r"\\(?:\s*([A-Za-z@_:]+)|.)", re.S)  # `\\` is one token: `{Token\\Input}` is text
_COMMENT = re.compile(r"(\\.)|%[^\n]*(?:\n[ \t]*)?", re.S)
_LIBS = re.compile(r"\\usetikzlibrary\s*\{([^}]*)\}")
_BEGIN = re.compile(r"\\begin\s*\{tikzpicture\}")
_END = re.compile(r"\\end\s*\{tikzpicture\}")
# Where a picture carries text: `\\node`, a `node` on a path or edge (`-- node[above] {yes} (b)`), and `label=` /
# `pin=` options. `node distance`, `every node/.style` and `nodes=` are keys, not text.
_NODE = re.compile(r"\\node(?![A-Za-z])|(?<![\w\\])node(?=\s*(?:[\[({]|at\b))")
_LABEL_KEY = re.compile(r"(?<![A-Za-z])(?:label|pin)\s*=\s*")
_WHERE = r"(?:above|below|left|right|north|south|east|west|center|base)(?:\s+(?:left|right|east|west))?"
_POSITION = re.compile(r"^\s*(?:\[[^\]]*\])?\s*(?:" + _WHERE + r"|-?\d+(?:\.\d+)?)\s*:(?!:)")  # a TikZ position only


def split_code(raw: str) -> tuple[list[str], str]:
    """Lifts every `\\usetikzlibrary{a,b}` out of `raw`: the deduped libraries, and the rest trimmed."""
    libs: list[str] = []
    for group in _LIBS.findall(raw):
        for name in (n.strip() for n in group.split(",")):
            if name and name not in libs:
                libs.append(name)
    return libs, _LIBS.sub("", raw).strip()


def strip_comments(code: str) -> str:
    """Drops each `%` comment with its line end and the next line's leading blanks, as TeX reads it; `\\%` stays."""
    return _COMMENT.sub(lambda m: m.group(1) or "", code)


def _denied(name: str) -> bool:
    low = name.lower()
    return name in DENIED or any(part in low for part in DENIED_PARTS)


def check(libraries: list[str], picture: str) -> list[str]:
    """Plain-language problems; empty when the picture is safe to compile and insert."""
    errors = [
        f"The diagram uses the TikZ library {lib}, which PaperLab doesn't include offline."
        for lib in libraries
        if lib not in ALLOWED_LIBRARIES
    ]
    if len(picture) > MAX_CHARS:
        errors.append(f"The diagram code is too long ({MAX_CHARS:,} characters at most).")
    code = strip_comments(picture).strip()
    begins, ends = list(_BEGIN.finditer(code)), list(_END.finditer(code))
    if len(begins) != 1 or len(ends) != 1 or begins[0].start() != 0 or ends[0].end() != len(code):
        errors.append("The diagram must be exactly one tikzpicture, with nothing but comments around it.")
    names = {n for text in (picture, code) for n in _CS.findall(text) if n and _denied(n)}
    for name in sorted(names):
        errors.append(f"The diagram code uses \\{name}, which PaperLab doesn't allow in a diagram.")
    if "^^" in picture:
        errors.append("The diagram code uses a character escape (^^), which PaperLab doesn't allow.")
    return errors


def _flat(text: str) -> str:
    flat = re.sub(r"\\[A-Za-z]+", " ", text.replace("\\\\", " "))
    return " ".join(flat.replace("{", " ").replace("}", " ").split())


def _option_value(s: str, i: int) -> str:
    """A `label=` / `pin=` value from `i`: a brace group, else up to the next `,` or `]`."""
    if s[i : i + 1] == "{":
        return _balanced(s, i) or ""
    end = re.search(r"[,\]]", s[i:])
    return s[i : i + end.start()] if end else s[i:]


def node_labels(picture: str) -> list[str]:
    """Every text the picture shows: node texts (`\\node`, and `node` on paths and edges) and `label=`/`pin=` texts,
    braces and line breaks flattened. ponytail: `matrix of nodes` cell text isn't read; parse cells if it matters."""
    out = []
    for m in _NODE.finditer(picture):
        text = _first_group(picture, m.end())
        if text is not None:
            out.append(_flat(text))
    for m in _LABEL_KEY.finditer(picture):
        out.append(_flat(_POSITION.sub("", _option_value(picture, m.end()), count=1)))
    return [label for label in out if label]


def drop_comments(code: str) -> str:
    """Model `%` comments removed (a comment-only line goes entirely); `\\%` stays. Generated code reaches the
    researcher's file only through these lines, so no model prose rides along in a comment (D118)."""
    lines = []
    for line in code.split("\n"):
        kept = re.sub(r"(\\.)|%.*", lambda m: m.group(1) or "", line).rstrip()
        if kept or not line.lstrip().startswith("%"):
            lines.append(kept)
    return "\n".join(lines).strip()


def _first_group(s: str, i: int) -> str | None:
    """The first brace group after `i` that sits outside any [options] or (coordinates), up to the `;`."""
    depth = 0  # [] and () nesting
    while i < len(s) and s[i] != ";":
        c = s[i]
        if c in "[(":
            depth += 1
        elif c in "])":
            depth -= 1
        elif c == "{" and depth == 0:
            return _balanced(s, i)
        elif c == "{":  # braces inside options, e.g. label={…}: skip the whole group
            i = len(s) if _balanced(s, i) is None else _skip(s, i)
            continue
        i += 1
    return None


def _skip(s: str, i: int) -> int:
    level = 0
    for j in range(i, len(s)):
        level += (s[j] == "{") - (s[j] == "}")
        if level == 0:
            return j + 1
    return len(s)


def _balanced(s: str, i: int) -> str | None:
    end = _skip(s, i)
    return s[i + 1 : end - 1] if s[end - 1 : end] == "}" else None


_WORD = re.compile(r"[^\W\d_]{2,}")


def _said(word: str, known: set[str]) -> bool:
    """`word` or its light singular/plural is in `known` (both lower case)."""
    w = word.lower()
    forms = {w, w + "s", w + "es", w[:-1] if w.endswith("s") else w, w[:-2] if w.endswith("es") else w}
    return not forms.isdisjoint(known)


def labels_not_in_description(picture: str, description: str) -> list[str]:
    """Labels with a word (2+ letters) the description never says; numbers and single letters are ignored."""
    known = {w.lower() for w in _WORD.findall(description)}
    return [label for label in node_labels(picture) if not all(_said(w, known) for w in _WORD.findall(label))]


# `preview` crops the page to the picture. The `standalone` class would too, but it probes /dev/null, which the compile
# sandbox reads as an outside-file access and refuses.
PREAMBLE = (
    "\\documentclass{article}\n\\usepackage{tikz}\n\\usepackage[active,tightpage]{preview}\n"
    "\\PreviewEnvironment{tikzpicture}\n\\setlength\\PreviewBorder{4pt}\n"
)


def preview_document(libraries: list[str], picture: str) -> str:
    """The picture on a page cropped to it, so the preview isn't a mostly-empty letter page."""
    return f"{PREAMBLE}\\usetikzlibrary{{{','.join(libraries)}}}\n\\begin{{document}}\n{picture}\n\\end{{document}}\n"
