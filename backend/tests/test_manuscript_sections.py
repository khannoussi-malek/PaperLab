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
    assert moved[1:4] == ["\\input{sections/method}", "\\clearpage", "\\input{sections/intro}"]
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
