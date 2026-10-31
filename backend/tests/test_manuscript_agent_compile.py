from datetime import datetime, timedelta, timezone

import pymupdf
import pytest

from app.core import manuscript_agent_compile as mc
from app.core import manuscripts, queue
from app.core.errors import InvalidInput, NotFound
from app.core.latex_compile import CompileResult
from app.workers import manuscripts as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


@pytest.fixture(autouse=True)
def wiring(session, arq, pdf_dir, monkeypatch):
    monkeypatch.setattr(queue, "_pool", arq)


async def new(session):
    return (await manuscripts.create(session, title="M", template="article", workspace_id=None)).id


async def put(session, mid, **cols):
    m = await manuscripts.get(session, mid)
    for k, v in cols.items():
        setattr(m, k, v)
    await session.flush()


def make_pdf(mid, pages):
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    path = manuscripts.pdf_path(mid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(doc.tobytes())


async def code(coro, kind):
    with pytest.raises(kind) as info:
        await coro
    return str(info.value)


# --- compile_manuscript ---------------------------------------------------------------------------------------


async def test_compile_queues_once_then_asks_again(session, arq):
    mid = await new(session)
    first = await mc.compile_manuscript(session, mid)
    assert (first.state, first.status) == ("queued", "running") and first.started_at is not None
    assert arq.jobs == [("compile_manuscript", str(mid))]
    again = await mc.compile_manuscript(session, mid)
    assert (again.state, again.status) == ("again", "running") and len(arq.jobs) == 1
    assert (await mc.get_compile_result(session, mid)).again is True


async def test_compile_requeues_a_stale_running(session, arq):
    mid = await new(session)
    await put(
        session,
        mid,
        compile_status="running",
        compile_started_at=datetime.now(timezone.utc) - manuscripts.STALE_AFTER - timedelta(seconds=5),
    )
    assert (await mc.compile_manuscript(session, mid)).state == "queued" and len(arq.jobs) == 1


async def test_compile_unknown_manuscript(session):
    import uuid

    assert await code(mc.compile_manuscript(session, uuid.uuid4()), NotFound) == "unknown_manuscript"


async def test_compile_enqueue_failure_marks_failed(session, monkeypatch):
    class Boom:
        async def enqueue_job(self, *a, **k):
            raise RuntimeError("redis down")

    monkeypatch.setattr(queue, "_pool", Boom())
    mid = await new(session)
    with pytest.raises(RuntimeError):
        await mc.compile_manuscript(session, mid)
    assert (await mc.get_compile_result(session, mid)).status == "failed"


# --- get_compile_result ---------------------------------------------------------------------------------------


async def test_result_never_and_running(session):
    mid = await new(session)
    view = await mc.get_compile_result(session, mid)
    assert (view.status, view.finished, view.again, view.errors, view.log_tail) == ("never", False, False, [], None)
    assert view.pdf == mc.PdfInfo(available=False, page_count=None, from_latest_compile=False)
    await put(session, mid, compile_status="running", compile_started_at=datetime.now(timezone.utc))
    assert (await mc.get_compile_result(session, mid)).finished is False


async def test_result_ok_has_a_pdf(session):
    mid = await new(session)
    make_pdf(mid, ["a", "b"])
    await put(session, mid, compile_status="ok", compile_log="log", compiled_at=datetime.now(timezone.utc))
    view = await mc.get_compile_result(session, mid)
    assert (view.finished, view.errors, view.errors_total, view.log_tail) == (True, [], 0, None)
    assert view.pdf == mc.PdfInfo(available=True, page_count=2, from_latest_compile=True)
    assert (await mc.get_compile_result(session, mid, include_log=True)).log_tail == "log"


async def test_result_failed_keeps_errors_and_friendly(session):
    mid = await new(session)
    errs = [
        {"file": "ch/a.tex", "line": 7, "message": "File `x.sty' not found", "kind": "package_missing"},
        {"file": "main.tex", "line": None, "message": "w", "kind": "warning"},
    ]
    await put(
        session,
        mid,
        compile_status="failed",
        compile_errors=errs,
        compile_friendly="package_missing",
        compile_log="x" * 5000,
    )
    view = await mc.get_compile_result(session, mid)
    assert [e.__dict__ for e in view.errors] == errs and view.friendly == "package_missing"
    assert view.finished and len(view.log_tail) == 3000


async def test_result_caps_errors_at_50(session):
    mid = await new(session)
    errs = [{"file": "main.tex", "line": i, "message": "m", "kind": "error"} for i in range(60)]
    await put(session, mid, compile_status="failed", compile_errors=errs)
    view = await mc.get_compile_result(session, mid)
    assert (len(view.errors), view.errors_total) == (50, 60)


async def test_result_stale_running_is_interrupted(session):
    mid = await new(session)
    await put(
        session,
        mid,
        compile_status="running",
        compile_requested=True,
        compile_started_at=datetime.now(timezone.utc) - manuscripts.STALE_AFTER - timedelta(seconds=5),
    )
    view = await mc.get_compile_result(session, mid)
    assert (view.status, view.friendly, view.again, view.finished) == ("failed", "compile_interrupted", False, True)


async def test_failed_compile_over_an_older_pdf_is_not_latest(session):
    mid = await new(session)
    make_pdf(mid, ["old"])
    await put(session, mid, compile_status="failed")
    assert (await mc.get_compile_result(session, mid)).pdf == mc.PdfInfo(True, 1, False)
    assert (await mc.read_pdf_text(session, mid)).from_latest_compile is False


async def test_worker_round_trip(session, monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def shared():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared)

    async def compile_dir(workdir, main_file, **kw):
        return CompileResult(ok=True, pdf=b"%PDF-1.4 fake", log="fine", errors=[], friendly=None)

    monkeypatch.setattr(worker, "compile_dir", compile_dir)
    mid = await new(session)
    await mc.compile_manuscript(session, mid)
    await worker.compile_manuscript({}, str(mid))
    view = await mc.get_compile_result(session, mid)
    assert (view.status, view.finished) == ("ok", True) and view.pdf.available


# --- read_pdf_text --------------------------------------------------------------------------------------------


async def test_read_pdf_text_pages_and_ranges(session):
    mid = await new(session)
    make_pdf(mid, ["alpha", "beta", "gamma"])
    await put(session, mid, compile_status="ok")
    full = await mc.read_pdf_text(session, mid)
    assert (full.page_count, full.first_page, full.last_page, full.truncated, full.next_page) == (3, 1, 3, False, None)
    assert [p.page for p in full.pages] == [1, 2, 3] and "beta" in full.pages[1].text and full.from_latest_compile
    part = await mc.read_pdf_text(session, mid, 2, 2)
    assert [p.page for p in part.pages] == [2]


@pytest.mark.parametrize(("first", "last"), [(0, None), (3, 2), (4, None), (1, 4)])
async def test_read_pdf_text_bad_range(session, first, last):
    mid = await new(session)
    make_pdf(mid, ["a", "b", "c"])
    got = await code(mc.read_pdf_text(session, mid, first, last), InvalidInput)
    assert got == "bad_page_range"


async def test_read_pdf_text_cap_stops_before_a_page(session):
    mid = await new(session)
    make_pdf(mid, ["a", "b", "c"])
    old = mc.MAX_CHARS
    try:
        mc.MAX_CHARS = 3  # each page's text is "x\n" (2 chars)
        first = await mc.read_pdf_text(session, mid)
        assert [p.page for p in first.pages] == [1] and first.next_page == 2 and not first.truncated
        second = await mc.read_pdf_text(session, mid, first.next_page)
        assert [p.page for p in second.pages] == [2] and second.next_page == 3
    finally:
        mc.MAX_CHARS = old


async def test_read_pdf_text_one_page_over_the_cap_is_cut(session):
    mid = await new(session)
    make_pdf(mid, ["word " * 50, "b"])
    old = mc.MAX_CHARS
    try:
        mc.MAX_CHARS = 20
        got = await mc.read_pdf_text(session, mid)
        assert got.truncated and len(got.pages[0].text) == 20 and got.next_page == 2
    finally:
        mc.MAX_CHARS = old


async def test_read_pdf_text_real_cap_continues(session):
    mid = await new(session)
    big = "\n".join("w" * 60 for _ in range(14))  # ~850 chars/page is under cap; pad via many pages
    make_pdf(mid, [big] * 60)
    first = await mc.read_pdf_text(session, mid)
    assert first.next_page is not None and sum(len(p.text) for p in first.pages) <= 40_000
    nxt = await mc.read_pdf_text(session, mid, first.next_page)
    assert nxt.pages[0].page == first.next_page


async def test_read_pdf_text_no_pdf_and_corrupt(session):
    mid = await new(session)
    assert await code(mc.read_pdf_text(session, mid), NotFound) == "no_pdf"
    path = manuscripts.pdf_path(mid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a pdf")
    assert await code(mc.read_pdf_text(session, mid), InvalidInput) == "unreadable_pdf"
