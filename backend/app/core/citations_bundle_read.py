"""Read a Zotero "export with files" zip (M40 Task 8, I3): the references file plus the PDFs its entries point at.
Parsing only, no database. The zip is never trusted: every member is vetted from the central directory before
anything is read, nothing is extracted by path or written to disk, and PDFs are read one at a time (the `Bundle`
keeps the zip open; use it as a context manager or call `close()`)."""

import io
import zipfile
from dataclasses import dataclass, field, replace
from typing import IO

from app.core.citations_import import MAX_BYTES, MIME_TAIL, CitationsImportError, ImportEntry, parse

MAX_ZIP_BYTES = 200 * 1024 * 1024  # total uncompressed
MAX_MEMBERS = 20_000
REFS_SUFFIXES = (".bib", ".bibtex", ".ris", ".json")
_SYMLINK = 0o120000
_TYPE_MASK = 0o170000


def _clean(name: str) -> str:
    return name.replace("\\", "/")


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
        if _unsafe(i.filename) or i.flag_bits & 0x1 or (i.external_attr >> 16) & _TYPE_MASK == _SYMLINK:
            raise bad
        total += i.file_size
        if i.file_size > MAX_ZIP_BYTES or total > MAX_ZIP_BYTES:
            raise CitationsImportError("This zip is larger than 200 MB, which is more than PaperLab imports at once.")


def _read(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int, head: bool = False) -> bytes:
    """At most `limit` bytes; more means the declared size lied, so the zip is refused. `head`: just the first 5."""
    try:
        with zf.open(info) as f:
            data = f.read(5 if head else limit + 1)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError):
        raise CitationsImportError("This zip is damaged, so nothing was imported.") from None
    if len(data) > limit and not head:
        raise CitationsImportError("This zip is larger than it says it is, so nothing was imported.")
    return data


def _refs_member(infos: list[zipfile.ZipInfo]) -> zipfile.ZipInfo:
    found = []
    for i in infos:
        name = _clean(i.filename)
        if i.is_dir() or not name.lower().endswith(REFS_SUFFIXES) or name.startswith(("files/", "__MACOSX/")):
            continue
        if not name.rsplit("/", 1)[-1].startswith("."):
            found.append(i)
    if not found:
        raise CitationsImportError("This zip has no .bib, .ris or .json references file in it.")
    if len(found) > 1:
        raise CitationsImportError("This zip has more than one references file. Export one collection at a time.")
    return found[0]


@dataclass(frozen=True)
class Bundle:
    entries: list[ImportEntry]
    warnings: list[str]
    _zf: zipfile.ZipFile = field(repr=False)
    _pdfs: dict[int, zipfile.ZipInfo] = field(repr=False)  # id(entry) -> its PDF member

    def has_pdf(self, entry: ImportEntry) -> bool:
        return id(entry) in self._pdfs

    def pdf_for(self, entry: ImportEntry) -> bytes | None:
        """The entry's PDF, read now (one member in memory at a time), or None."""
        info = self._pdfs.get(id(entry))
        return None if info is None else _read(self._zf, info, max(info.file_size, 1))

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> "Bundle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _candidates(raw: str, base: str) -> list[str]:
    path = MIME_TAIL.sub("", _clean(raw).strip())
    if path.lower().startswith("desc:"):
        path = path[5:]
    path = path.removeprefix("./")
    return [path, base + path] if base else [path]


def _match(path: str, exact: dict, lowered: dict) -> zipfile.ZipInfo | None:
    return exact.get(path) or lowered.get(path.lower())


def _pair(zf: zipfile.ZipFile, infos, entries: list[ImportEntry], base: str) -> tuple[dict, list[str]]:
    pdfs = [i for i in infos if i.filename.lower().endswith(".pdf") and not i.is_dir()]
    exact = {_clean(i.filename): i for i in pdfs}
    lowered: dict[str, zipfile.ZipInfo | None] = {}
    for name, i in exact.items():  # a case-insensitive match must be unambiguous
        lowered[name.lower()] = None if name.lower() in lowered else i
    paired, warnings = {}, []
    for entry in entries:
        for raw in entry.files:
            info = next((m for c in _candidates(raw, base) if (m := _match(c, exact, lowered))), None)
            if info is None:
                continue
            if _read(zf, info, 0, head=True) != b"%PDF-":
                warnings.append(f"'{entry.title}': {raw} isn't a PDF, so it was left out.")
                continue
            paired[id(entry)] = info
            break
        else:
            if entry.files:
                warnings.append(f"'{entry.title}': its PDF isn't in the zip.")
    return paired, warnings


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
        entries = parse(name.rsplit("/", 1)[-1], _read(zf, refs, MAX_BYTES))
        collection = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        entries = [e if e.collection else replace(e, collection=collection) for e in entries]
        base = name[: name.rfind("/") + 1]
        pdfs, warnings = _pair(zf, infos, entries, base)
        return Bundle(entries, warnings, zf, pdfs)
    except BaseException:
        zf.close()
        raise
