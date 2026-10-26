"""Overleaf-style zips in and out of a manuscript. Pure: no database, no files."""

import io
import re
import stat
import zipfile

from app.core import manuscript_paths as paths
from app.core.errors import Conflict, DomainError, InvalidInput

IMPORTED_BIB = "paperlab-imported.bib"
LATEXMKRC = "$pdf_mode = 5;  # XeLaTeX\n"
DOCUMENTCLASS = re.compile(r"^[^%\n]*\\documentclass", re.M)


def _skipped(name: str) -> bool:
    segments = name.split("/")
    return name.endswith("/") or segments[0] == "__MACOSX" or any(
        s.startswith(".") and s not in {".", ".."} for s in segments)


def _read_capped(archive: zipfile.ZipFile, info: zipfile.ZipInfo, cap: int) -> bytes:
    with archive.open(info) as member:
        data = member.read(cap + 1)  # a header that understates its size cannot get past the cap
    if len(data) > cap:
        raise Conflict("file_too_large", limit=cap)  # the class the manuscript's own caps raise
    return data


def _main_file(files: dict[str, str | bytes]) -> str:
    with_class = [p for p, c in files.items() if p.endswith(".tex") and isinstance(c, str) and DOCUMENTCLASS.search(c)]
    if "main.tex" in with_class:
        return "main.tex"
    if len(with_class) == 1:
        return with_class[0]
    raise InvalidInput("no_main_file")


def _member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[str, str | bytes] | None:
    """(path, content) of one member, or None for a type a manuscript can't hold. Errors raised carry no path yet."""
    if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
        raise InvalidInput("bad_zip")
    path = IMPORTED_BIB if info.filename == paths.RESERVED else info.filename
    try:
        paths.validate_path(path)
    except InvalidInput as exc:
        if str(exc) == "unsupported_file_type":
            return None
        raise
    if not paths.is_text(path):
        return path, _read_capped(archive, info, paths.MAX_BINARY)
    raw = _read_capped(archive, info, paths.MAX_TEXT)
    try:
        return path, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidInput("not_text") from exc


def read_zip(data: bytes) -> tuple[dict[str, str | bytes], str, list[str]]:
    """The files in the zip, the main file and the paths skipped for being a type a manuscript can't hold. Every
    error from a member names it in `path`."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InvalidInput("bad_zip") from exc
    with archive:
        infos = [i for i in archive.infolist() if not _skipped(i.filename)]
        if len(infos) > paths.MAX_FILES:
            raise Conflict("too_many_files", limit=paths.MAX_FILES)
        if sum(i.file_size for i in infos) > paths.MAX_TOTAL:
            raise Conflict("manuscript_too_large", limit=paths.MAX_TOTAL)
        files: dict[str, str | bytes] = {}
        seen: set[str] = set()
        skipped: list[str] = []
        for info in infos:
            try:
                if info.filename.casefold() in seen:  # twice, or twice in different case: one file on a Mac
                    raise InvalidInput("bad_zip")
                seen.add(info.filename.casefold())
                member = _member(archive, info)
            except DomainError as exc:
                raise type(exc)(str(exc), **{**exc.details, "path": info.filename}) from exc
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:  # CRC, odd compression, encryption
                raise InvalidInput("bad_zip", path=info.filename) from exc
            if member is None:
                skipped.append(info.filename)
            else:
                files[member[0]] = member[1]
    return files, _main_file(files), skipped


def write_zip(files: dict[str, str | bytes], bib: str, pdf: bytes | None, title: str = "manuscript") -> bytes:
    """Every file, paperlab.bib, a latexmkrc (the project's own wins) and, when there is one, <title>.pdf."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
        archive.writestr(paths.RESERVED, bib)
        if "latexmkrc" not in files:
            archive.writestr("latexmkrc", LATEXMKRC)
        if pdf is not None:
            archive.writestr(f"{re.sub(r'[^A-Za-z0-9._-]', '_', title).strip('_') or 'manuscript'}.pdf", pdf)
    return buf.getvalue()
