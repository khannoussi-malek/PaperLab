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


def _write(items: list[dict], papers: list, fmt: str) -> IO[bytes]:
    keys = citations_export.bibtex_keys(items)
    on_disk = {p.id: Path(p.file_path) for p in papers if Path(p.file_path).is_file()}
    # the same key the BibTeX writer assigns; items are new dicts, the CSL items stay untouched
    named = [{**i, "_file": f"files/{keys[i['id']]}.pdf"} if uuid.UUID(i["id"]) in on_disk else i for i in items]
    out = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    ext = citations_export.FORMATS[fmt][1]
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(f"refs.{ext}", citations_export.render(named, fmt), compress_type=zipfile.ZIP_DEFLATED)
        for item in named:
            if "_file" in item:  # PDFs are already compressed: store them
                zf.write(on_disk[uuid.UUID(item["id"])], item["_file"], compress_type=zipfile.ZIP_STORED)
    size = out.tell()
    out.seek(0)
    return out, size


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
