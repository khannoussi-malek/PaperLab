"""Compiled-PDF checks (P9): page limit, overfull boxes and unresolved references. Findings only; nothing edits text."""

from pathlib import Path

import pymupdf

from app.core import manuscript_templates
from app.core.manuscript_template_spec import TemplateSpec

from . import pdf_layout, pdf_log
from .base import Check, CheckContext, Finding

OVERFULL_MIN_PT = 5.0
UNDERFULL_MIN_BADNESS = 10000
MAX_UNDERFULL = 10
_UNREADABLE = (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError, OSError)

_LIMIT = "pdf.page_limit"
_OVERFULL = "pdf.overfull_boxes"
_UNRESOLVED_NAME = "pdf.unresolved_refs"
_RUNNING = "A compile is running; check again when it finishes."
_NO_PDF = "No compiled PDF to check yet."
_NO_PDF_HINT = "Compile the manuscript, then press Check again."
_UNREADABLE_MSG = "The compiled PDF couldn't be read."
_STALE_MSG = "The PDF is older than your last edit; compile again for current numbers."
_OVERFULL_HINT = (
    "Rephrase near this line, add a hyphenation point with \\-, or for a table or figure "
    "reduce its width (for example \\resizebox{\\columnwidth}{!}{...})."
)
_UNRESOLVED_HINT = (
    "Compile again. If the marks stay, a \\ref label or cite key doesn't exist; "
    "the cited-keys check lists missing keys."
)


def _finding(check: str, severity: str, message: str, fix_hint: str | None = None,
             file: str | None = None, line: int | None = None) -> Finding:
    return Finding(check, severity, file, line, message, fix_hint)


def _ready(ctx: CheckContext) -> Path | None:
    m = ctx.manuscript
    return m.pdf_path if m.compile_status == "ok" else None


def _gate(ctx: CheckContext) -> list[Finding]:
    if ctx.manuscript.compile_status == "running":
        return [_finding(_LIMIT, "info", _RUNNING)]
    return [_finding(_LIMIT, "info", _NO_PDF, _NO_PDF_HINT)]


def _stale(ctx: CheckContext) -> bool:
    m = ctx.manuscript
    return m.updated_at is not None and m.compiled_at is not None and m.updated_at > m.compiled_at


def _counted(spec: TemplateSpec, stats: pdf_layout.PdfStats) -> tuple[int, str]:
    if spec.references_count:
        return stats.page_count, "references included"
    if stats.body_pages is None:
        return stats.page_count, (
            "references not counted, but no References heading found, so all pages are counted")
    return stats.body_pages, f"references not counted: body ends on page {stats.body_pages}"


def _no_limit(stats: pdf_layout.PdfStats) -> Finding:
    pages = "page" if stats.page_count == 1 else "pages"
    if stats.body_pages is None:
        message = f"This PDF has {stats.page_count} {pages}. The template sets no page limit."
    else:
        message = (f"This PDF has {stats.page_count} {pages}; the body ends on page "
                   f"{stats.body_pages}. The template sets no page limit.")
    return _finding(_LIMIT, "info", message)


def _against_limit(spec: TemplateSpec, stats: pdf_layout.PdfStats) -> Finding:
    counted, how = _counted(spec, stats)
    limit = spec.page_limit
    if counted > limit:
        return _finding(
            _LIMIT, "warning",
            f"{counted} pages count against the {limit}-page limit of {spec.label} ({how}).",
            f"Cut or tighten text, or shrink figures, to get {counted - limit} page(s) back. "
            "PaperLab doesn't change your text.")
    return _finding(_LIMIT, "info", f"{counted} of {limit} pages used ({how}).")


def _page_limit(ctx: CheckContext) -> list[Finding]:
    path = _ready(ctx)
    if path is None:
        return _gate(ctx)
    try:
        stats = pdf_layout.stats(path)
    except _UNREADABLE:
        return [_finding(_LIMIT, "info", _UNREADABLE_MSG, "Compile again.")]
    spec = manuscript_templates.get(ctx.manuscript.template)
    found = [_no_limit(stats) if spec is None or spec.page_limit is None else _against_limit(spec, stats)]
    if _stale(ctx):
        found.append(_finding(_LIMIT, "info", _STALE_MSG))
    return found


def _span(first: int, last: int) -> str:
    return f"line {first}" if first == last else f"lines {first}-{last}"


def _overfull_finding(box: pdf_log.Box) -> Finding:
    message = f"Line is {box.amount:g}pt too wide ({_span(box.first_line, box.last_line)})."
    return _finding(_OVERFULL, "warning", message, _OVERFULL_HINT, box.file, box.first_line)


def _underfull_findings(boxes: list[pdf_log.Box]) -> list[Finding]:
    shown = [
        _finding(_OVERFULL, "info", f"Line is badly stretched ({_span(b.first_line, b.last_line)}).",
                 file=b.file, line=b.first_line)
        for b in boxes[:MAX_UNDERFULL]
    ]
    hidden = len(boxes) - MAX_UNDERFULL
    if hidden > 0:
        shown.append(_finding(_OVERFULL, "info", f"{hidden} more badly stretched lines not listed."))
    return shown


def _opens(path: Path) -> bool:
    try:
        with pymupdf.open(path):
            return True
    except _UNREADABLE:
        return False


def _overfull(ctx: CheckContext) -> list[Finding]:
    path = _ready(ctx)
    if path is None or not ctx.manuscript.compile_log or not _opens(path):
        return []
    boxes = pdf_log.boxes(ctx.manuscript.compile_log)
    overfull = [b for b in boxes if b.kind == "overfull"]
    big = [b for b in overfull if b.amount >= OVERFULL_MIN_PT]
    small = len(overfull) - len(big)
    underfull = [b for b in boxes if b.kind == "underfull" and b.amount == UNDERFULL_MIN_BADNESS]
    found = [_overfull_finding(b) for b in big]
    if small:
        found.append(_finding(_OVERFULL, "info", f"{small} smaller overfull box(es) (under 5pt) not listed."))
    return found + _underfull_findings(underfull)


def _unresolved(ctx: CheckContext) -> list[Finding]:
    path = _ready(ctx)
    if path is None:
        return []
    try:
        pages = pdf_layout.unresolved(path)
    except _UNREADABLE:
        return []
    return [
        _finding(_UNRESOLVED_NAME, "warning",
                 f"Page {page} shows {count} unresolved reference or citation mark(s) (?? or [?]).",
                 _UNRESOLVED_HINT)
        for page, count in pages
    ]


PAGE_LIMIT = Check(_LIMIT, "full", "Page count against the template's page limit", _page_limit)
OVERFULL = Check(_OVERFULL, "full", "Overfull and badly stretched lines from the compile log", _overfull)
UNRESOLVED = Check(_UNRESOLVED_NAME, "full", "Unresolved references (?? or [?]) in the compiled PDF", _unresolved)
CHECKS = (PAGE_LIMIT, OVERFULL, UNRESOLVED)
