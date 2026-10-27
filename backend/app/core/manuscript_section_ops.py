"""Add, retitle, move, delete and split sections. Each validates first, then locks the main file, snapshots as
`before_sections` and writes, so history can undo it. The caller commits."""

import uuid

from app.core import manuscript_history, manuscripts
from app.core import manuscript_sections as sec
from app.core.errors import Conflict, InvalidInput

REASON = "before_sections"


async def _open(session, mid: uuid.UUID) -> tuple[str, str, set[str]]:
    """(main path, main text, every file path), with the main row locked against a concurrent save."""
    main_path = (await manuscripts.get(session, mid)).main_file
    row = await manuscripts._file(session, mid, main_path, lock=True)
    taken = {f.path for f in await manuscripts.files(session, mid)}
    return main_path, row.text or "", taken


async def _lock(session, mid: uuid.UUID, path: str):
    """The section's row, locked right after main's (always that order) and before it is read or snapshotted, so a
    save of it can't land between our read and our write. None when the file is missing."""
    return await manuscripts._file(session, mid, path, lock=True)


async def add(session, mid: uuid.UUID, *, title: str, after: str | None) -> str:
    title = sec.check_title(title)
    main_path, main, taken = await _open(session, mid)
    path = sec.section_path(title, taken)
    new_main = sec.insert_input(main, path, after)
    await manuscript_history.take(session, mid, REASON)
    await manuscripts.upsert_text(session, mid, path, f"\\section{{{title}}}\n\n")
    await manuscripts.upsert_text(session, mid, main_path, new_main)
    return path


async def retitle(session, mid: uuid.UUID, path: str, *, title: str) -> str:
    title = sec.check_title(title)
    main_path, main, taken = await _open(session, mid)
    row = await _lock(session, mid, path)
    text = row.text if row is not None else None
    if text is None:
        raise InvalidInput("not_a_section")
    new_path = sec.section_path(title, taken - {path}) if path.startswith(sec.SECTIONS_DIR + "/") else path
    new_main = sec.retarget_input(main, path, new_path)
    await manuscript_history.take(session, mid, REASON)
    if new_path != path:
        await manuscripts.rename(session, mid, path, new_path)
    await manuscripts.upsert_text(session, mid, new_path, sec.set_title(text, title))
    await manuscripts.upsert_text(session, mid, main_path, new_main)
    return new_path


async def move(session, mid: uuid.UUID, path: str, *, to: int) -> None:
    main_path, main, _ = await _open(session, mid)
    await _lock(session, mid, path)
    new_main = sec.move_input(main, path, to)
    await manuscript_history.take(session, mid, REASON)
    await manuscripts.upsert_text(session, mid, main_path, new_main)


async def delete(session, mid: uuid.UUID, path: str) -> None:
    main_path, main, taken = await _open(session, mid)
    if path == main_path:
        raise InvalidInput("not_a_section")
    await _lock(session, mid, path)
    new_main = sec.drop_input(main, path)
    await manuscript_history.take(session, mid, REASON)
    await manuscripts.upsert_text(session, mid, main_path, new_main)
    if path in taken:  # an \input of a missing file is just a row to drop
        await manuscripts.remove(session, mid, path)


async def split_main(session, mid: uuid.UUID) -> list[str]:
    main_path, main, taken = await _open(session, mid)
    new_main, files = sec.split(main)
    if taken & files.keys():
        raise Conflict("file_exists")
    await manuscript_history.take(session, mid, REASON)
    for path, text in files.items():
        await manuscripts.upsert_text(session, mid, path, text)
    await manuscripts.upsert_text(session, mid, main_path, new_main)
    return list(files)
