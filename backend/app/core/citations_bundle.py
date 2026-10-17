"""Citations with their PDFs for Zotero (M40 D270): `refs.<bib|ris>` plus `files/<key>.pdf`, the layout of Zotero's own
"export with files". The zip is written to a spooled temp file straight from disk, so a workspace's PDFs are never
all in memory."""

import asyncio
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import citations_export
from app.core.errors import InvalidInput

BUNDLE_FORMATS = ("bibtex", "ris")
SPOOL_BYTES = 8 * 1024 * 1024  # above this the temp file spills to disk
CHUNK = 64 * 1024


def _write(items: list[dict], papers: list, fmt: str) -> tuple[IO[bytes], int]:
    keys = citations_export.bibtex_keys(items)
    on_disk = {p.id: Path(p.file_path) for p in papers if Path(p.file_path).is_file()}
    out = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    try:
        attached: dict[str, str] = {}  # item id -> path in the zip, for the PDFs actually written
        with zipfile.ZipFile(out, "w") as zf:
            for item in items:
                if not (path := on_disk.get(uuid.UUID(item["id"]))):
                    continue
                name = f"files/{keys[item['id']]}.pdf"
                try:  # PDFs are already compressed: store them
                    zf.write(path, name, compress_type=zipfile.ZIP_STORED)
                except FileNotFoundError:  # vanished since the check: no attachment, like a missing one
                    continue
                attached[item["id"]] = name
            named = [{**i, "_file": attached[i["id"]]} if i["id"] in attached else i for i in items]
            refs = citations_export.render(named, fmt)
            zf.writestr(f"refs.{citations_export.FORMATS[fmt][1]}", refs, compress_type=zipfile.ZIP_DEFLATED)
        size = out.tell()
        out.seek(0)
        return out, size
    except BaseException:
        out.close()
        raise


async def build(session: AsyncSession, workspace_id: uuid.UUID, fmt: str, notes: bool) -> tuple[IO[bytes], int]:
    """(zip file positioned at 0, its size) for the workspace. Raises InvalidInput unknown_format / no_papers,
    NotFound. A paper whose PDF is missing on disk is listed without an attachment."""
    if fmt not in BUNDLE_FORMATS:
        raise InvalidInput("unknown_format")
    papers, items = await citations_export.load_items(session, workspace_id=workspace_id, notes=notes)
    return await asyncio.to_thread(_write, items, papers, fmt)


def chunks(file: IO[bytes]) -> Iterator[bytes]:
    try:
        while data := file.read(CHUNK):
            yield data
    finally:
        file.close()
