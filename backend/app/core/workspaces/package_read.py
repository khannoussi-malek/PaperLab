"""Reading a workspace package before import: open the zip safely and check every file's shape."""

import io
import json
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import IO

from pydantic import BaseModel, ValidationError

from app.core.citations import citations_bundle_read
from app.core.citations.citations_import import CitationsImportError
from app.core.workspaces import workspace_package_screening
from app.core.workspaces.workspace_package import (
    FORMAT,
    FORMAT_VERSION,
    INVALID,
    MAX_JSON_BYTES,
    TOO_LARGE,
    UNKNOWN_FORMAT,
    UNSAFE,
)
from app.core.workspaces.workspace_package_shapes import (
    AnswersDoc,
    Manifest,
    NotesDoc,
    PapersDoc,
    PrismaTotals,
    ScreeningV2,
    TagsDoc,
)
from app.domain.errors import InvalidInput


@dataclass(frozen=True)
class _Package:
    zf: zipfile.ZipFile
    manifest: dict
    papers: list[dict]
    notes: list[dict]
    tags: list[dict]
    screening: dict
    prisma: dict
    answers: list[dict]


def _invalid(detail: str = INVALID) -> InvalidInput:
    return InvalidInput(detail)


def _open(data: bytes | IO[bytes]) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data)
    except (zipfile.BadZipFile, OSError, ValueError):
        raise InvalidInput(UNKNOWN_FORMAT) from None


def _vet(zf: zipfile.ZipFile) -> None:
    """citations_bundle_read's zip checks, from the central directory alone. Too many members or too many bytes is
    package_too_large; any other refusal is package_unsafe."""
    infos = zf.infolist()
    too_many = len(infos) > citations_bundle_read.MAX_MEMBERS
    if too_many or sum(i.file_size for i in infos) > citations_bundle_read.MAX_ZIP_BYTES:
        raise InvalidInput(TOO_LARGE)
    try:
        citations_bundle_read._vet(infos)
    except CitationsImportError:
        raise InvalidInput(UNSAFE) from None


def _no_nul(value):
    """The value with NUL characters removed from every string (Postgres text and JSONB refuse them). A new value."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_no_nul(item) for item in value]
    if isinstance(value, dict):
        return {_no_nul(key): _no_nul(item) for key, item in value.items()}
    return value


def _json(zf: zipfile.ZipFile, name: str):
    if name not in zf.NameToInfo:
        raise InvalidInput(INVALID)
    info = zf.getinfo(name)
    if info.file_size > MAX_JSON_BYTES:
        raise InvalidInput(TOO_LARGE)
    try:
        return _no_nul(json.loads(zf.read(info)))
    except (ValueError, OSError, RuntimeError, EOFError, NotImplementedError, zipfile.BadZipFile, zlib.error):
        raise InvalidInput(INVALID) from None


def _supported(version) -> bool:
    return isinstance(version, int) and not isinstance(version, bool) and 1 <= version <= FORMAT_VERSION


def _made_on(manifest: dict) -> str:
    try:
        return datetime.fromisoformat(manifest["created_at"]).date().isoformat()
    except (KeyError, TypeError, ValueError):
        raise InvalidInput(INVALID) from None


def _shaped(model: type[BaseModel], doc):
    """The document, when it takes the shape the model describes; package_invalid otherwise. Never a server error."""
    try:
        model.model_validate(doc)
    except ValidationError:
        raise InvalidInput(INVALID) from None
    return doc


def _check_papers(doc) -> list[dict]:
    rows = doc["papers"]
    keys = [row["key"] for row in rows]
    if len(set(keys)) != len(keys) or not all(row["title"].strip() for row in rows):
        raise InvalidInput(INVALID)
    return rows


def _check_notes(doc, keys: set[str]) -> list[dict]:
    rows = doc["notes"]
    for row in rows:
        listed = set(row.get("papers") or [])
        highlights = row.get("highlights") or []
        if not listed <= keys or any(h["paper"] not in listed for h in highlights):
            raise InvalidInput(INVALID)
    return rows


def _check_tags(doc, keys: set[str]) -> list[dict]:
    rows = doc["tags"]
    if not all(set(r.get("papers") or []) <= keys for r in rows):
        raise InvalidInput(INVALID)
    return rows


def _answer_rows(zf: zipfile.ZipFile) -> list[dict]:
    """answers.json's rows when the package has the member; a package from before M35b2 has none and no answers."""
    if "answers.json" not in zf.NameToInfo:
        return []
    return _shaped(AnswersDoc, _json(zf, "answers.json"))["answers"]


def _check_screening_v2(screening: dict, prisma: dict, paper_keys: set[str]) -> None:
    """A version 2 screening takes its shape, names only keys the package holds, and prisma.json carries the totals
    the count check reads."""
    _shaped(ScreeningV2, screening)
    _shaped(PrismaTotals, prisma)
    try:
        workspace_package_screening.check_references(screening, paper_keys)
    except ValueError:
        raise InvalidInput(INVALID) from None


def _read(zf: zipfile.ZipFile) -> _Package:
    """Every member, checked: the manifest first (a file without one, or of another format, is refused before anything
    else is read). Each JSON member must take the shape its model describes."""
    if "manifest.json" not in zf.NameToInfo:
        raise InvalidInput(UNKNOWN_FORMAT)
    manifest = _json(zf, "manifest.json")
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != FORMAT
        or not _supported(manifest.get("format_version"))
    ):
        raise InvalidInput(UNKNOWN_FORMAT)
    _shaped(Manifest, manifest)
    papers_rows = _check_papers(_shaped(PapersDoc, _json(zf, "papers.json")))
    keys = {row["key"] for row in papers_rows}
    notes_rows = _check_notes(_shaped(NotesDoc, _json(zf, "notes.json")), keys)
    tag_rows = _check_tags(_shaped(TagsDoc, _json(zf, "tags.json")), keys)
    screening, prisma = _json(zf, "screening.json"), _json(zf, "prisma.json")
    if not isinstance(screening, dict) or not isinstance(prisma, dict):
        raise InvalidInput(INVALID)
    if workspace_package_screening.is_v2(screening):
        _check_screening_v2(screening, prisma, {row["key"] for row in papers_rows})
    _made_on(manifest)
    return _Package(zf, manifest, papers_rows, notes_rows, tag_rows, screening, prisma, _answer_rows(zf))
