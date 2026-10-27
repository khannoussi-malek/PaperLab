import pytest

from app.core.errors import InvalidInput
from app.core.manuscript_paths import is_text, validate_path


@pytest.mark.parametrize(
    ("path", "code"),
    [("../a.tex", "bad_path"), ("/a.tex", "bad_path"), ("a\\b.tex", "bad_path"), ("a b.tex", "bad_path"),
     ("a/b/c/d/e.tex", "bad_path"), ("", "bad_path"), ("paperlab.bib", "reserved_path"),
     ("PaperLab.BIB", "reserved_path"),
     ("sub/paperlab.bib", "reserved_path"),
     ("fig.svg", "unsupported_file_type")],
)
def test_rejected_paths(path, code):
    with pytest.raises(InvalidInput, match=code):
        validate_path(path)


def test_accepted_paths():
    for path in ("figures/plot.pdf", "sections/intro.tex", "latexmkrc"):
        assert validate_path(path) == path
    assert is_text("latexmkrc") and is_text("a/b.bib") and not is_text("figures/plot.pdf")


@pytest.mark.parametrize("name", ["a.clo", "b.def", "c.cfg", "style.bbx", "style.cbx", "fig.tikz", "plot.pgf"])
def test_tex_support_files_are_text(name):
    assert validate_path(name) == name and is_text(name)
