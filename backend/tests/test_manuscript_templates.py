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


# Exactly what slice C inserts (toBooktabs / toPgfplots / the picture path in ChartDialog) for a small example.
RESULTS_PACKAGES = ["booktabs", "pgfplots", "graphicx"]
RESULTS_BLOCKS = r"""
\begin{table}[t]
\centering
\begin{tabular}{lrr}
\toprule
System & F1 & Acc \\
\midrule
BERT-B & $88.5 \pm 0.3$ & $0.90 \pm 0.02$ \\
BERT-L & \textbf{$90.9 \pm 0.1$} & \textbf{$0.93 \pm 0.01$} \\
\bottomrule
\end{tabular}
\caption{Scores \citep{smith2021deep}}
\label{tab:scores}
\end{table}

\begin{figure}[t]
  \centering
  \begin{tikzpicture}
  \begin{axis}[
    ybar,
    width=\linewidth,
    xlabel={System},
    ylabel={F1},
    symbolic x coords={BERT-B,BERT-L},
    xtick=data,
    legend pos=outer north east,
  ]
    \addplot[error bars/.cd, y dir=both, y explicit] table[col sep=comma, row sep=\\, x=x, y=y, y error=err] {
    x,y,err\\
    BERT-B,88.5,0.3\\
    BERT-L,90.9,0\\
    };
    \addlegendentry{F1}
    \addplot table[col sep=comma, row sep=\\, x=x, y=y] {
    x,y\\
    BERT-B,0.4\\
    BERT-L,0.2\\
    };
    \addlegendentry{Std}
  \end{axis}
  \end{tikzpicture}
  \caption{F1 by system}
  \label{fig:f1}
\end{figure}

\begin{figure}[t]
  \centering
  \begin{tikzpicture}
  \begin{axis}[
    width=\linewidth,
    xlabel={Std},
    ylabel={F1},
    xmode=log,
    xmin=1e-1,
    xmax=1e0,
    ymode=log,
    ymin=1e1,
    ymax=1e2,
  ]
    \addplot table[col sep=comma, row sep=\\, x=x, y=y] {
    x,y\\
    0.4,88.5\\
    0.2,90.9\\
    };
  \end{axis}
  \end{tikzpicture}
  \caption{Log}
  \label{fig:log}
\end{figure}

\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/results-chart}
\caption{Results chart}
\label{fig:results-chart}
\end{figure}
"""


def with_results(main: str) -> str:
    """main.tex with the preamble lines slice C adds (only the missing ones) just before \\begin{document}."""
    at = main.index("\\begin{document}")
    have = {p.strip() for m in re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", main[:at]) for p in m.split(",")}
    lines = [
        line
        for p in RESULTS_PACKAGES
        if p not in have
        for line in [f"\\usepackage{{{p}}}"] + (["\\pgfplotsset{compat=1.18}"] if p == "pgfplots" else [])
    ]
    return main[:at] + "".join(f"{line}\n" for line in lines) + main[at:]


@pytest.mark.tectonic
@pytest.mark.skipif(not os.environ.get("TECTONIC_BIN"), reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)")
@pytest.mark.anyio
@pytest.mark.parametrize("name", NAMES)
async def test_every_template_compiles_inserted_tables_and_charts_from_the_cache_alone(name, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))
    files = {**mt.files(name), "paperlab.bib": BIB}
    files["main.tex"] = with_results(files["main.tex"])
    files["sections/results.tex"] += RESULTS_BLOCKS
    for fname, body in files.items():
        (tmp_path / fname).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / fname).write_text(body)
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures/results-chart.png").write_bytes((mt.DIR / "warm-figure.png").read_bytes())
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert res.ok, res.log[-2000:]
    assert res.pdf.startswith(b"%PDF")
