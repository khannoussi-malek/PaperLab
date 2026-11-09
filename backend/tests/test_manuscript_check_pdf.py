from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymupdf
import pytest

from app.core import latex_compile
from app.core.manuscript_checks import pdf
from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo

LOG = (
    "(main.tex\n(sections/method.tex\n"
    "Overfull \\hbox (12.3pt too wide) in paragraph at lines 40--42\n[]x\n\n"
    "Overfull \\hbox (2.0pt too wide) in paragraph at lines 50--50\n[]x\n\n"
    "Underfull \\hbox (badness 10000) in paragraph at lines 7--8\n[]x\n\n)\n)\n"
)
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def pdf_file(tmp_path: Path, n_pages: int, refs_on: int | None = None, extra: dict[int, str] | None = None) -> Path:
    """Every page has two lines of 12 words each (24 words) above y=400, so a heading at y=400 never reads as
    'starts a page'."""
    doc = pymupdf.open()
    for i in range(1, n_pages + 1):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), "body text " * 6, fontsize=11)
        page.insert_text((72, 120), "body text " * 6, fontsize=11)
        if i == refs_on:
            page.insert_text((72, 400), "References", fontsize=11)
        if extra and i in extra:
            page.insert_text((72, 500), extra[i], fontsize=11)
    path = tmp_path / "m.pdf"
    doc.save(path)
    return path


def ctx(template="ieee", status="ok", log=LOG, path=None, compiled_at=T0, updated_at=T0) -> CheckContext:
    return CheckContext(files={}, known_keys=frozenset(), manuscript=ManuscriptInfo(
        id="m", main_file="main.tex", compile_status=status, compiled_at=compiled_at,
        compile_log=log, pdf_path=path, updated_at=updated_at, template=template))


def test_gate_never_compiled_failed_or_missing_pdf(tmp_path):
    for c in (ctx(status="never"), ctx(status="failed", path=pdf_file(tmp_path, 1)), ctx(path=None)):
        found = pdf.PAGE_LIMIT.run(c)
        assert [(f.severity, f.message) for f in found] == [("info", "No compiled PDF to check yet.")]
        assert found[0].fix_hint == "Compile the manuscript, then press Check again."
        assert pdf.OVERFULL.run(c) == [] and pdf.UNRESOLVED.run(c) == []


def test_gate_running(tmp_path):
    c = ctx(status="running", path=pdf_file(tmp_path, 1))
    assert [f.message for f in pdf.PAGE_LIMIT.run(c)] == ["A compile is running; check again when it finishes."]
    assert pdf.OVERFULL.run(c) == [] and pdf.UNRESOLVED.run(c) == []


def test_unreadable_pdf(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    found = pdf.PAGE_LIMIT.run(ctx(path=bad))
    assert [(f.severity, f.message) for f in found] == [("info", "The compiled PDF couldn't be read.")]
    assert pdf.UNRESOLVED.run(ctx(path=bad)) == []
    assert pdf.OVERFULL.run(ctx(path=bad)) == []  # LOG holds boxes; an unreadable PDF still gives none


def test_stale_pdf_adds_one_info(tmp_path):
    p = pdf_file(tmp_path, 3)
    found = pdf.PAGE_LIMIT.run(ctx("ieee", path=p, updated_at=T0 + timedelta(minutes=5)))
    assert [f.message for f in found if f.severity == "info" and "older" in f.message] == [
        "The PDF is older than your last edit; compile again for current numbers."]
    assert len(found) == 2
    assert len(pdf.PAGE_LIMIT.run(ctx("ieee", path=p))) == 1                       # fresh
    assert len(pdf.PAGE_LIMIT.run(ctx("ieee", path=p, updated_at=None))) == 1       # unknown: not stale


def test_no_limit_is_info_only(tmp_path):
    f, = pdf.PAGE_LIMIT.run(ctx("article", path=pdf_file(tmp_path, 9, refs_on=8)))
    assert f.severity == "info" and f.file is None and f.line is None
    assert f.message == "This PDF has 9 pages; the body ends on page 8. The template sets no page limit."
    f, = pdf.PAGE_LIMIT.run(ctx("custom", path=pdf_file(tmp_path, 2)))
    assert f.message == "This PDF has 2 pages. The template sets no page limit."


def test_over_the_limit_references_counted(tmp_path):
    f, = pdf.PAGE_LIMIT.run(ctx("ieee", path=pdf_file(tmp_path, 8, refs_on=7)))
    assert f.severity == "warning"
    assert f.message == "8 pages count against the 6-page limit of IEEE conference (references included)."
    assert f.fix_hint == ("Cut or tighten text, or shrink figures, to get 2 page(s) back. "
                          "PaperLab doesn't change your text.")


def test_over_the_limit_references_not_counted(tmp_path):
    f, = pdf.PAGE_LIMIT.run(ctx("acm", path=pdf_file(tmp_path, 12, refs_on=11)))
    assert f.severity == "warning"
    assert f.message == ("11 pages count against the 9-page limit of ACM (sigconf) "
                         "(references not counted: body ends on page 11).")


def test_total_over_but_body_within(tmp_path):
    f, = pdf.PAGE_LIMIT.run(ctx("acm", path=pdf_file(tmp_path, 11, refs_on=9)))
    assert f.severity == "info"
    assert f.message == "9 of 9 pages used (references not counted: body ends on page 9)."


def test_within_limit_references_included_without_heading(tmp_path):
    f, = pdf.PAGE_LIMIT.run(ctx("lncs", path=pdf_file(tmp_path, 10)))
    assert f.severity == "info" and f.message == "10 of 12 pages used (references included)."


def test_not_counted_but_no_heading_counts_all_pages(tmp_path):
    f, = pdf.PAGE_LIMIT.run(ctx("acm", path=pdf_file(tmp_path, 10)))
    assert f.severity == "warning"
    assert f.message == ("10 pages count against the 9-page limit of ACM (sigconf) "
                         "(references not counted, but no References heading found, so all pages are counted).")


def test_overfull_findings(tmp_path):
    found = pdf.OVERFULL.run(ctx(path=pdf_file(tmp_path, 1)))
    big = next(f for f in found if f.severity == "warning")
    assert (big.file, big.line, big.message) == ("sections/method.tex", 40, "Line is 12.3pt too wide (lines 40-42).")
    assert "\\resizebox" in big.fix_hint
    assert any(f.severity == "info" and f.message == "1 smaller overfull box(es) (under 5pt) not listed." for f in found)
    assert any(f.severity == "info" and f.message == "Line is badly stretched (lines 7-8)." for f in found)
    assert all(f.check == "pdf.overfull_boxes" for f in found)


def test_single_line_wording(tmp_path):
    log = "(main.tex\nOverfull \\hbox (9.0pt too wide) in paragraph at lines 5--5\n[]x\n\n)\n"
    f, = pdf.OVERFULL.run(ctx(log=log, path=pdf_file(tmp_path, 1)))
    assert f.message == "Line is 9pt too wide (line 5)."


def test_underfull_cap(tmp_path):
    log = "(main.tex\n" + "".join(
        f"Underfull \\hbox (badness 10000) in paragraph at lines {i}--{i}\n[]x\n\n" for i in range(1, 16)) + ")\n"
    found = pdf.OVERFULL.run(ctx(log=log, path=pdf_file(tmp_path, 1)))
    assert sum(f.message.startswith("Line is badly") for f in found) == 10
    assert any(f.message == "5 more badly stretched lines not listed." for f in found)


def test_overfull_never_enters_compile_errors():  # regression pin: green before this task, stays green
    assert latex_compile.parse_errors(LOG) == []


def test_unresolved_refs(tmp_path):
    found = pdf.UNRESOLVED.run(ctx(path=pdf_file(tmp_path, 3, extra={2: "see Figure ?? and Table ??", 3: "[?]"})))
    assert [(f.severity, f.file, f.line, f.message) for f in found] == [
        ("warning", None, None, "Page 2 shows 2 unresolved reference or citation mark(s) (?? or [?])."),
        ("warning", None, None, "Page 3 shows 1 unresolved reference or citation mark(s) (?? or [?])."),
    ]
    assert pdf.UNRESOLVED.run(ctx(path=pdf_file(tmp_path, 2))) == []


def test_check_objects():
    assert [(c.name, c.cost) for c in pdf.CHECKS] == [
        ("pdf.page_limit", "full"), ("pdf.overfull_boxes", "full"), ("pdf.unresolved_refs", "full")]
    assert all(c.description for c in pdf.CHECKS)
