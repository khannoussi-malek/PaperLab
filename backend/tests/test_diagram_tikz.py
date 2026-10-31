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
    assert dt.node_labels(pic) == ["Encoder block 2", "Out", "no"]  # label= text counts too (final review I1)


def test_labels_not_in_description_flags_a_cache():
    pic = "\\node {Encoder}; \\node {Cache}; \\node {A 2}; \\node {Decoders};"
    assert dt.labels_not_in_description(pic, "an encoder and decoder") == ["Cache"]


def test_the_allowlist_equals_the_warm_file_and_the_dockerfile_uses_it():
    warm = (ROOT / "backend/app/manuscript_templates/warm-diagram.tex").read_text()
    libs = [x.strip() for m in re.findall(r"^\\usetikzlibrary\{([^}]*)\}", warm, re.M) for x in m.split(",")]
    assert sorted(libs) == sorted(dt.ALLOWED_LIBRARIES) and len(libs) == len(set(libs))
    assert "/templates/warm-diagram.tex" in (ROOT / "Dockerfile").read_text()


def test_preview_document_wraps_the_picture():
    doc = dt.preview_document(["fit", "calc"], PIC)
    assert doc.startswith(dt.PREAMBLE + "\\usetikzlibrary{fit,calc}\n")
    assert dt.PREAMBLE in (ROOT / "backend/app/manuscript_templates/warm-diagram.tex").read_text()
    assert PIC in doc


@pytest.mark.parametrize(
    "picture",
    [
        "% \\begin{tikzpicture}\nInjected prose. \\tikz \\node{A};\n% \\end{tikzpicture}",  # review 5 C1
        "% \\begin{tikzpicture}\nInjected prose.\n\\begin{tikz%\npicture}\\node {A};\\end{tikzpicture}",
        PIC + "\nprose %\n",
    ],
)
def test_comments_are_stripped_the_way_tex_does_before_the_structure_is_judged(picture):
    assert dt.check([], picture)


@pytest.mark.parametrize(
    "body",
    [
        "\\makeatletter\\@@input{../secret}",  # review 5 I1
        "\\ExplSyntaxOn\\file_get:nnN{x}{}\\l_tmpa_tl",
        "\\ExplSyntaxOn\\iow_open:Nn \\g_tmpa_iow {/tmp/x}",
        "\\filedump{x}",
        "\\pgfimage{x}",
        "\\XeTeXpdffile x",
        "\\UseName{input}{x}",
        "\\inp%\nut{x}",  # a comment joins the name back together
        "\\usetikzlibrary[external]",  # minor 1: the allowlist is the only door
        "\\usepgflibrary{x}",
        "\\RequirePackage{x}",
        "\\gdef\\thepage{HACKED}",  # minor 2: no global side effects
        "\\global\\let\\x\\relax",
        "\\AtEndDocument{x}",
        "\\AddToHook{x}{y}",
    ],
)
def test_aliases_of_denied_commands_are_rejected(body):
    assert dt.check([], PIC.replace("\\node {A};", body + " \\node {A};"))


def test_the_warm_files_own_picture_passes_the_guard():
    warm = (ROOT / "backend/app/manuscript_templates/warm-diagram.tex").read_text()
    picture = warm[warm.index("\\begin{tikzpicture}") : warm.index("\\end{document}")].strip()
    assert dt.check(list(dt.ALLOWED_LIBRARIES), picture) == []


def test_plurals_and_non_ascii_labels_match_the_description():
    pic = "\\begin{tikzpicture}\\node {Processes}; \\node {Boxes}; \\node {Ölmodell};\\end{tikzpicture}"
    assert dt.labels_not_in_description(pic, "a process, a box and the Ölmodell") == []


def test_a_line_break_before_a_word_in_a_label_is_not_a_command():  # re-review 1 F1
    pic = "\\begin{tikzpicture}\\node {Token\\\\Input}; \\node {Raw\\\\Image};\\end{tikzpicture}"
    assert dt.check([], pic) == []
    assert dt.check([], pic.replace("Raw\\\\Image", "Raw\\\\ \\input{x}"))


def test_labels_on_paths_edges_and_label_pin_options_are_read():  # final review I1
    pic = (
        "\\begin{tikzpicture}[node distance=8mm, every node/.style={draw}]\n"
        "\\node (a) {Encoder};\n"
        "\\node[right=of a, label=above:{Hidden prose}, pin={[red]90:Pinned words}] (b) {Decoder};\n"
        "\\draw[->] (a) -- node[above] {model says hi} (b);\n"
        "\\path (a) edge node {edge text} (b);\n"
        "\\end{tikzpicture}"
    )
    assert dt.node_labels(pic) == ["Encoder", "Decoder", "model says hi", "edge text", "Hidden prose", "Pinned words"]
    assert dt.labels_not_in_description(pic, "An encoder feeds a decoder.") == [
        "model says hi",
        "edge text",
        "Hidden prose",
        "Pinned words",
    ]


def test_drop_comments_removes_model_comments_and_keeps_escaped_percent():
    assert (
        dt.drop_comments("% intro\n\\node {A}; % tail\n\\node {50\\% done};\n") == "\\node {A};\n\\node {50\\% done};"
    )


def test_a_word_before_a_colon_in_a_label_is_text_unless_it_is_a_position():  # final re-review minor
    pic = "\\begin{tikzpicture}\\node[label=Note: x, pin=above left:Kept] {A};\\end{tikzpicture}"
    assert dt.node_labels(pic) == ["A", "Note: x", "Kept"]
