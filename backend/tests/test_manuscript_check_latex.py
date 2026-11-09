import time
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
    found = run("latex.numbered_heading",
                "\\section{1. Introduction}\n\\subsection{2.1 Setup}\n\\subsection{3) Results}\n"
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
    files = {"main.tex": "\\documentclass{article}\n\\begin{document}\\input{sections/a}\\end{document}\n",
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
    assert f.fix_hint == ("Replace with the LaTeX form (\u201c -> ``; \u201d -> ''; \u2013 -> --) "
                          "or put it in math mode. "
                          "Tectonic reads UTF-8, so this only breaks the PDF if the font lacks the glyph.")


def test_nbsp_and_greek_outside_math_are_flagged():
    [a, b] = run("latex.non_ascii", "a\u00a0b\n\u03b1 is the rate.\n")
    assert "U+00A0" in a.message and "(\u00a0 -> ~)" in a.fix_hint
    assert "U+03B1" in b.message and b.fix_hint.startswith("Replace with a LaTeX command or put it in math mode.")


def test_accents_math_comments_and_verbatim_are_silent():
    text = ("M\u00fcller and \u0160imi\u0107 wrote it. $\\alpha \u2264 3$ holds.\n% \u201ccomment\u201d\n"
            "\\begin{verbatim}\n\u201cx\u201d\n\\end{verbatim}\n")
    assert run("latex.non_ascii", text) == []


EQ = ("\\begin{equation}\ny = \\alpha x + \\beta + \\pi + \\sigma(x) + \\Theta(n)\n\\end{equation}\n"
      "Here $\\alpha$ is the slope.\n")


def test_undefined_symbol_flagged_at_its_first_display_use():
    [f] = run("latex.notation_undefined", EQ)
    assert (f.file, f.line, f.severity) == ("main.tex", 2, "warning")
    assert f.message == "\\beta appears in an equation but is never introduced in running text or a table."
    assert f.fix_hint == ('Say what it stands for where it first appears ("where \\beta is ...") '
                          'or add a notation table.')


def test_a_row_break_with_a_length_is_not_a_display_start():
    text = ("\\begin{align}\nx &= \\gamma \\\\[2pt]\n y &= 1\n\\end{align}\nwhere $\\gamma$ is a rate and \\[ z \\]\n")
    assert run("latex.notation_undefined", text) == []


def test_symbol_introduced_in_another_file_or_a_table_is_silent():
    eq = "\\begin{align}\nx &= \\gamma + \\delta\n\\end{align}\n"
    files = {"main.tex": eq, "b.tex": "where $\\gamma$ is a rate.\n\\begin{tabular}{c}$\\delta$\\end{tabular}\n"}
    assert run("latex.notation_undefined", files) == []


def test_adjacent_cites_are_hinted_never_merged():
    text = "A \\citep{a}\\citep{b}. B \\citep{c} \\citep{d}. C \\citep{e}~\\citep{f}.\n"
    found = run("latex.adjacent_cites", text)
    assert [f.severity for f in found] == ["info"] * 3
    assert found[0].message == "Adjacent citations \\citep{a}\\citep{b} print as two brackets."
    assert found[0].fix_hint == "Merge them into \\citep{a,b} so numbered styles print a range."


def test_other_adjacent_cites_are_silent():
    assert run("latex.adjacent_cites", "A \\citep{a}\\citet{b}. B \\cite{c}, \\cite{d}.\n") == []
    assert run("latex.adjacent_cites", "A \\citep[see][p.~3]{a}\\citep{b}.\n") == []


def wide(cols, wrapper=""):
    return f"\\begin{{table}}\n{wrapper}\\begin{{tabular}}{{{cols}}}\na\\\\\n\\end{{tabular}}\n\\end{{table}}\n"


def test_wide_table_flagged_with_a_hint():
    [f] = run("latex.table_width", wide("lcccccccc"))
    assert (f.line, f.severity) == (2, "info")
    assert f.message == "A table with 9 columns may run past the margin."
    assert f.fix_hint == ("Wrap the tabular in \\resizebox{\\columnwidth}{!}{...} or "
                          "\\adjustbox{max width=\\columnwidth}{...}, or use \\footnotesize.")


def test_siunitx_columns_count_once_each():
    [f] = run("latex.table_width", wide("lSSSSSSSS"))
    assert f.message == "A table with 9 columns may run past the margin."
    [g] = run("latex.table_width", wide("lS[table-format=1.2]SSSSSSS"))
    assert "9 columns" in g.message


def test_tables_that_fit_or_are_wrapped_are_silent():
    assert run("latex.table_width", wide("lcccccccc", "\\resizebox{\\columnwidth}{!}{%\n")) == []
    assert run("latex.table_width", wide("lcccccccc", "\\footnotesize\n")) == []
    assert run("latex.table_width", wide("lccc")) == []
    assert run("latex.table_width", wide("lcccccccc", "\\small\n")) == []
    assert run("latex.table_width", wide("l@{\\hspace{1em}}ccc")) == []
    assert run("latex.table_width", wide("lp{3cm}p{3cm}p{3cm}")) == []
    assert run("latex.table_width", "\\begin{tabular}{lcccccccc}\na\\\\\n\\end{tabular}\n") == []
    assert run("latex.table_width",
               "\\begin{table}\n\\begin{tabularx}{\\textwidth}{XXXXXXXXX}\na\\\\\n\\end{tabularx}\n"
               "\\end{table}\n") == []


def test_non_ascii_scan_is_linear_on_a_long_clean_text():
    # A thesis-sized file with no non-ASCII: the unanchored line regex was quadratic (2.6 s here).
    line = "We train the model on the corpus and report the mean over five seeds in the table " * 18
    start = time.perf_counter()
    assert run("latex.non_ascii", "\n".join([line[:1500]] * 390)) == []
    assert time.perf_counter() - start < 0.1


def test_stray_preamble_only_in_files_an_input_pulls_in():
    files = {"main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{sections/a}\n\\end{document}\n",
             "supplement.tex": "\\documentclass{article}\n\\begin{document}\nS\n\\end{document}\n",
             "chapters/bg.tex": "\\documentclass[../main.tex]{subfiles}\n\\begin{document}\nB\n\\end{document}\n",
             "sections/a.tex": "\\documentclass{article}\nText.\n"}
    [f] = run("latex.stray_preamble", files)
    assert f.file == "sections/a.tex"


def test_todo_definitions_are_silent_and_uses_are_flagged():
    files = {"main.tex": "\\newcommand{\\todo}[1]{}  % disabled for submission\n"
                         "\\newcommand{\\TODO}[1]{\\textcolor{red}{#1}}\nSee \\todo{fix}.\n",
             "macros.tex": "\\newcommand{\\todo}[1]{\\textcolor{red}{TODO: #1}}\n"}
    assert [(f.file, f.line) for f in run("latex.placeholder", files)] == [("main.tex", 3)]


def test_a_row_break_does_not_hide_the_prose_after_it():
    text = "\\begin{tabular}{cc}\na & b \\\\[2pt]\n\\end{tabular}\nTODO here.\n\\[ x \\]\n"
    [f] = run("latex.placeholder", text)
    assert f.line == 4


def test_a_display_after_a_row_break_is_still_read_for_notation():
    [f] = run("latex.notation_undefined", "a & b \\\\[2pt]\n\\[ \\delta > 0 \\]\n")
    assert (f.line, f.message.split()[0]) == (2, "\\delta")


def test_repeated_column_specs_count_each_column():
    [f] = run("latex.table_width", wide("l*{9}{c}"))
    assert f.message == "A table with 10 columns may run past the margin."
    assert run("latex.table_width", wide("l*{3}{p{1cm}}")) == []
    [g] = run("latex.table_width", wide("*{999999999}{c}"))  # the repeat count is capped, so this stays fast
    assert g.message == "A table with 50 columns may run past the margin."


def test_adjacent_cites_across_a_paragraph_break_are_silent():
    assert run("latex.adjacent_cites", "A \\citep{a}\n\n\\citep{b}.\n") == []
    assert [f.line for f in run("latex.adjacent_cites", "A \\citep{a}\n\\citep{b}.\n")] == [1]


def test_a_latex_quote_at_a_line_start_is_not_a_code_fence():
    assert run("latex.markdown_leak", "```nested' quote'' here.\n") == []
    assert [f.line for f in run("latex.markdown_leak", "```python\nx\n```\n")] == [1, 3]


def test_significance_stars_are_not_markdown_bold():
    assert run("latex.markdown_leak", "Gains of 0.85** & 0.91** are reported.\n") == []
    [f] = run("latex.markdown_leak", "This is **bold** text.\n")
    assert f.message == 'Markdown bold "**bold**" left in the source.'
