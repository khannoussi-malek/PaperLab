"""Read a Zotero "export with files" zip (M40 Task 8, I3): the references file plus the PDFs its entries point at.
Parsing only, no database. The zip is never trusted: every member is vetted from the central directory before
anything is read, nothing is extracted by path or written to disk, and PDFs are read one at a time (the `Bundle`
keeps the zip open; use it as a context manager or call `close()`)."""

import io
import lzma
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field, replace
from typing import IO

from app.core.citations_bundle import EXPORT_NAME
from app.core.citations_import import MAX_BYTES, CitationsImportError, ImportEntry, parse
from app.core.pipeline import MAX_UPLOAD_PDF_BYTES

MAX_ZIP_BYTES = 200 * 1024 * 1024  # total uncompressed
MAX_MEMBERS = 20_000
REFS_SUFFIXES = (".bib", ".bibtex", ".ris", ".json")
_METHODS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
_SYMLINK = 0o120000
_TYPE_MASK = 0o170000
# The names Zotero gives an export of the whole library or of selected items, and PaperLab's own export's name: not
# collections.
DEFAULT_EXPORT_NAMES = frozenset({"My Library", "Exported Items", EXPORT_NAME})


def _clean(name: str) -> str:
    """Forward slashes and NFC, so an accented name matches however the OS or the file spelled it."""
    return unicodedata.normalize("NFC", name.replace("\\", "/"))


def _unsafe(name: str) -> bool:
    n = _clean(name)
    return n.startswith("/") or (len(n) > 1 and n[1] == ":") or ".." in n.split("/")


def _vet(infos: list[zipfile.ZipInfo]) -> None:
    """Reject the whole zip on the first hostile member, using only the central directory."""
    bad = CitationsImportError("This zip can't be imported safely, so nothing was imported.")
    if len(infos) > MAX_MEMBERS:
        raise CitationsImportError("This zip has more files than PaperLab imports at once.")
    if len({_clean(i.filename) for i in infos}) != len(infos):
        raise bad
    total = 0
    for i in infos:
        if i.compress_type not in _METHODS:
            raise CitationsImportError("This zip uses a compression PaperLab doesn't read, so nothing was imported.")
        if _unsafe(i.filename) or i.flag_bits & 0x1 or (i.external_attr >> 16) & _TYPE_MASK == _SYMLINK:
            raise bad
        total += i.file_size
        if i.file_size > MAX_ZIP_BYTES or total > MAX_ZIP_BYTES:
            raise CitationsImportError("This zip is larger than 200 MB, which is more than PaperLab imports at once.")


def _read(zf: zipfile.ZipFile, info: zipfile.ZipInfo, head: bool = False) -> bytes:
    """The member's bytes (or just the first 5). The declared size was vetted and zipfile never reads past it."""
    try:
        with zf.open(info) as f:
            return f.read(5) if head else f.read()
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error, lzma.LZMAError, OSError):
        raise CitationsImportError("This zip is damaged, so nothing was imported.") from None


def _refs_member(infos: list[zipfile.ZipInfo]) -> zipfile.ZipInfo:
    """The one references file: skip anything under a `files` folder, take the shallowest (Finder may wrap the
    export in a folder), and refuse a tie."""
    found = []
    for i in infos:
        parts = _clean(i.filename).lower().split("/")
        if i.is_dir() or not parts[-1].endswith(REFS_SUFFIXES) or parts[-1].startswith("."):
            continue
        if "files" not in parts[:-1] and "__macosx" not in parts[:-1]:
            found.append((len(parts), i))
    if not found:
        raise CitationsImportError("This zip has no .bib, .ris or .json references file in it.")
    shallowest = min(d for d, _ in found)
    top = [i for d, i in found if d == shallowest]
    if len(top) > 1:
        raise CitationsImportError("This zip has more than one references file. Export one collection at a time.")
    return top[0]


@dataclass(frozen=True)
class Bundle:
    entries: list[ImportEntry]
    warnings: list[str]
    _zf: zipfile.ZipFile = field(repr=False)
    _paths: list[str | None] = field(repr=False)  # per entry index: its PDF's member name in the zip
    _pdfs: dict[str, zipfile.ZipInfo] = field(repr=False)

    def pdf_path(self, index: int) -> str | None:
        """The zip member holding `entries[index]`'s PDF, or None."""
        return self._paths[index]

    def read_pdf(self, member: str) -> bytes:
        """One PDF from the zip (a name from `pdf_path`), checked as a PDF. CitationsImportError otherwise."""
        info = self._pdfs.get(_clean(member))
        if info is None:
            raise CitationsImportError(f"{member} is not a PDF in this zip.")
        data = _read(self._zf, info)
        if not data.startswith(b"%PDF-"):
            raise CitationsImportError(f"{member} isn't a PDF.")
        return data

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> "Bundle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _is_pdf_path(raw: str) -> bool:
    return _clean(raw).strip().lower().endswith(".pdf")


def _pair(zf: zipfile.ZipFile, infos, entries: list[ImportEntry], base: str) -> tuple[list, dict, list[str]]:
    pdfs = {_clean(i.filename): i for i in infos if i.filename.lower().endswith(".pdf") and not i.is_dir()}
    lowered: dict[str, zipfile.ZipInfo | None] = {}
    for name, i in pdfs.items():  # a case-insensitive match must be unambiguous
        lowered[name.lower()] = None if name.lower() in lowered else i
    paths, warnings = [], []
    for entry in entries:
        found, reported = None, False
        wanted = [raw for raw in entry.files if _is_pdf_path(raw)]
        for raw in wanted:
            path = _clean(raw).strip().removeprefix("./")
            info = next((m for c in (path, base + path) if (m := pdfs.get(c) or lowered.get(c.lower()))), None)
            if info is None:
                continue
            if info.file_size > MAX_UPLOAD_PDF_BYTES:
                warnings.append(f"'{entry.title}': {raw} is larger than PaperLab's PDF limit, so it was left out.")
                reported = True
            elif _head_ok(zf, info):
                found = info
                break
            else:
                warnings.append(f"'{entry.title}': {raw} isn't a PDF, so it was left out.")
                reported = True
        paths.append(found.filename if found else None)
        if found is None and entry.files and not wanted:
            warnings.append(f"'{entry.title}': no PDF attachment.")
        elif found is None and wanted and not reported:
            warnings.append(f"'{entry.title}': its PDF isn't in the zip.")
    return paths, pdfs, warnings


def _head_ok(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bool:
    try:
        return _read(zf, info, head=True) == b"%PDF-"
    except CitationsImportError:
        return False


def read_bundle(data: bytes | IO[bytes]) -> Bundle:
    """Entries from the zip's references file, paired with the PDFs inside it. Raises CitationsImportError."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data)
    except (zipfile.BadZipFile, OSError, ValueError):
        raise CitationsImportError("This isn't a zip file PaperLab can read.") from None
    try:
        infos = zf.infolist()
        _vet(infos)
        refs = _refs_member(infos)
        name = _clean(refs.filename)
        if refs.file_size > MAX_BYTES:
            raise CitationsImportError("The references file is larger than 20 MB, which PaperLab can't import.")
        entries = parse(name.rsplit("/", 1)[-1], _read(zf, refs))
        stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        collection = None if stem in DEFAULT_EXPORT_NAMES else stem  # an exported collection is named after it
        entries = [e if e.collection or not collection else replace(e, collection=collection) for e in entries]
        paths, pdfs, warnings = _pair(zf, infos, entries, name[: name.rfind("/") + 1])
        return Bundle(entries, warnings, zf, paths, pdfs)
    except BaseException:
        zf.close()
        raise
