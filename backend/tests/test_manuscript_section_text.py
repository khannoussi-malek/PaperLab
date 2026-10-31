from pathlib import Path

from app.core.manuscript_section_text import section_slices
from app.core.manuscript_sentences import claim_hash

SAMPLE = (Path(__file__).parent / "fixtures" / "section_sample.tex").read_text()


def _slices(text=SAMPLE, path="main.tex", main="main.tex"):
    return section_slices(text, path=path, main_file=main)


def test_fixture_slices():
    s = _slices()
    assert [x.title for x in s] == [
        "Introduction",
        "Methods",
        "Results and Findings",
        "A Weird Title",
        "Acknowledgements",
    ]
    assert SAMPLE[s[0].start :].startswith("\\section{Introduction}")
    assert "\\subsection{Setting}" in SAMPLE[s[0].start : s[0].end]
    assert "Hidden" not in s[0].norm and "\\section{Hidden}" not in s[0].norm
    assert SAMPLE[s[1].start :].startswith("\\section*{Methods}")
    assert SAMPLE[s[2].start :].startswith("\\section[Short]{Results")
    assert SAMPLE[s[4].start : s[4].end].rstrip().endswith("Thanks to all.")  # \appendix ends it
    assert all(a.end <= b.start for a, b in zip(s, s[1:]))
    assert s[1].hash == claim_hash(SAMPLE[s[1].start : s[1].end])
    assert s[1].words > 0


def test_guesses():
    assert [x.guess for x in _slices()] == ["intro", "method", "results", None, None]


def test_main_with_inputs_has_no_slices():
    main = "\\begin{document}\n\\input{sections/a}\n\\section{Stray}\nwords\n\\end{document}\n"
    assert _slices(main) == []


def test_section_file_keeps_text_before_first_section():
    text = "Some lead in words.\n\\section{Method}\nWe did it.\n"
    (s,) = _slices(text, path="sections/m.tex")
    assert (s.start, s.title, s.guess) == (0, "Method", "method")


def test_heading_free_file_needs_twenty_words():
    short = "word " * 19
    long = "word " * 20
    assert _slices(short, path="sections/plain.tex") == []
    (s,) = _slices(long, path="sections/plain.tex")
    assert (s.title, s.guess, s.start) == ("plain", None, 0)


def test_hash_ignores_reflow_but_not_a_changed_word():
    a = "\\section{Introduction}\nWe study  retrieval\nfor papers.\n"
    b = "\\section{Introduction}\nWe study retrieval for   papers.\n"
    c = "\\section{Introduction}\nWe study retrieval for books.\n"
    ha, hb, hc = (_slices(t, path="s.tex")[0].hash for t in (a, b, c))
    assert ha == hb != hc
