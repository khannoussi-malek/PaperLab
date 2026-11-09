"""P06: LaTeX hygiene checks over the source: markdown leaks, placeholders, numbered headings, stray preamble, odd
characters, undefined notation, adjacent cites, wide tables. Text-only hints; nothing is rewritten (S2P B2)."""

import re
from collections.abc import Callable, Iterator

from app.core.manuscript_checks.base import Check, CheckContext, Finding
from app.core.manuscript_sentences import DISPLAY_MATH, INLINE_MATH, _blank_comments

VERBATIM = re.compile(r"\\begin\{(verbatim|lstlisting|minted)\*?\}.*?\\end\{\1\*?\}", re.S)


def _spaces(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group())


def blank_math(text: str) -> str:
    """Verbatim and math overwritten with spaces; same length, newlines kept. Comments must already be blanked."""
    for pattern in (VERBATIM, *DISPLAY_MATH, *INLINE_MATH):
        text = pattern.sub(_spaces, text)
    return text


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def tex_files(ctx: CheckContext) -> Iterator[tuple[str, str]]:
    for path in sorted(ctx.files):
        if path.endswith(".tex"):
            yield path, ctx.files[path]


def per_file(name: str, scan: Callable[[str, str], Iterator[tuple[str, int, str, str]]]):
    """Turn `scan(blanked_comments_text, math_blanked_text)` yielding (severity, pos, message, hint) into a check."""

    def run(ctx: CheckContext) -> list[Finding]:
        found = []
        for path, text in tex_files(ctx):
            blanked = _blank_comments(text)
            for severity, pos, message, hint in scan(blanked, blank_math(blanked)):
                found.append(Finding(name, severity, path, line_of(blanked, pos), message, hint))
        return sorted(found, key=lambda f: (f.file, f.line))

    return run


MD_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+\S[^\n]*", re.M)
MD_BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")


def _markdown(_blanked: str, text: str):
    for m in MD_HEADING.finditer(text):
        yield ("error", m.start(), f'Markdown heading "{m.group().strip()}" left in the source; LaTeX stops on a bare #.',
               "Use \\section{...} or \\subsection{...}.")
    for m in MD_BOLD.finditer(text):
        yield ("warning", m.start(), f'Markdown bold "{m.group()}" left in the source.',
               "Use \\textbf{...} or, better, no emphasis in running prose.")
    for m in re.finditer(r"^[ \t]*```", text, re.M):
        yield ("warning", m.start(), "Markdown code fence left in the source.",
               "Delete the fence; use a verbatim or lstlisting environment for code.")


PLACEHOLDER = re.compile(
    r"\[\s*(?i:TBD|TODO|citation needed|cite)\s*\]|\bTODO\b|\bFIXME\b|\bTBD\b|\bXXX\b|\bX{2,}\.X+\b|(?<!\\)\?\?|\\todo\b"
)


def _placeholder(_blanked: str, text: str):
    for m in PLACEHOLDER.finditer(text):
        yield ("warning", m.start(), f'Placeholder "{m.group()}" is still in the source.',
               "Fill it in or remove it before you submit.")


NUMBERED = re.compile(
    r"\\(?:sub)*section\s*(?:\[[^\]]*\])?\s*\{\s*(\d{1,2}(?:\.\d{1,2})*[.)]?\s+[A-Za-z][^}]*)\}"  # \d{1,2} per part keeps 802.11 and 2023 silent; known noisy: `5 Whys`, `10.5 Hz sensing`. No \*? : starred headings are unnumbered, so a number there is the author's
)


def _numbered(blanked: str, _text: str):
    for m in NUMBERED.finditer(blanked):
        yield ("warning", m.start(), f'Heading "{m.group(1).strip()}" starts with a number; LaTeX numbers headings itself.',
               "Delete the number from the heading.")


STRAY = re.compile(r"\\documentclass\b|\\begin\{document\}")


def _stray_preamble(ctx: CheckContext) -> list[Finding]:
    found = []
    for path, text in tex_files(ctx):
        if path == ctx.manuscript.main_file:
            continue
        blanked = VERBATIM.sub(_spaces, _blank_comments(text))
        for m in STRAY.finditer(blanked):
            found.append(Finding(
                "latex.stray_preamble", "warning", path, line_of(blanked, m.start()),
                f"{path} contains {m.group()}; only the main file should.",
                "Remove it; this file is read through \\input and a second document start breaks the compile."))
    return found



LATEX_FORMS = {  # char -> LaTeX form named in the hint ("" = delete)
    "\u2018": "`", "\u2019": "'", "\u201c": "``", "\u201d": "''", "\u2013": "--", "\u2014": "---", "\u2212": "$-$",
    "\u00a0": "~", "\u2009": "\\,", "\u202f": "\\,", "\u2026": "\\ldots{}", "\u00d7": "$\\times$",
    "\u2264": "$\\leq$", "\u2265": "$\\geq$", "\u00b1": "$\\pm$", "\u2192": "$\\to$", "\u200b": "delete",
    "\ufeff": "delete",
}
ODD_RANGES = ((0x2000, 0x206F), (0x2190, 0x22FF), (0x0370, 0x03FF))
TECTONIC_NOTE = "Tectonic reads UTF-8, so this only breaks the PDF if the font lacks the glyph."


def _odd(ch: str) -> bool:
    return ch in LATEX_FORMS or any(lo <= ord(ch) <= hi for lo, hi in ODD_RANGES)


def _non_ascii(_blanked: str, text: str):
    for m in re.finditer(r"[^\n]*[^\x00-\x7f][^\n]*", text):
        chars = list(dict.fromkeys(c for c in m.group() if ord(c) > 127 and _odd(c)))
        if not chars:
            continue
        forms = [f"{c} -> {LATEX_FORMS[c]}" for c in chars if c in LATEX_FORMS]
        lead = f"Replace with the LaTeX form ({'; '.join(forms)})" if forms else "Replace with a LaTeX command"
        yield ("warning", m.start(),
               f"Non-ASCII characters outside math: {' '.join(chars)} ({', '.join(f'U+{ord(c):04X}' for c in chars)}).",
               f"{lead} or put it in math mode. {TECTONIC_NOTE}")



GREEK = ("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi rho varrho sigma "
         "varsigma tau upsilon phi varphi chi psi omega Gamma Theta Lambda Xi Sigma Upsilon Phi Psi Omega").split()
FUNCTION_LIKE = {"sigma", "Gamma", "Theta", "Omega"}  # \sigma(x), \Theta(n): a function or big-O, not a symbol
SYMBOL = re.compile(r"\\(" + "|".join(sorted(GREEK, key=len, reverse=True)) + r")(?![A-Za-z])")


def _symbols(text: str):
    for m in SYMBOL.finditer(text):
        if m.group(1) in FUNCTION_LIKE and text[m.end():].lstrip().startswith("("):
            continue
        yield m.group(1), m.start()


def _notation(ctx: CheckContext) -> list[Finding]:
    inline: set[str] = set()
    first: dict[str, tuple[str, int]] = {}
    for path, text in tex_files(ctx):
        blanked = _blank_comments(text)
        displays = [m for p in DISPLAY_MATH for m in p.finditer(blanked)
                    if m.start() == 0 or blanked[m.start() - 1] != "\\"]  # `\\[2pt]` (a row break) is not a display
        for m in sorted(displays, key=lambda m: m.start()):
            for name, pos in _symbols(m.group()):
                first.setdefault(name, (path, line_of(blanked, m.start() + pos)))
        rest = blanked
        for m in displays:
            rest = rest[: m.start()] + re.sub(r"[^\n]", " ", m.group()) + rest[m.end():]
        inline |= {name for p in INLINE_MATH for m in p.finditer(rest) for name, _ in _symbols(m.group())}
    return [
        Finding("latex.notation_undefined", "warning", path, line,
                f"\\{name} appears in an equation but is never introduced in running text or a table.",
                f'Say what it stands for where it first appears ("where \\{name} is ...") or add a notation table.')
        for name, (path, line) in first.items()
        if name not in inline
    ]


# Only plain pairs: a cite with an optional argument (\citep[p.~3]{a}) would lose its note in a merge.
ADJACENT = re.compile(
    r"\\(cite|citep|citet|citealp|citealt|parencite|textcite)\*?\{([^}]*)\}(?:\s|~)*\\\1\*?\{([^}]*)\}"
)


def _adjacent(blanked: str, _text: str):
    for m in ADJACENT.finditer(blanked):
        cmd, a, b = m.group(1), m.group(2), m.group(3)
        yield ("info", m.start(), f"Adjacent citations \\{cmd}{{{a}}}\\{cmd}{{{b}}} print as two brackets.",
               f"Merge them into \\{cmd}{{{a},{b}}} so numbered styles print a range.")


TABLE_WIDE_COLUMNS = 8  # calibration knob: a tabular this wide with no wrapper is worth a look
FLOAT_TABLE = re.compile(r"\\begin\{(table\*?)\}(.*?)\\end\{\1\}", re.S)
TABULAR = re.compile(r"\\begin\{tabular\}\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
FITS = re.compile(r"\\(?:resizebox|adjustbox|scalebox|small|footnotesize|scriptsize|tiny|tabcolsep)\b|\\begin\{adjustbox\}")


def _columns(spec: str) -> int:
    spec = re.sub(r"\[[^\]]*\]", "", spec)  # S[table-format=1.2]
    while (inner := re.sub(r"\{[^{}]*\}", "", spec)) != spec:  # p{3cm}, @{\hspace{1em}}, >{\bfseries}
        spec = inner
    return len(re.findall(r"[lcrpmbXS]", spec))


def _table_width(blanked: str, _text: str):
    for fl in FLOAT_TABLE.finditer(blanked):
        if FITS.search(fl.group(2)):
            continue
        for t in TABULAR.finditer(fl.group(2)):
            columns = _columns(t.group(1))
            if columns >= TABLE_WIDE_COLUMNS:
                yield ("info", fl.start(2) + t.start(), f"A table with {columns} columns may run past the margin.",
                       "Wrap the tabular in \\resizebox{\\columnwidth}{!}{...} or "
                       "\\adjustbox{max width=\\columnwidth}{...}, or use \\footnotesize.")


CHECKS = (
    Check("latex.markdown_leak", "cheap", "Markdown headings, bold and fences left in the source", per_file("latex.markdown_leak", _markdown)),
    Check("latex.placeholder", "cheap", "TODO, XX.X, [TBD] and ?? left in the source", per_file("latex.placeholder", _placeholder)),
    Check("latex.numbered_heading", "cheap", "Section headings that start with a number", per_file("latex.numbered_heading", _numbered)),
    Check("latex.stray_preamble", "cheap", "A second \\documentclass or document start in a body file", _stray_preamble),
    Check("latex.non_ascii", "cheap", "Typographic and symbol characters outside math", per_file("latex.non_ascii", _non_ascii)),
    Check("latex.notation_undefined", "cheap", "Greek symbols used in equations but never introduced", _notation),
    Check("latex.adjacent_cites", "cheap", "Back-to-back cite commands that could be one", per_file("latex.adjacent_cites", _adjacent)),
    Check("latex.table_width", "cheap", "Wide tables with no width wrapper", per_file("latex.table_width", _table_width)),
)
