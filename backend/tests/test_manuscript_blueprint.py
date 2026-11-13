import pytest

from app.core import manuscript_blueprint as bp


def test_parse_accepts_a_full_file_and_an_empty_object():
    spec = bp.parse('{"title": "T", "contributions": ["a"], "notation": [{"symbol": "\\\\alpha", "meaning": "w"}],'
                    ' "target_words": {"method": [100, 200]}}')
    assert spec.target_words["method"] == (100, 200) and spec.notation[0].symbol == "\\alpha"
    assert bp.parse("{}").contributions == []


@pytest.mark.parametrize("text", [
    "[]", "nope", '{"colour": 1}', '{"target_words": {"a": [5, 2]}}', '{"target_words": {"a": [-1, 2]}}',
    '{"contributions": ' + str(["x"] * 13).replace("'", '"') + "}", '{"notation": [{"symbol": "", "meaning": "m"}]}',
])
def test_parse_rejects_bad_files(text):
    with pytest.raises(ValueError):  # ValidationError and JSON errors are both ValueError
        bp.parse(text)


def test_slug():
    assert bp.slug("Related work") == "related-work" and bp.slug("  Method & Setup! ") == "method-setup"


def test_sections_split_per_file_and_stop_at_the_bibliography():
    files = {"main.tex": "\\section{Intro}\none two\n\\section{Method}\nthree\n\\bibliography{x}\nignored words here\n",
             "sections/r.tex": "\\section{Results}\nfour five six\n"}
    got = {s.id: (s.path, s.line, s.words) for s in bp.sections(files)}
    assert got == {"intro": ("main.tex", 1, 2), "method": ("main.tex", 3, 1), "results": ("sections/r.tex", 1, 3)}


def test_count_ignores_comments_math_cites_and_environment_names():
    text = ("\\section{A}\n% five hidden words in a comment\n"
            "We show $x = \\alpha + 1$ in \\cite{k1,k2} and \\ref{fig:a}.\n"
            "\\begin{figure}\\end{figure}\n\\textbf{Bold} text.\n")
    assert bp.sections({"main.tex": text})[0].words == 6  # We show in and Bold text (+ "A" is the heading, not counted)


def test_tables_figures_and_file_names_are_not_words_and_input_marks_unmeasurable():
    body = ("\\section{R}\nOne two.\n"
            "\\begin{table}\\begin{tabular}{lcc} a & 0.91 & 0.85 \\\\ \\end{tabular}\\end{table}\n"
            "\\includegraphics[width=3cm]{fig/plot.pdf}\n\\bibliographystyle{plain}\n")
    got = bp.sections({"main.tex": body, "b.tex": "\\section{Q}\n\\input{sections/q}\n"})
    assert {s.id: (s.words, s.measurable) for s in got} == {"r": (2, True), "q": (0, False)}


def test_band_prefers_the_blueprint_then_the_template():
    spec = bp.parse('{"target_words": {"method": [1, 2]}}')
    assert bp.band(spec, "method", "article") == (1, 2)
    assert bp.band(spec, "introduction", "article") == (400, 900)
    assert bp.band(spec, "introduction", "custom") is None and bp.band(spec, "nope", "article") is None


@pytest.mark.parametrize("tex, want", [
    ("\\title{What Works}", "What Works"),
    ("\\title[Short]{Long \\\\ Title}", "Long Title"),
    ("\\title{A\\thanks{Funded by X.} B}", "A B"),
    ("% \\title{Old}\n\\title{New}", "New"),
    ("\\title{\\textbf{Bold} words}", "Bold words"),
    ("\\title{Foo\\\\ \\large Bar}", "Foo Bar"),
    ("\\title{Line one\\newline line two}", "Line one line two"),
    ("\\title{Half 50\\% done % a comment\n}", "Half 50% done"),
    ("\\title{Nested {braces} stay}", "Nested braces stay"),
    ("\\title{}", None),
    ("\\title{\\thanks{only a note}}", None),
    ("\\section{No title here}", None),
    ("\\title{Unclosed", None),
])
def test_latex_title_is_readable_plain_text(tex, want):
    assert bp.latex_title(tex) == want
