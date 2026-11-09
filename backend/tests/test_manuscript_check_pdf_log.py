import os
from pathlib import Path

import pytest

from app.core.manuscript_checks import pdf_log
from app.core.manuscript_checks.pdf_log import Box

FIX = Path(__file__).parent / "fixtures" / "tectonic"

LOG = """(main.tex
LaTeX2e <2021-11-15> patch level 1
(article.cls
Document Class: article 2021/10/04 v1.4n Standard LaTeX document class
)
(sections/method.tex
Overfull \\hbox (12.3pt too wide) in paragraph at lines 40--42
[]\\OT1/cmr/m/n/10 A very long line (with parens) []

Underfull \\hbox (badness 10000) in paragraph at lines 7--8
[]\\OT1/cmr/m/n/10 short

)
Overfull \\hbox (3.0pt too wide) in alignment at lines 5--9
[]\\OT1/cmr/m/n/10 x)

Underfull \\hbox (badness 2500) detected at line 12
)
"""


def test_boxes_with_files_and_ranges():
    assert pdf_log.boxes(LOG) == [
        Box("overfull", 12.3, 40, 42, "sections/method.tex"),
        Box("underfull", 10000.0, 7, 8, "sections/method.tex"),
        Box("overfull", 3.0, 5, 9, "main.tex"),
        Box("underfull", 2500.0, 12, 12, "main.tex"),
    ]


def test_leading_dot_slash_is_stripped():
    log = "(./main.tex\n(./sections/a.tex\nOverfull \\hbox (9.0pt too wide) in paragraph at lines 3--3\n[]x\n\n)\n)\n"
    assert pdf_log.boxes(log) == [Box("overfull", 9.0, 3, 3, "sections/a.tex")]


def test_a_path_wrapped_at_79_columns_is_joined():
    first = "(./sections/" + "x" * (79 - len("(./sections/"))
    assert len(first) == 79
    log = f"(main.tex\n{first}\n.tex\nOverfull \\hbox (9.0pt too wide) in paragraph at lines 3--3\n[]x\n\n)\n)\n"
    assert pdf_log.boxes(log)[0].file == "sections/" + "x" * (79 - len("(./sections/")) + ".tex"


def test_package_file_gives_no_file():
    log = "(main.tex (somepkg.sty\nOverfull \\hbox (9.0pt too wide) in paragraph at lines 1--1\n\n)\n)\n"
    assert pdf_log.boxes(log) == [Box("overfull", 9.0, 1, 1, None)]


def test_stderr_lines_never_move_the_file_stack():
    stderr = "note: Writing `main.pdf` (1 KiB)\nwarning: odd ( paren in a message\nnote: ) stray\n"
    log = "(main.tex\n(sections/a.tex\nOverfull \\hbox (9.0pt too wide) in paragraph at lines 3--3\n[]x\n\n)\n)\n"
    assert pdf_log.boxes(stderr + log) == [Box("overfull", 9.0, 3, 3, "sections/a.tex")]


def test_stderr_and_log_copies_are_one_box():
    stderr = "warning: sections/method.tex:40: Overfull \\hbox (12.3pt too wide) in paragraph at lines 40--42\n"
    log = "(main.tex\n(sections/method.tex\nOverfull \\hbox (12.3pt too wide) in paragraph at lines 40--42\n[]x\n\n)\n)\n"
    assert pdf_log.boxes(stderr + log) == [Box("overfull", 12.3, 40, 42, "sections/method.tex")]


def test_same_size_and_lines_in_two_files_stay_two():
    head = "Overfull \\hbox (7.0pt too wide) in paragraph at lines 3--3\n[]x\n\n"
    log = f"(main.tex\n(sections/a.tex\n{head})\n(sections/b.tex\n{head})\n)\n"
    assert [b.file for b in pdf_log.boxes(log)] == ["sections/a.tex", "sections/b.tex"]


def test_no_boxes():
    assert pdf_log.boxes("(main.tex\nAll good.\n)\n") == []
    assert pdf_log.boxes("") == []


def test_real_captured_wrapped_path_is_attributed():
    """The one real wrapped-path case: Task 5 Step 0 captured a log where the long section file's open line wraps."""
    log = (FIX / "overfull.main.log").read_text()
    assert any(len(line) == 79 for line in log.splitlines()), "the fixture must contain a wrapped line"
    both = (FIX / "overfull.stderr.txt").read_text() + "\n" + log
    long_name = "sections/" + "longname" * 9 + ".tex"
    assert any(b.file == long_name for b in pdf_log.boxes(both))


def test_real_captured_log_parses():
    both = (FIX / "overfull.stderr.txt").read_text() + "\n" + (FIX / "overfull.main.log").read_text()
    found = pdf_log.boxes(both)
    overfull = [b for b in found if b.kind == "overfull"]
    assert overfull and overfull[0].amount > 0
    assert overfull[0].file == "sections/a.tex"


@pytest.mark.tectonic
@pytest.mark.anyio
@pytest.mark.skipif(not os.environ.get("TECTONIC_BIN"), reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)")
async def test_live_compile_boxes_get_a_file(tmp_path, monkeypatch):
    from app.config import settings
    from app.core import latex_compile as lc

    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))
    (tmp_path / "sections").mkdir()
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\input{sections/a}\n\\end{document}\n")
    # The blank line closes the paragraph inside a.tex; without it TeX reports the box against main.tex.
    (tmp_path / "sections/a.tex").write_text("\\section{A}\nSee " + "x" * 120 + " here.\n\n")
    result = await lc.compile_dir(tmp_path, "main.tex")
    boxes = pdf_log.boxes(result.log)
    assert any(b.kind == "overfull" and b.file == "sections/a.tex" for b in boxes)
