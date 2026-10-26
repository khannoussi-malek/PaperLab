import io
import zipfile

import pytest

from app.core import manuscript_paths as paths
from app.core import manuscript_zip
from app.core.errors import InvalidInput

TEX = "\\documentclass{article}\\begin{document}Hi\\end{document}"


def make_zip(members: dict[str, str | bytes], patch=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
        if patch:
            patch(z.filelist)
    return buf.getvalue()


def test_lying_file_size_stops_at_the_cap():
    def lie(infos):
        infos[0].file_size = 10  # the header says 10 bytes; the stream holds more than the text cap

    data = make_zip({"main.tex": TEX + "x" * (paths.MAX_TEXT + 5)}, lie)
    with pytest.raises(InvalidInput):
        manuscript_zip.read_zip(data)


def test_total_size_checked_before_reading():
    def lie(infos):
        for info in infos:
            info.file_size = paths.MAX_TOTAL // 2 + 1

    data = make_zip({"main.tex": TEX, "b.tex": "b"}, lie)
    with pytest.raises(InvalidInput, match="zip_too_large"):
        manuscript_zip.read_zip(data)


def test_dot_dot_paths_refused():
    with pytest.raises(InvalidInput, match="bad_path"):
        manuscript_zip.read_zip(make_zip({"main.tex": TEX, "../evil.tex": "x"}))


def test_too_many_files():
    members = {f"f{i}.txt": "" for i in range(paths.MAX_FILES + 1)}
    with pytest.raises(InvalidInput, match="too_many_files"):
        manuscript_zip.read_zip(make_zip(members))


def test_macosx_and_dotfiles_skipped():
    files, _ = manuscript_zip.read_zip(make_zip({"main.tex": TEX, "__MACOSX/._main.tex": "x", ".DS_Store": "x",
                                                 "sub/.hidden.tex": "x"}))
    assert list(files) == ["main.tex"]


def test_paperlab_bib_renamed():
    files, _ = manuscript_zip.read_zip(make_zip({"main.tex": TEX, "paperlab.bib": "@a{b}"}))
    assert files["paperlab-imported.bib"] == "@a{b}" and "paperlab.bib" not in files


def test_main_file_detection():
    assert manuscript_zip.read_zip(make_zip({"main.tex": TEX, "other.tex": TEX}))[1] == "main.tex"
    assert manuscript_zip.read_zip(make_zip({"paper.tex": TEX, "ch.tex": "no class"}))[1] == "paper.tex"
    with pytest.raises(InvalidInput, match="no_main_file"):
        manuscript_zip.read_zip(make_zip({"a.tex": TEX, "b.tex": TEX}))
    with pytest.raises(InvalidInput, match="no_main_file"):
        manuscript_zip.read_zip(make_zip({"a.tex": "nothing"}))


def test_non_utf8_text_refused():
    with pytest.raises(InvalidInput, match="not_text"):
        manuscript_zip.read_zip(make_zip({"main.tex": TEX, "x.tex": b"\xff\xfe\x00"}))


def test_round_trip_keeps_every_file_and_adds_bib_and_latexmkrc():
    files = {"main.tex": TEX, "img/a.png": b"\x89PNG", "refs.bib": "@x{y}"}
    out = manuscript_zip.write_zip(files, "@bib{k}", b"%PDF", "My Paper")
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        names = set(z.namelist())
        assert names == {*files, "paperlab.bib", "latexmkrc", "My_Paper.pdf"}
        assert b"$pdf_mode = 5;" in z.read("latexmkrc")
    back, main = manuscript_zip.read_zip(out)
    assert main == "main.tex" and back["main.tex"] == TEX and back["img/a.png"] == b"\x89PNG"
    assert back["paperlab-imported.bib"] == "@bib{k}"
    own = manuscript_zip.write_zip({**files, "latexmkrc": "mine"}, "", None, "T")
    with zipfile.ZipFile(io.BytesIO(own)) as z:
        assert z.read("latexmkrc") == b"mine" and "T.pdf" not in z.namelist()


def test_not_a_zip():
    with pytest.raises(InvalidInput, match="bad_zip"):
        manuscript_zip.read_zip(b"this is not a zip")
