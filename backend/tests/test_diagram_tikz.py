import re
from pathlib import Path

import pytest

from app.core import diagram_tikz as dt

ROOT = Path(__file__).resolve().parents[2]
PIC = "\\begin{tikzpicture}\n\\node {A};\n\\end{tikzpicture}"


def test_split_code_lifts_and_dedupes_libraries():
    code = "\\usetikzlibrary{fit, calc}\n" + PIC + "\n\\usetikzlibrary{calc,chains}\n"
    libs, rest = dt.split_code(code)
    assert libs == ["fit", "calc", "chains"]
    assert rest == PIC


def test_a_plain_picture_is_insertable():
    assert dt.check(["fit"], "% note\n" + PIC + "\n% done\n") == []


@pytest.mark.parametrize(
    "picture",
    [
        PIC + "\n" + PIC,
        "Hello\n" + PIC,
        "\\begin{scope}x\\end{scope}" + PIC,
        PIC + "\nmore text",
        "\\node {A};",
        PIC.replace("\\end", "% x\n\\end{tikzpicture}\\end"),
    ],
)
def test_structure_is_one_picture_and_nothing_else(picture):
    assert dt.check([], picture)


DENIED = [
    "usepackage{x}",
    "documentclass{x}",
    "input{x}",
    "include{x}",
    "write18{x}",
    "openout3=x",
    "openin3=x",
    "read3 to \\x",
    "immediate",
    "catcode`\\a=11",
    "directlua{}",
    "caption{x}",
    "label{x}",
    "ref{x}",
    "includegraphics{x}",
    "csname input\\endcsname",
    "readline3 to \\x",
    "scantokens{x}",
    "InputIfFileExists{x}{}{}",
    "lstinputlisting{x}",
    "verbatiminput{x}",
    "special{x}",
    "endinput",
]


@pytest.mark.parametrize("cmd", DENIED)
@pytest.mark.parametrize("form", ["\\{}", "\\ {}", "\\\t{}", "\\\n{}"])
def test_each_denied_command_is_rejected_in_any_spacing(cmd, form):
    body = PIC.replace("\\node {A};", form.format(cmd) + " \\node {A};")
    assert dt.check([], body), body


def test_input_forms_and_escapes_are_rejected():
    for bad in ["\\input{x}", "\\input x", "\\ input{x}", "\\^^69nput{x}", "\\input\n{x}"]:
        assert dt.check([], PIC.replace("{A}", "{A} " + bad)), bad


def test_a_denied_command_in_a_comment_is_rejected_too():
    assert dt.check([], PIC.replace("\\node", "% \\input{x}\n\\node"))


def test_a_longer_command_name_is_not_a_false_positive():
    assert dt.check([], PIC.replace("{A}", "{A \\referee}")) == []


def test_library_outside_the_allowlist_is_named():
    errs = dt.check(["external"], PIC)
    assert errs == ["The diagram uses the TikZ library external, which PaperLab doesn't include offline."]


def test_oversize_is_rejected():
    assert dt.check([], PIC.replace("{A}", "{" + "a" * 20_000 + "}"))


def test_node_labels_flatten_nested_braces_and_line_breaks():
    pic = "\\node[draw, label={[x]above:no}] (a) at (0,0) {Encoder \\\\ {\\textbf{block}} 2};\n\\node {Out};"
    assert dt.node_labels(pic) == ["Encoder block 2", "Out"]


def test_labels_not_in_description_flags_a_cache():
    pic = "\\node {Encoder}; \\node {Cache}; \\node {A 2}; \\node {Decoders};"
    assert dt.labels_not_in_description(pic, "an encoder and decoder") == ["Cache"]


def test_the_allowlist_equals_the_warm_file_and_the_dockerfile_uses_it():
    warm = (ROOT / "backend/app/manuscript_templates/warm-diagram.tex").read_text()
    libs = [x.strip() for m in re.findall(r"^\\usetikzlibrary\{([^}]*)\}", warm, re.M) for x in m.split(",")]
    assert sorted(libs) == sorted(dt.ALLOWED_LIBRARIES) and len(libs) == len(set(libs))
    assert "/templates/warm-diagram.tex" in (ROOT / "Dockerfile").read_text()


def test_standalone_document_wraps_the_picture():
    doc = dt.standalone_document(["fit", "calc"], PIC)
    assert doc.startswith(dt.PREAMBLE + "\\usetikzlibrary{fit,calc}\n")
    assert dt.PREAMBLE in (ROOT / "backend/app/manuscript_templates/warm-diagram.tex").read_text()
    assert PIC in doc
