import io
import zipfile

import pytest

from app.core import manuscript_paths as paths
from app.core import manuscript_zip
from app.core.errors import Conflict, InvalidInput

TEX = "\\documentclass{article}\\begin{document}Hi\\end{document}"


def make_zip(members: dict[str, str | bytes], patch=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
        if patch:
            patch(z.filelist)
    return buf.getvalue()


def test_lying_header_is_a_bad_zip_naming_the_member():
    def lie(infos):
        infos[0].file_size = 10  # the header says 10 bytes; the stream holds more

    data = make_zip({"main.tex": TEX + "x" * (paths.MAX_TEXT + 5)}, lie)
    with pytest.raises(InvalidInput, match="bad_zip") as exc:
        manuscript_zip.read_zip(data)
    assert exc.value.details["path"] == "main.tex"


def test_honest_member_over_the_text_cap_is_file_too_large():
    with pytest.raises(Conflict, match="file_too_large") as exc:
        manuscript_zip.read_zip(make_zip({"main.tex": TEX + "x" * paths.MAX_TEXT}))
    assert exc.value.details["path"] == "main.tex" and exc.value.details["limit"] == paths.MAX_TEXT


def test_total_size_checked_before_reading():
    def lie(infos):
        for info in infos:
            info.file_size = paths.MAX_TOTAL // 2 + 1

    data = make_zip({"main.tex": TEX, "b.tex": "b"}, lie)
    with pytest.raises(Conflict, match="manuscript_too_large"):
        manuscript_zip.read_zip(data)


def test_dot_dot_paths_refused():
    for name in ("../evil.tex", "/abs.tex", "a\\b.tex"):
        with pytest.raises(InvalidInput, match="bad_path") as exc:
            manuscript_zip.read_zip(make_zip({"main.tex": TEX, name: "x"}))
        assert exc.value.details["path"] == name


def test_too_many_files():
    members = {f"f{i}.txt": "" for i in range(paths.MAX_FILES + 1)}
    with pytest.raises(Conflict, match="too_many_files"):
        manuscript_zip.read_zip(make_zip(members))


def test_macosx_and_dotfiles_skipped():
    files, _, _ = manuscript_zip.read_zip(make_zip({"main.tex": TEX, "__MACOSX/._main.tex": "x", ".DS_Store": "x",
                                                 "sub/.hidden.tex": "x"}))
    assert list(files) == ["main.tex"]


def test_paperlab_bib_renamed():
    files, _, _ = manuscript_zip.read_zip(make_zip({"main.tex": TEX, "paperlab.bib": "@a{b}"}))
    assert files["paperlab-imported.bib"] == "@a{b}" and "paperlab.bib" not in files


def test_main_file_detection():
    assert manuscript_zip.read_zip(make_zip({"main.tex": TEX, "other.tex": TEX}))[1] == "main.tex"
    assert manuscript_zip.read_zip(make_zip({"paper.tex": TEX, "ch.tex": "no class"}))[1] == "paper.tex"
    with pytest.raises(InvalidInput, match="no_main_file"):
        manuscript_zip.read_zip(make_zip({"a.tex": TEX, "b.tex": TEX}))
    with pytest.raises(InvalidInput, match="no_main_file"):
        manuscript_zip.read_zip(make_zip({"a.tex": "nothing"}))


def test_non_utf8_text_refused():
    with pytest.raises(InvalidInput, match="not_text") as exc:
        manuscript_zip.read_zip(make_zip({"main.tex": TEX, "x.tex": b"\xff\xfe\x00"}))
    assert exc.value.details["path"] == "x.tex"


def test_round_trip_keeps_every_file_and_adds_bib_and_latexmkrc():
    files = {"main.tex": TEX, "img/a.png": b"\x89PNG", "refs.bib": "@x{y}"}
    out = manuscript_zip.write_zip(files, "@bib{k}", b"%PDF", "My Paper")
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        names = set(z.namelist())
        assert names == {*files, "paperlab.bib", "latexmkrc", "My_Paper.pdf"}
        assert b"$pdf_mode = 5;" in z.read("latexmkrc")
    back, main, _ = manuscript_zip.read_zip(out)
    assert main == "main.tex" and back["main.tex"] == TEX and back["img/a.png"] == b"\x89PNG"
    assert back["paperlab-imported.bib"] == "@bib{k}"
    own = manuscript_zip.write_zip({**files, "latexmkrc": "mine"}, "", None, "T")
    with zipfile.ZipFile(io.BytesIO(own)) as z:
        assert z.read("latexmkrc") == b"mine" and "T.pdf" not in z.namelist()


def test_not_a_zip():
    with pytest.raises(InvalidInput, match="bad_zip"):
        manuscript_zip.read_zip(b"this is not a zip")


def test_unsupported_types_are_skipped_and_listed():
    files, main, skipped = manuscript_zip.read_zip(
        make_zip({"main.tex": TEX, "README": "x", "fig.eps": b"x", "img/logo.svg": b"<svg/>", "a.png": b"p"}))
    assert sorted(files) == ["a.png", "main.tex"] and main == "main.tex"
    assert sorted(skipped) == ["README", "fig.eps", "img/logo.svg"]


def test_symlink_members_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("main.tex", TEX)
        link = zipfile.ZipInfo("link.tex")
        link.external_attr = 0o120777 << 16
        z.writestr(link, "/etc/passwd")
    with pytest.raises(InvalidInput, match="bad_zip") as exc:
        manuscript_zip.read_zip(buf.getvalue())
    assert exc.value.details["path"] == "link.tex"


def test_duplicate_and_case_folding_duplicate_members_refused():
    import warnings
    for names in (["Fig.png", "fig.png"], ["a.png", "a.png"]):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z, warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z.writestr("main.tex", TEX)
            for name in names:
                z.writestr(name, b"p")
        with pytest.raises(InvalidInput, match="bad_zip") as exc:
            manuscript_zip.read_zip(buf.getvalue())
        assert exc.value.details["path"] == names[1]


def test_reserved_bib_variants_refused_with_the_path():
    for name in ("sub/paperlab.bib", "Paperlab.bib"):
        with pytest.raises(InvalidInput, match="reserved_path") as exc:
            manuscript_zip.read_zip(make_zip({"main.tex": TEX, name: "x"}))
        assert exc.value.details["path"] == name


def test_a_single_wrapper_folder_is_dropped():
    # Overleaf's own download, and most zips made of a folder, put everything under "<project>/".
    data = make_zip({"My Paper/main.tex": TEX, "My Paper/sections/intro.tex": "Hi", "My Paper/paperlab.bib": "@x{y}",
                     "__MACOSX/My Paper/._main.tex": b"junk", "My Paper/notes.svg": "<svg/>"})
    files, main, skipped = manuscript_zip.read_zip(data)
    assert set(files) == {"main.tex", "sections/intro.tex", manuscript_zip.IMPORTED_BIB}
    assert main == "main.tex" and skipped == ["notes.svg"]


def test_folders_that_differ_are_kept():
    files, main, _ = manuscript_zip.read_zip(make_zip({"paper/main.tex": TEX, "figs/a.png": b"\x89PNG"}))
    assert set(files) == {"paper/main.tex", "figs/a.png"} and main == "paper/main.tex"
