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
        assert len(b.entries) == 4
        assert {e.collection for e in b.entries} == {"My Library"}
        assert b.read_pdf(b.pdf_path(0)) == PDF
        assert b.read_pdf(b.pdf_path(1)) == PDF + b"2"  # case-insensitive fallback + Title:path:mime form
        assert b.pdf_path(2) is None and b.pdf_path(3) is None
        assert any("Gamma" in w for w in b.warnings) and not any("Delta" in w for w in b.warnings)


def test_better_bibtex_and_stream_input():
    data = make({"Exported Items.bib": BBT, "files/12/Alpha.pdf": PDF})
    with read_bundle(io.BytesIO(data)) as b:
        assert b.read_pdf(b.pdf_path(0)) == PDF


def test_non_pdf_bytes_warn_not_crash():
    data = make({"x.bib": BIB, "files/12/Alpha.pdf": b"<html>"})
    with read_bundle(data) as b:
        assert b.pdf_path(0) is None
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


def deflated(members: dict, corrupt: str | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in members.items():
            zf.writestr(name, body)
        target = zf.getinfo(corrupt) if corrupt else None
    raw = bytearray(out.getvalue())
    if target:
        start = target.header_offset + 30 + len(target.filename.encode()) + 8
        raw[start : start + 12] = b"\xff" * 12
    return bytes(raw)


def test_corrupt_deflate_is_a_plain_message():
    body = PDF + b"abcdefgh" * 500
    data = deflated({"x.bib": BIB, "files/12/Alpha.pdf": body}, corrupt="files/12/Alpha.pdf")
    with read_bundle(data) as b:
        assert b.pdf_path(0) is None and any("Alpha" in w for w in b.warnings)
    with pytest.raises(CitationsImportError, match="damaged"):
        read_bundle(deflated({"x.bib": BIB * 50}, corrupt="x.bib"))


def test_corrupt_data_after_a_good_header_is_a_plain_error_on_read():
    body = PDF + bytes(range(256)) * 200
    data = deflated({"x.bib": BIB, "files/12/Alpha.pdf": body})
    with read_bundle(data) as b:
        info = b._pdfs["files/12/Alpha.pdf"]
        raw = bytearray(data)
        pos = info.header_offset + 30 + len(info.filename) + 40
        raw[pos : pos + 8] = b"\xff" * 8
    with read_bundle(bytes(raw)) as b2:
        if b2.pdf_path(0):
            with pytest.raises(CitationsImportError):
                b2.read_pdf(b2.pdf_path(0))


def test_rejects_other_compression_methods():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_BZIP2) as zf:
        zf.writestr("x.bib", BIB)
    with pytest.raises(CitationsImportError, match="compression"):
        read_bundle(out.getvalue())


def test_finder_wrapped_export_ignores_attachments_named_like_refs():
    data = make({"Exported Items/Exported Items.bib": BIB, "Exported Items/files/12/Alpha.pdf": PDF,
                 "Exported Items/files/13/data.json": "{}"})  # fmt: skip
    with read_bundle(data) as b:
        assert b.entries[0].collection == "Exported Items"
        assert b.read_pdf(b.pdf_path(0)) == PDF


def test_two_refs_files_at_the_same_depth_are_refused():
    with pytest.raises(CitationsImportError, match="more than one"):
        read_bundle(make({"W/a.bib": BIB, "W/b.ris": "x", "files/z.json": "{}"}))


def test_shallowest_refs_file_wins():
    b = read_bundle(make({"a.bib": BIB, "deep/dir/b.bib": BIB}))
    assert b.entries[0].collection == "a"


def test_oversized_pdf_is_skipped_with_a_warning(monkeypatch):
    monkeypatch.setattr(cbr, "MAX_UPLOAD_PDF_BYTES", 5)
    with read_bundle(make({"x.bib": BIB, "files/12/Alpha.pdf": PDF})) as b:
        assert b.pdf_path(0) is None and any("limit" in w for w in b.warnings)


def test_accented_names_match_across_unicode_forms():
    nfd = "files/1/Caf\u0065\u0301.pdf"
    bib = "@article{a, title={Cafe}, year={2020}, file={files/1/Caf\u00e9.pdf}}\n"
    with read_bundle(make({"x.bib": bib, nfd: PDF})) as b:
        assert b.read_pdf(b.pdf_path(0)) == PDF


@pytest.mark.parametrize("path", ["../../etc/passwd", "../../etc/passwd.pdf", "/etc/passwd.pdf"])
def test_hostile_file_field_reads_nothing_outside_the_zip(path):
    bib = "@article{a, title={Evil}, year={2020}, file={%s}}\n" % path
    with read_bundle(make({"x.bib": bib, "files/1/a.pdf": PDF})) as b:
        assert b.pdf_path(0) is None and b.warnings


def test_html_snapshot_only_says_no_pdf_attachment():
    bib = "@article{a, title={Web}, year={2020}, file={files/1/snap.html}}\n"
    with read_bundle(make({"x.bib": bib, "files/1/snap.html": "<html>"})) as b:
        assert b.warnings == ["'Web': no PDF attachment."]


def test_read_pdf_refuses_unknown_member_and_non_pdf():
    with read_bundle(make({"x.bib": BIB, "files/12/Alpha.pdf": b"<html>"})) as b:
        with pytest.raises(CitationsImportError):
            b.read_pdf("files/12/Alpha.pdf")
        with pytest.raises(CitationsImportError):
            b.read_pdf("x.bib")
