"""Compiles a generated TikZ picture to a cropped PDF preview, offline (M27e). Runs under the worker's compile lock."""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core import diagram_tikz, latex_compile

PREVIEW_TIMEOUT = 30
MAX_PDF = 300 * 1024


@dataclass(frozen=True)
class PreviewResult:
    ok: bool
    pdf: bytes | None
    errors: list[dict]  # {line, message}; line counts from the first line of the researcher's picture
    friendly: str | None


async def preview(libraries: list[str], picture: str) -> PreviewResult:
    if problems := diagram_tikz.check(libraries, picture):  # re-run here: nothing unchecked is ever compiled
        return PreviewResult(False, None, [{"line": None, "message": m} for m in problems], "diagram_invalid")
    doc = diagram_tikz.preview_document(libraries, picture)
    offset = doc[: doc.index(picture)].count("\n")  # wrapper lines before the picture
    last = picture.count("\n") + 1
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "main.tex").write_text(doc)
        res = await latex_compile.compile_dir(Path(tmp), "main.tex", timeout=PREVIEW_TIMEOUT)
    errors = [
        {"line": line if line is not None and 0 < line <= last else None, "message": e["message"]}
        for e in res.errors
        if e["kind"] != "warning"
        for line in [e["line"] - offset if e["line"] is not None and e["file"] == "main.tex" else None]
    ]
    if res.ok and len(res.pdf) > MAX_PDF:
        return PreviewResult(False, None, errors, "diagram_too_large")
    return PreviewResult(res.ok, res.pdf, errors, res.friendly)
