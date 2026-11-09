from types import MappingProxyType

from app.core.manuscript_checks import latex_hygiene
from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo

INFO = ManuscriptInfo("m", "main.tex", "never", None, None, None)


def run(name, files):
    files = files if isinstance(files, dict) else {"main.tex": files}
    check = next(c for c in latex_hygiene.CHECKS if c.name == name)
    return check.run(CheckContext(MappingProxyType(files), frozenset(), INFO))


def test_markdown_leaks_have_the_right_severity_line_and_text():
    found = run("latex.markdown_leak", "## Intro\nSome **bold** text.\n```\n")
    assert [(f.line, f.severity) for f in found] == [(1, "error"), (2, "warning"), (3, "warning")]
    assert found[0].message == 'Markdown heading "## Intro" left in the source; LaTeX stops on a bare #.'
    assert found[0].fix_hint == "Use \\section{...} or \\subsection{...}."
    assert found[1].message == 'Markdown bold "**bold**" left in the source.'
    assert found[2].message == "Markdown code fence left in the source."


def test_markdown_lookalikes_are_silent():
    text = ("\\newcommand{\\x}[1]{#1}\n\\def\\y#1{#1}\n$a**b$\n\\begin{verbatim}\n## not a heading\n```\n"
            "\\end{verbatim}\n% ## comment\n")
    assert run("latex.markdown_leak", text) == []
    assert run("latex.markdown_leak", "He wrote ```nested' quote'' here.\n") == []  # LaTeX quotes, not a fence


def test_placeholders_each_reported_once():
    text = "TODO: cite.\nAccuracy is XX.X percent and [TBD] more ?? here.\nSee \\todo{fix}.\n"
    found = run("latex.placeholder", text)
    assert [(f.line, f.message.split('"')[1]) for f in found] == [
        (1, "TODO"), (2, "XX.X"), (2, "[TBD]"), (2, "??"), (3, "\\todo")]
    assert found[0].message == 'Placeholder "TODO" is still in the source.'
    assert found[0].fix_hint == "Fill it in or remove it before you submit."


def test_placeholder_lookalikes_are_silent():
    text = "Chapter XX covers it. Is it? Yes.\nSee \\ref{a}. % TODO later\nAn $XX.X$ value.\n"
    assert run("latex.placeholder", text) == []


def test_numbered_headings():
    found = run("latex.numbered_heading", "\\section{1. Introduction}\n\\subsection{2.1 Setup}\n\\subsection{3) Results}\n"
                "\\section{2 Method}\n")
    assert [f.line for f in found] == [1, 2, 3, 4]
    assert found[0].message == 'Heading "1. Introduction" starts with a number; LaTeX numbers headings itself.'
    assert found[0].fix_hint == "Delete the number from the heading."


def test_headings_that_only_look_numbered_are_silent():
    text = ("\\section{3D reconstruction}\n\\section{2023 results}\n\\section{Introduction}\n"
            "\\section{2.5D mapping}\n\\section{802.11 networks}\n\\section{3.5mm sensors}\n"
            "\\section*{1. Unnumbered by LaTeX}\n")
    assert run("latex.numbered_heading", text) == []


def test_stray_preamble_in_a_non_main_file_only():
    files = {"main.tex": "\\documentclass{article}\n\\begin{document}x\\end{document}\n",
             "sections/a.tex": "\\documentclass{article}\nText.\n",
             "sections/code.tex": "\\begin{lstlisting}\n\\documentclass{article}\n\\end{lstlisting}\n",
             "refs.bib": "@misc{a, title={\\documentclass}}"}
    [f] = run("latex.stray_preamble", files)
    assert (f.file, f.line, f.severity) == ("sections/a.tex", 1, "warning")
    assert f.message == "sections/a.tex contains \\documentclass; only the main file should."
    assert f.fix_hint == "Remove it; this file is read through \\input and a second document start breaks the compile."


def test_typography_characters_are_listed_once_per_line():
    [f] = run("latex.non_ascii", "He said \u201chi\u201d \u2013 then left.\n")
    assert (f.line, f.severity) == (1, "warning")
    assert f.message == "Non-ASCII characters outside math: \u201c \u201d \u2013 (U+201C, U+201D, U+2013)."
    assert f.fix_hint == ("Replace with the LaTeX form (\u201c -> ``; \u201d -> ''; \u2013 -> --) or put it in math mode. "
                          "Tectonic reads UTF-8, so this only breaks the PDF if the font lacks the glyph.")


def test_nbsp_and_greek_outside_math_are_flagged():
    [a, b] = run("latex.non_ascii", "a\u00a0b\n\u03b1 is the rate.\n")
    assert "U+00A0" in a.message and "(\u00a0 -> ~)" in a.fix_hint
    assert "U+03B1" in b.message and b.fix_hint.startswith("Replace with a LaTeX command or put it in math mode.")


def test_accents_math_comments_and_verbatim_are_silent():
    text = ("M\u00fcller and \u0160imi\u0107 wrote it. $\\alpha \u2264 3$ holds.\n% \u201ccomment\u201d\n"
            "\\begin{verbatim}\n\u201cx\u201d\n\\end{verbatim}\n")
    assert run("latex.non_ascii", text) == []
