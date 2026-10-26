"""Overleaf-style zips in and out of a manuscript. Pure: no database, no files."""

import io
import re
import zipfile

from app.core import manuscript_paths as paths
from app.core.errors import InvalidInput

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
        raise InvalidInput("file_too_large", path=info.filename, limit=cap)
    return data


def _main_file(files: dict[str, str | bytes]) -> str:
    with_class = [p for p, c in files.items() if p.endswith(".tex") and isinstance(c, str) and DOCUMENTCLASS.search(c)]
    if "main.tex" in with_class:
        return "main.tex"
    if len(with_class) == 1:
        return with_class[0]
    raise InvalidInput("no_main_file")


def read_zip(data: bytes) -> tuple[dict[str, str | bytes], str]:
    """The files in the zip and the main file. Refuses what the manuscript caps would."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InvalidInput("bad_zip") from exc
    with archive:
        infos = [i for i in archive.infolist() if not _skipped(i.filename)]
        if len(infos) > paths.MAX_FILES:
            raise InvalidInput("too_many_files", limit=paths.MAX_FILES)
        if sum(i.file_size for i in infos) > paths.MAX_TOTAL:
            raise InvalidInput("zip_too_large", limit=paths.MAX_TOTAL)
        files: dict[str, str | bytes] = {}
        try:
            for info in infos:
                path = IMPORTED_BIB if info.filename == paths.RESERVED else info.filename
                paths.validate_path(path)
                if paths.is_text(path):
                    raw = _read_capped(archive, info, paths.MAX_TEXT)
                    try:
                        files[path] = raw.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise InvalidInput("not_text", path=path) from exc
                else:
                    files[path] = _read_capped(archive, info, paths.MAX_BINARY)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:  # CRC, odd compression, encryption
            raise InvalidInput("bad_zip") from exc
    return files, _main_file(files)


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
