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
# Matched anywhere, comments included, with any whitespace after the backslash: `\ input` is rejected too.
DENIED = (
    "usepackage",
    "documentclass",
    "input",
    "include",
    "write",
    "openout",
    "openin",
    "read",
    "readline",
    "immediate",
    "catcode",
    "directlua",
    "caption",
    "label",
    "ref",
    "includegraphics",
    "csname",
    "scantokens",
    "InputIfFileExists",
    "lstinputlisting",
    "verbatiminput",
    "special",
    "openoutput",
    "pdfobj",
    "pdffiledump",
    "endinput",
)
_DENIED = re.compile(r"\\\s*(" + "|".join(DENIED) + r")(?![A-Za-z])")
_LIBS = re.compile(r"\\usetikzlibrary\s*\{([^}]*)\}")
_BEGIN = re.compile(r"\\begin\s*\{tikzpicture\}")
_END = re.compile(r"\\end\s*\{tikzpicture\}")
_SHELL = re.compile(r"(?:\s|%[^\n]*)*\\begin\s*\{tikzpicture\}.*\\end\s*\{tikzpicture\}(?:\s|%[^\n]*)*", re.S)
_NODE = re.compile(r"\\node(?![A-Za-z])")


def split_code(raw: str) -> tuple[list[str], str]:
    """Lifts every `\\usetikzlibrary{a,b}` out of `raw`: the deduped libraries, and the rest trimmed."""
    libs: list[str] = []
    for group in _LIBS.findall(raw):
        for name in (n.strip() for n in group.split(",")):
            if name and name not in libs:
                libs.append(name)
    return libs, _LIBS.sub("", raw).strip()


def check(libraries: list[str], picture: str) -> list[str]:
    """Plain-language problems; empty when the picture is safe to compile and insert."""
    errors = [
        f"The diagram uses the TikZ library {lib}, which PaperLab doesn't include offline."
        for lib in libraries
        if lib not in ALLOWED_LIBRARIES
    ]
    if len(picture) > MAX_CHARS:
        errors.append(f"The diagram code is too long ({MAX_CHARS:,} characters at most).")
    if len(_BEGIN.findall(picture)) != 1 or len(_END.findall(picture)) != 1 or not _SHELL.fullmatch(picture):
        errors.append("The diagram must be exactly one tikzpicture, with nothing but comments around it.")
    for name in sorted(set(_DENIED.findall(picture))):
        errors.append(f"The diagram code uses \\{name}, which PaperLab doesn't allow in a diagram.")
    if "^^" in picture:
        errors.append("The diagram code uses a character escape (^^), which PaperLab doesn't allow.")
    return errors


def node_labels(picture: str) -> list[str]:
    """The `{…}` text of each `\\node`, braces and line breaks flattened."""
    out = []
    for m in _NODE.finditer(picture):
        text = _first_group(picture, m.end())
        if text is not None:
            flat = re.sub(r"\\[A-Za-z]+", " ", text.replace("\\\\", " "))
            out.append(" ".join(flat.replace("{", " ").replace("}", " ").split()))
    return out


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


def _norm(word: str) -> str:
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def labels_not_in_description(picture: str, description: str) -> list[str]:
    """Labels with a word (2+ letters) the description never says; numbers and single letters are ignored."""
    known = {_norm(w) for w in re.findall(r"[A-Za-z]{2,}", description)}
    return [
        label
        for label in node_labels(picture)
        if any(_norm(w) not in known for w in re.findall(r"[A-Za-z]{2,}", label))
    ]


# `preview` crops the page to the picture. The `standalone` class would too, but it probes /dev/null, which the compile
# sandbox reads as an outside-file access and refuses.
PREAMBLE = (
    "\\documentclass{article}\n\\usepackage{tikz}\n\\usepackage[active,tightpage]{preview}\n"
    "\\PreviewEnvironment{tikzpicture}\n\\setlength\\PreviewBorder{4pt}\n"
)


def standalone_document(libraries: list[str], picture: str) -> str:
    """The picture on a page cropped to it, so the preview isn't a mostly-empty letter page."""
    return f"{PREAMBLE}\\usetikzlibrary{{{','.join(libraries)}}}\n\\begin{{document}}\n{picture}\n\\end{{document}}\n"
