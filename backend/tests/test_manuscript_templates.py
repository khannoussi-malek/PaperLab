import os
import re
from pathlib import Path

import pymupdf
import pytest

from app.config import settings
from app.core import latex_compile as lc
from app.core import manuscript_templates as mt
from app.core.errors import InvalidInput

NAMES = sorted(mt.TEMPLATES)
SLUGS = ["introduction", "related-work", "method", "results", "discussion", "conclusion"]


def joined(name):
    return "\n".join(mt.files(name).values())
BIB = (
    "@article{smith2021deep, author={Smith, Jane}, title={Deep Learning for Papers},"
    " journal={Journal of Examples}, year={2021}}\n"
    "@inproceedings{lee2020graph, author={Lee, Kim}, title={Graph Methods},"
    " booktitle={Proc. of Testing}, year={2020}}\n"
)


def test_labels():
    assert mt.TEMPLATES == {
        "article": "Plain article",
        "ieee": "IEEE conference",
        "acm": "ACM (sigconf)",
        "lncs": "Springer LNCS",
        "elsevier": "Elsevier",
    }


@pytest.mark.parametrize("name", NAMES)
def test_every_template_is_split_into_sections(name):
    files = mt.files(name)
    assert sorted(files) == ["main.tex"] + sorted(f"sections/{s}.tex" for s in SLUGS)
    inputs = re.findall(r"^\\input\{(sections/[a-z-]+)\}$", files["main.tex"], re.M)
    assert inputs == [f"sections/{s}" for s in SLUGS]
    for s in SLUGS:
        assert files[f"sections/{s}.tex"].lstrip().startswith("\\section{")
    assert "\\section{" not in files["main.tex"]


@pytest.mark.parametrize("name", NAMES)
def test_every_template_is_engine_neutral(name):
    tex = joined(name)
    assert not [w for w in ("fontspec", "\\setmainfont", "luacode") if w in tex]
    assert tex.startswith("% PaperLab: ")


@pytest.mark.parametrize("name", NAMES)
def test_every_template_cites_paperlab_bib(name):
    tex = joined(name)
    assert "\\bibliography{paperlab}" in tex and "\\bibliographystyle{" in tex
    assert "\\cite" in tex and "\\fbox" in tex


@pytest.mark.parametrize("name", NAMES)
def test_every_template_has_imrad_sections(name):
    tex = joined(name)
    for sec in ("Introduction", "Related work", "Method", "Results", "Discussion", "Conclusion"):
        assert "\\section{%s}" % sec in tex


def test_unknown_template():
    with pytest.raises(InvalidInput, match="unknown_template"):
        mt.files("nope")


@pytest.mark.tectonic
@pytest.mark.skipif(not os.environ.get("TECTONIC_BIN"), reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)")
@pytest.mark.anyio
@pytest.mark.parametrize("name", NAMES)
async def test_every_template_compiles(name, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))
    for fname, body in {**mt.files(name), "paperlab.bib": BIB}.items():
        (tmp_path / fname).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / fname).write_text(body)
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert res.ok, res.log[-2000:]
    text = "".join(p.get_text() for p in pymupdf.open(stream=res.pdf, filetype="pdf"))
    assert "deep learning for papers" in text.lower()


WARM = mt.DIR / "warm-packages.tex"


def test_the_warm_package_list_is_not_a_template():
    assert WARM.exists() and "warm-packages" not in mt.TEMPLATES
    with pytest.raises(InvalidInput, match="unknown_template"):
        mt.files("warm-packages")


@pytest.mark.tectonic
@pytest.mark.skipif(not os.environ.get("TECTONIC_BIN"), reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)")
@pytest.mark.anyio
async def test_the_warm_package_list_compiles_from_the_cache_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))
    (tmp_path / "main.tex").write_text(WARM.read_text())
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert res.ok, res.log[-2000:]


LOG_AXIS_PAPER = r"""\documentclass{article}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\begin{document}
\begin{figure}[t]
\centering
\begin{tikzpicture}
\begin{axis}[ybar, symbolic x coords={a,b}, xtick=data, width=\linewidth, ymode=log, ymin=1e1, ymax=1e2]
\addplot table[col sep=comma, row sep=\\, x=x, y=y] {
x,y\\
a,88.5\\
b,90.9\\
};
\end{axis}
\end{tikzpicture}
\caption{Narrow log range}
\end{figure}
${\scriptstyle a_1 + \alpha^2} + {\scriptscriptstyle b_2 + \beta^3} + x^{2^{2}}$
\end{document}
"""


@pytest.mark.tectonic
@pytest.mark.skipif(not os.environ.get("TECTONIC_BIN"), reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)")
@pytest.mark.anyio
async def test_a_log_axis_figure_and_script_size_maths_compile_from_the_cache_alone(tmp_path, monkeypatch):
    # Tick labels like 10^2 and script-size maths use cmr5/cmr7/cmmi5/cmmi7: warm-packages.tex must have fetched them.
    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))
    (tmp_path / "main.tex").write_text(LOG_AXIS_PAPER)
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert res.ok, res.log[-2000:]
    assert res.pdf.startswith(b"%PDF")
