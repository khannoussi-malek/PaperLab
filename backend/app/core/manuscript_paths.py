"""Which file paths a manuscript may hold, and the size caps."""

import re

from app.core.errors import InvalidInput

TEXT_EXTENSIONS = {".tex", ".bib", ".sty", ".cls", ".bst", ".txt", ".md", ".csv", ".dat"}
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
TEXT_NAMES = {"latexmkrc"}
MAX_TEXT = 2 * 1024**2
MAX_BINARY = 20 * 1024**2
MAX_TOTAL = 100 * 1024**2
MAX_FILES = 500
MAX_DEPTH = 4
RESERVED = "paperlab.bib"
_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")


def _extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_text(path: str) -> bool:
    return path.rsplit("/", 1)[-1] in TEXT_NAMES or _extension(path) in TEXT_EXTENSIONS


def validate_path(path: str) -> str:
    segments = path.split("/")
    if len(segments) > MAX_DEPTH or not all(_SEGMENT.fullmatch(s) and s not in {".", ".."} for s in segments):
        raise InvalidInput("bad_path")
    if path == RESERVED:
        raise InvalidInput("reserved_path")
    if not is_text(path) and _extension(path) not in BINARY_EXTENSIONS:
        raise InvalidInput("unsupported_file_type")
    return path
