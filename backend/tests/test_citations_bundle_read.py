"""M40 Task 8: read a Zotero "export with files" zip safely. No database."""

import io
import zipfile

import pytest

from app.core import citations_bundle_read as cbr
from app.core.citations_bundle_read import read_bundle
from app.core.citations_import import CitationsImportError

PDF = b"%PDF-1.7 body"
BIB = (
    "@article{a, title={Alpha}, author={Smith, Jane}, year={2020}, file={files/12/Alpha.pdf}}\n"
    "@article{b, title={Beta}, author={Doe, Jo}, year={2021}, file={Beta:files/13/Beta.PDF:application/pdf}}\n"
    "@article{c, title={Gamma}, year={2022}, file={files/14/missing.pdf}}\n"
    "@article{d, title={Delta}, year={2023}}\n"
)
BBT = "@article{a, title={Alpha}, year={2020}, file={:files/12/Alpha.pdf:application/pdf;desc:files\\\\12\\\\x.pdf}}\n"


def make(members: dict, symlink: set = frozenset()) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, body in members.items():
            info = zipfile.ZipInfo(name)
            if name in symlink:
                info.external_attr = (0o120777) << 16
            zf.writestr(info, body)
    return out.getvalue()


def test_zotero_export_with_files():
    data = make({"My Library.bib": BIB, "files/12/Alpha.pdf": PDF, "files/13/Beta.PDF": PDF + b"2",
                 "files/14/notpdf.pdf": b"nope"})  # fmt: skip
    with read_bundle(data) as b:
        a, bt, c, d = b.entries
        assert {e.collection for e in b.entries} == {"My Library"}
        assert b.pdf_for(a) == PDF
        assert b.pdf_for(bt) == PDF + b"2"  # case-insensitive fallback + Title:path:mime form
        assert b.pdf_for(c) is None and b.pdf_for(d) is None
        assert any("Gamma" in w for w in b.warnings) and not any("Delta" in w for w in b.warnings)


def test_better_bibtex_and_stream_input():
    data = make({"Exported Items.bib": BBT, "files/12/Alpha.pdf": PDF})
    with read_bundle(io.BytesIO(data)) as b:
        assert b.pdf_for(b.entries[0]) == PDF


def test_non_pdf_bytes_warn_not_crash():
    data = make({"x.bib": BIB, "files/12/Alpha.pdf": b"<html>"})
    with read_bundle(data) as b:
        assert b.pdf_for(b.entries[0]) is None
        assert any("isn't a PDF" in w for w in b.warnings)


@pytest.mark.parametrize("name", ["../../etc/passwd", "/etc/passwd", "files/../../x.pdf", "C:/win.pdf", "a\\..\\b"])
def test_rejects_escaping_paths(name):
    with pytest.raises(CitationsImportError, match="safely"):
        read_bundle(make({"x.bib": BIB, name: PDF}))


def test_rejects_symlink_member():
    with pytest.raises(CitationsImportError, match="safely"):
        read_bundle(make({"x.bib": BIB, "files/12/Alpha.pdf": "/etc/passwd"}, symlink={"files/12/Alpha.pdf"}))


def test_rejects_declared_size_bomb(monkeypatch):
    monkeypatch.setattr(cbr, "MAX_ZIP_BYTES", 1000)
    with pytest.raises(CitationsImportError, match="200 MB"):
        read_bundle(make({"x.bib": BIB, "files/12/Alpha.pdf": PDF + b"0" * 2000}))


def test_rejects_too_many_members(monkeypatch):
    monkeypatch.setattr(cbr, "MAX_MEMBERS", 3)
    with pytest.raises(CitationsImportError, match="more files"):
        read_bundle(make({"x.bib": BIB, "a.pdf": PDF, "b.pdf": PDF, "c.pdf": PDF}))


def test_reads_are_capped_at_the_declared_size():
    data = make({"x.bib": BIB, "files/12/Alpha.pdf": PDF})
    with read_bundle(data) as b:
        info = next(i for i in b._zf.infolist() if i.filename.endswith("Alpha.pdf"))
        with pytest.raises(CitationsImportError, match="than it says"):
            cbr._read(b._zf, info, 3)


@pytest.mark.parametrize(
    "members, match",
    [({"files/a.pdf": PDF}, "no .bib"), ({"a.bib": BIB, "b.ris": "TY  - JOUR\nER  - \n"}, "more than one")],
)
def test_refs_file_must_be_exactly_one(members, match):
    with pytest.raises(CitationsImportError, match=match):
        read_bundle(make(members))


def test_not_a_zip_and_bad_refs():
    with pytest.raises(CitationsImportError, match="isn't a zip"):
        read_bundle(b"hello")
    with pytest.raises(CitationsImportError):
        read_bundle(make({"x.bib": "garbage"}))
