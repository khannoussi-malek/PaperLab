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


CHECKS = (
    Check("latex.markdown_leak", "cheap", "Markdown headings, bold and fences left in the source", per_file("latex.markdown_leak", _markdown)),
    Check("latex.placeholder", "cheap", "TODO, XX.X, [TBD] and ?? left in the source", per_file("latex.placeholder", _placeholder)),
    Check("latex.numbered_heading", "cheap", "Section headings that start with a number", per_file("latex.numbered_heading", _numbered)),
    Check("latex.stray_preamble", "cheap", "A second \\documentclass or document start in a body file", _stray_preamble),
)
