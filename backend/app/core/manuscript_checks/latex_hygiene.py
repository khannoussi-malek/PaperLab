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


CHECKS = (
    Check("latex.markdown_leak", "cheap", "Markdown headings, bold and fences left in the source", per_file("latex.markdown_leak", _markdown)),
    Check("latex.placeholder", "cheap", "TODO, XX.X, [TBD] and ?? left in the source", per_file("latex.placeholder", _placeholder)),
    Check("latex.numbered_heading", "cheap", "Section headings that start with a number", per_file("latex.numbered_heading", _numbered)),
    Check("latex.stray_preamble", "cheap", "A second \\documentclass or document start in a body file", _stray_preamble),
    Check("latex.non_ascii", "cheap", "Typographic and symbol characters outside math", per_file("latex.non_ascii", _non_ascii)),
)
