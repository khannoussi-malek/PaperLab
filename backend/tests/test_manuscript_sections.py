# ruff: noqa: E501
import pytest

from app.core.errors import InvalidInput
from app.core.manuscript_sections import (
    check_title,
    drop_input,
    input_lines,
    insert_input,
    move_input,
    retarget_input,
    section_path,
    set_title,
    split,
)

MAIN = "\\begin{document}\n\\input{sections/intro}\n\\clearpage\n\\input{sections/method.tex}\n% \\input{sections/old}\n\\bibliography{paperlab}\n\\end{document}\n"


def test_input_lines_reads_both_forms_and_skips_comments():
    assert [(x.index, x.target) for x in input_lines(MAIN)] == [(1, "sections/intro.tex"), (3, "sections/method.tex")]
    assert [x.target for x in input_lines("\\input{ a }\\include{b}\n")] == ["a.tex", "b.tex"]
    assert [x.target for x in input_lines("\\input {sections/x}\n")] == ["sections/x.tex"]
    assert input_lines("\\input sections/x\n") == []
    assert [x.target for x in input_lines("\\input{a} % \\input{b}\n100\\% \\input{c}\n")] == ["a.tex", "c.tex"]


def test_section_path_slugs():
    assert section_path("Résultats", set()) == "sections/resultats.tex"
    assert section_path("方法", set()) == "sections/section.tex"
    assert section_path("A/B tests", set()) == "sections/a-b-tests.tex"
    assert section_path("Method", {"sections/method.tex"}) == "sections/method-2.tex"
    assert section_path("Method", {"sections/method.tex", "sections/method-2.tex"}) == "sections/method-3.tex"


def test_insert_after_a_section_and_at_the_end():
    assert insert_input(MAIN, "sections/new.tex", after="sections/intro.tex").splitlines()[2] == "\\input{sections/new}"
    assert insert_input(MAIN, "sections/new.tex", after=None).splitlines()[4] == "\\input{sections/new}"
    assert "\\input{sections/a}\n\\bibliography" in insert_input("\\begin{document}\n\\bibliography{x}\n\\end{document}\n", "sections/a.tex", None)
    with pytest.raises(InvalidInput, match="no_end_document"):
        insert_input("hello\n", "sections/a.tex", None)
    with pytest.raises(InvalidInput, match="not_a_section"):
        insert_input(MAIN, "sections/new.tex", after="sections/zzz.tex")


def test_move_swaps_slots_and_keeps_lines_between():
    moved = move_input(MAIN, "sections/method.tex", to=0).splitlines()
    assert moved[1:4] == ["\\input{sections/method.tex}", "\\clearpage", "\\input{sections/intro}"]  # each slot keeps its text
    with pytest.raises(InvalidInput, match="not_a_section"):
        move_input(MAIN, "sections/old.tex", to=0)


def test_retarget_drop_and_unknown():
    assert "\\input{sections/b}" in retarget_input(MAIN, "sections/intro.tex", "sections/b.tex")
    assert "sections/intro" not in drop_input(MAIN, "sections/intro.tex")
    with pytest.raises(InvalidInput, match="not_a_section"):
        drop_input(MAIN, "sections/old.tex")
    with pytest.raises(InvalidInput, match="not_a_section"):
        retarget_input(MAIN, "sections/old.tex", "sections/b.tex")


def test_split_moves_each_section_and_keeps_the_rest():
    main = "\\begin{document}\nIntro text.\n\\section{Intro}\nA.\n\\section*{Method}\nB.\n\\appendix\n\\section{Extra}\nC.\n\\bibliography{x}\n\\end{document}\n"
    new_main, files = split(main)
    assert files == {"sections/intro.tex": "\\section{Intro}\nA.\n", "sections/method.tex": "\\section*{Method}\nB.\n"}
    assert new_main == "\\begin{document}\nIntro text.\n\\input{sections/intro}\n\\input{sections/method}\n\\appendix\n\\section{Extra}\nC.\n\\bibliography{x}\n\\end{document}\n"
    with pytest.raises(InvalidInput, match="no_sections"):
        split("\\begin{document}\nx\n\\end{document}\n")


def test_check_title():
    assert check_title("  A  ") == "A"
    for bad in ["", "   ", "x" * 201, "a{b", "a}b", "}a{", "a\nb", "a\rb", "50% done", "%"]:
        with pytest.raises(InvalidInput, match="bad_title"):
            check_title(bad)
    assert check_title("A {B} c") == "A {B} c"
    assert check_title("50\\% done") == "50\\% done"


def test_set_title_both_ways():
    assert set_title("\\section{Old}\nText\n", "New") == "\\section{New}\nText\n"
    assert set_title("x\n\\section*{Old {a}}\nT\n", "New") == "x\n\\section*{New}\nT\n"
    assert set_title("Text\n", "New") == "\\section{New}\nText\n"


def test_reorder_and_retitle_keep_include_and_its_form():
    main = "\\begin{document}\n\\include{chapters/a}\n\\input{ b.tex }\n\\end{document}\n"
    assert move_input(main, "b.tex", to=0).splitlines()[1:3] == ["\\input{ b.tex }", "\\include{chapters/a}"]
    assert retarget_input(main, "chapters/a.tex", "chapters/z.tex").splitlines()[1] == "\\include{chapters/z}"
    assert retarget_input(main, "b.tex", "c.tex").splitlines()[2] == "\\input{c}"


# Same case as sections.test.ts: only \input lines inside the body, before the first end marker, are sections.
PRE = ("\\documentclass{article}\n\\input{macros}\n\\bibliographystyle{plain}\n\\begin{document}\n\\input{sections/a}\n"
       "\\input{sections/b}\n\\appendix\n\\input{sections/app}\n\\bibliography{x}\n\\end{document}\n")


def test_only_body_inputs_are_sections():
    assert [x.target for x in input_lines(PRE)] == ["sections/a.tex", "sections/b.tex"]
    moved = move_input(PRE, "sections/b.tex", to=0).splitlines()
    assert moved[1] == "\\input{macros}" and moved[4:8] == ["\\input{sections/b}", "\\input{sections/a}", "\\appendix", "\\input{sections/app}"]
    for op in (lambda: move_input(PRE, "macros.tex", to=0), lambda: drop_input(PRE, "sections/app.tex")):
        with pytest.raises(InvalidInput, match="not_a_section"):
            op()
    assert insert_input(PRE, "sections/c.tex", None).splitlines()[6] == "\\input{sections/c}"
    bare = "\\documentclass{x}\n\\bibliographystyle{plain}\n\\begin{document}\nHi\n\\bibliography{x}\n\\end{document}\n"
    assert insert_input(bare, "sections/c.tex", None).splitlines()[4] == "\\input{sections/c}"
    _, files = split(bare.replace("Hi\n", "\\section{One}\nA.\n"))
    assert list(files) == ["sections/one.tex"]
    assert [x.target for x in input_lines("\\input{a}\n\\bibliography{x}\n\\input{b}\n")] == ["a.tex", "b.tex"]  # no \begin{document}: all


def test_a_title_ending_in_a_lone_backslash_is_refused():
    for bad in ["Results\\", "a\\\\\\"]:
        with pytest.raises(InvalidInput, match="bad_title"):
            check_title(bad)
    assert check_title("a\\\\") == "a\\\\"


def test_section_with_a_short_title():
    _, files = split("\\begin{document}\n\\section[Short]{Long title}\nA.\n\\end{document}\n")
    assert files == {"sections/long-title.tex": "\\section[Short]{Long title}\nA.\n"}
    assert set_title("\\section[S]{Old}\nT\n", "New") == "\\section[S]{New}\nT\n"
