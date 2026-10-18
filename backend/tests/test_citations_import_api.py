"""M40 Task 9a: importing a Zotero export over the API (preview, import inline or as a job, polling, body caps)."""

import asyncio
import io
import json
import pickle
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from dataclasses import asdict

import pytest
from arq.worker import JobExecutionFailed
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from app.api import citations as citations_api
from app.core import citations_import_apply as cia
from app.core import citations_import_run as run
from app.core import discovery, queue
from app.core.citations_bundle_read import read_bundle
from app.core.citations_import import ImportEntry
from app.models import Paper, Workspace
from app.schemas.citations_import import ImportResultOut, NeedsPdfOut
from app.workers import citations_import as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

RUN = uuid.uuid4().hex[:10]


def title(n: str) -> str:
    return f"Zr{RUN} {n} imported over the api"


def bib(*names: str, doi: bool = False) -> bytes:
    def one(n: str) -> str:
        extra = f", doi={{10.5555/m40t9.{RUN}.{n}}}" if doi else ""
        return (
            f"@article{{{n}, title={{{title(n)}}}, author={{Smith, Jane and Muller, Hans}}, year={{2021}},"
            f" journal={{Journal of Things}}, volume={{12}}, number={{3}}, pages={{45--67}},"
            f" keywords={{alpha, beta}}, abstract={{About {n}.}}{extra}}}\n"
        )

    return "".join(map(one, names)).encode()


class FakeJobRedis:
    """What arq's Job.status/result_info and the progress key read, plus enqueue_job (queue._pool)."""

    def __init__(self):
        self.values: dict[str, bytes] = {}
        self.queued: dict[str, float] = {}
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name, *args, _queue_name=None, _job_id=None):
        self.jobs.append((name, *args))
        self.queued[_job_id] = 1.0  # a score in the past: queued, not deferred
        return object()

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value.encode() if isinstance(value, str) else value

    @asynccontextmanager
    async def pipeline(self, transaction=True):
        yield _Pipeline(self)

    def start(self, job_id: str) -> None:
        self.queued.pop(job_id, None)
        self.values[f"arq:in-progress:{job_id}"] = b"1"

    def finish(self, job_id: str, result, success: bool = True) -> None:
        self.values.pop(f"arq:in-progress:{job_id}", None)
        self.values[f"arq:result:{job_id}"] = pickle.dumps({
            "t": 1, "f": cia.JOB, "a": (), "k": {}, "et": 0, "s": success, "r": result, "st": 0, "ft": 0,
            "q": "arq:queue", "id": job_id,
        })  # fmt: skip


class _Pipeline:
    def __init__(self, redis: FakeJobRedis):
        self.redis, self.calls = redis, []

    def exists(self, key):
        self.calls.append(int(key in self.redis.values))

    def zscore(self, _name, member):
        self.calls.append(self.redis.queued.get(member))

    async def execute(self):
        return self.calls


@pytest.fixture(autouse=True)
def redis(monkeypatch, app) -> FakeJobRedis:
    fake = FakeJobRedis()
    monkeypatch.setattr(queue, "_pool", fake)
    app.state.arq = fake
    return fake


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A fetch finds nothing and nothing reaches a paper source."""

    @asynccontextmanager
    async def open_providers(_session):
        yield None

    async def search(_session, _providers, _query):
        return discovery.SearchResult([], [])

    monkeypatch.setattr(discovery, "open_providers", open_providers)
    monkeypatch.setattr(discovery, "search", search)


async def post(client, path: str, data: bytes, name: str = "refs.bib", **form):
    fields = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in form.items()}
    return await client.post(path, files={"file": (name, data)}, data=fields)


async def paper_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Paper).where(Paper.title.contains(RUN)))


# ---- preview ----


async def test_preview_counts_and_says_what_a_fetch_contacts(client, session, monkeypatch):
    monkeypatch.setattr(discovery, "search", lambda *_: pytest.fail("a preview contacted a paper source"))
    data = bib("p1", "p2", doi=True) + bib("p3")

    response = await post(client, "/api/citations/import/preview", data)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total": 3, "already_in_library": 0, "with_bundled_pdf": 0, "would_fetch": 2,
        "cannot_import_without_fetch": 3,
        "disclosure": "Fetching contacts free-copy sources (Unpaywall, arXiv, …) for 2 entries, the same way adding a "
        "paper by DOI does.",
    }  # fmt: skip
    assert await paper_count(session) == 0


async def test_preview_with_fetch_off_has_no_disclosure_and_one_entry_reads_singular(client):
    off = await post(client, "/api/citations/import/preview", bib("p4", doi=True), fetch_free_pdfs=False)
    assert off.json()["would_fetch"] == 0 and off.json()["disclosure"] is None
    on = await post(client, "/api/citations/import/preview", bib("p5", doi=True))
    assert "for 1 entry, the same way" in on.json()["disclosure"]


async def test_preview_discloses_the_lookup_for_a_zip_pdf_that_cant_be_read(client):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:  # a bundled PDF and a DOI: a damaged PDF falls back to a free copy
        zf.writestr("Exported Items.bib", bib("p6", doi=True).decode().replace("}\n", ", file={files/1/p6.pdf}}\n"))
        zf.writestr("files/1/p6.pdf", b"%PDF-1.7 zipped")
    on = (await post(client, "/api/citations/import/preview", out.getvalue(), name="Exported Items.zip")).json()
    assert (on["with_bundled_pdf"], on["would_fetch"]) == (1, 0)
    assert on["disclosure"] == (
        "Fetching contacts free-copy sources (Unpaywall, arXiv, …) only for a PDF in the zip that can't be read, "
        "the same way adding a paper by DOI does."
    )
    off = await post(client, "/api/citations/import/preview", out.getvalue(), name="Exported Items.zip",
                     fetch_free_pdfs=False)  # fmt: skip
    assert off.json()["disclosure"] is None
    mixed = io.BytesIO()
    with zipfile.ZipFile(mixed, "w") as zf:
        zf.writestr("Exported Items.bib", bib("p7", doi=True).decode().replace("}\n", ", file={files/1/p7.pdf}}\n")
                    + bib("p8", doi=True).decode())  # fmt: skip
        zf.writestr("files/1/p7.pdf", b"%PDF-1.7 zipped")
    both = await post(client, "/api/citations/import/preview", mixed.getvalue(), name="Exported Items.zip")
    assert both.json()["disclosure"] == (
        "Fetching contacts free-copy sources (Unpaywall, arXiv, …) for 1 entry, and for a PDF in the zip that can't "
        "be read, the same way adding a paper by DOI does."
    )


async def test_preview_of_a_bad_file_is_a_plain_422(client):
    response = await post(client, "/api/citations/import/preview", b"not references at all", name="notes.txt")
    assert response.status_code == 422
    assert response.json() == {
        "detail": "PaperLab reads BibTeX (.bib), RIS (.ris) and CSL-JSON (.json) files from Zotero."
    }


# ---- import inline ----


async def test_a_small_import_runs_inline_and_lists_whole_entries_that_need_a_pdf(client, session, redis):
    response = await post(client, "/api/citations/import", bib("i1"), fetch_free_pdfs=False)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["state"], body["job_id"]) == ("finished", None)
    result = body["result"]
    assert (result["imported"], result["already_in_library"], result["failed"]) == (0, 0, [])
    assert result["needs_pdf"] == [{
        "title": title("i1"), "authors": ["Jane Smith", "Hans Muller"], "year": 2021, "venue": "Journal of Things",
        "doi": None, "arxiv_id": None, "pmid": None, "pmcid": None, "issn": None, "abstract": "About i1.",
        "volume": "12", "issue": "3", "pages": "45-67", "editors": [], "source_type": "journal_article",
        "tags": ["alpha", "beta"], "collection": None, "notes": [], "tried": [], "free_copies": [],
    }]  # fmt: skip
    assert redis.jobs == []


async def test_a_zip_with_its_pdf_imports_inline(client, session, redis):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("Exported Items.bib", bib("z1").decode().replace("}\n", ", file={files/1/z1.pdf}}\n"))
        zf.writestr("files/1/z1.pdf", b"%PDF-1.7 zipped")

    response = await post(client, "/api/citations/import", out.getvalue(), name="Exported Items.zip")

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert (result["imported"], result["pdfs_attached"], result["needs_pdf"]) == (1, 1, [])
    assert redis.jobs == [("ingest_paper", redis.jobs[0][1])]


async def test_a_new_workspace_is_made_and_filled(client, session):
    name = f"From Zotero {RUN}"
    response = await post(client, "/api/citations/import", bib("w1"), new_workspace_name=name)
    assert response.status_code == 200, response.text
    made = await session.scalar(select(Workspace).where(Workspace.name == name))
    assert made is not None and response.json()["workspace_id"] == str(made.id)


async def test_a_bad_file_creates_no_new_workspace(client, session):
    name = f"Never made {RUN}"
    response = await post(client, "/api/citations/import", b"@article{broken, title={", new_workspace_name=name)
    assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert await session.scalar(select(Workspace).where(Workspace.name == name)) is None


async def test_a_workspace_id_and_a_new_name_together_are_refused(client, session):
    name = f"Both {RUN}"
    response = await post(
        client, "/api/citations/import", bib("b1"), workspace_id=uuid.uuid4(), new_workspace_name=name
    )
    assert response.status_code == 422
    assert await session.scalar(select(Workspace).where(Workspace.name == name)) is None


async def test_an_unknown_workspace_is_404_before_anything(client, session):
    response = await post(client, "/api/citations/import", bib("u1"), workspace_id=uuid.uuid4())
    assert response.status_code == 404 and await paper_count(session) == 0


# ---- import as a job, and polling ----


async def test_a_fetching_import_is_a_job_polled_until_it_finishes(client, session, redis, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared_session)

    response = await post(client, "/api/citations/import", bib("j1", "j2", doi=True))

    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert response.json()["state"] == "queued" and job_id.startswith(f"{cia.JOB}:")
    [(name, *args)] = redis.jobs
    assert name == cia.JOB
    poll = f"/api/citations/import/{job_id}"
    assert (await client.get(poll)).json()["state"] == "queued"

    redis.start(job_id)
    await redis.set(cia.progress_key(job_id), json.dumps(cia.progress_payload(cia.ImportResult(), 2, False)))
    running = (await client.get(poll)).json()
    assert running["state"] == "running" and running["result"] is None
    assert (running["counts"]["total"], running["counts"]["done"]) == (2, 0)

    done = await worker.import_citations({"redis": redis, "job_id": job_id}, *args)
    redis.finish(job_id, done)
    finished = (await client.get(poll)).json()
    assert finished["state"] == "finished" and finished["message"] is None
    assert [n["title"] for n in finished["result"]["needs_pdf"]] == [title("j1"), title("j2")]
    assert finished["result"]["needs_pdf"][0]["tried"] == [
        {"url": f"https://doi.org/10.5555/m40t9.{RUN}.j1", "outcome": "no_match"}
    ]
    assert finished["result"]["needs_pdf"][0]["volume"] == "12"


async def test_a_finished_import_is_still_read_once_arq_forgets_the_job(client, redis):
    job_id = f"{cia.JOB}:{uuid.uuid4()}"
    payload = cia.progress_payload(cia.ImportResult(imported=3), 3, True)
    await redis.set(cia.progress_key(job_id), json.dumps(payload))
    body = (await client.get(f"/api/citations/import/{job_id}")).json()
    assert body["state"] == "finished" and body["result"]["imported"] == 3


@pytest.mark.parametrize("lost", [JobExecutionFailed("max 1 retries exceeded"), asyncio.CancelledError(),
                                  FileNotFoundError("gone")])  # fmt: skip
async def test_an_import_cut_short_by_a_restart_says_so(client, redis, lost):
    job_id = f"{cia.JOB}:{uuid.uuid4()}"
    redis.finish(job_id, lost, success=False)
    body = (await client.get(f"/api/citations/import/{job_id}")).json()
    assert body["state"] == "restarted" and body["message"] == run.RESTARTED
    assert body["message"] == (
        "PaperLab restarted during the import. Import the same file again; papers already imported are skipped."
    )


async def test_a_job_gone_with_its_progress_left_is_restarted(client, redis):
    job_id = f"{cia.JOB}:{uuid.uuid4()}"
    await redis.set(cia.progress_key(job_id), json.dumps(cia.progress_payload(cia.ImportResult(), 9, False)))
    assert (await client.get(f"/api/citations/import/{job_id}")).json()["state"] == "restarted"


async def test_a_job_that_raised_is_failed(client, redis):
    job_id = f"{cia.JOB}:{uuid.uuid4()}"
    redis.finish(job_id, RuntimeError("boom"), success=False)
    body = (await client.get(f"/api/citations/import/{job_id}")).json()
    assert body["state"] == "failed" and body["message"] == run.JOB_FAILED


async def test_an_unreadable_arq_result_is_failed_not_500(client, redis):
    job_id = f"{cia.JOB}:{uuid.uuid4()}"
    redis.values[f"arq:result:{job_id}"] = b"not a pickle"
    response = await client.get(f"/api/citations/import/{job_id}")
    assert response.status_code == 200 and response.json()["state"] == "failed"


@pytest.mark.parametrize("job_id", [f"{cia.JOB}:00000000-0000-4000-8000-000000000000", "nope", "ingest_paper:123"])
async def test_an_unknown_or_old_job_is_expired(client, job_id):
    response = await client.get(f"/api/citations/import/{job_id}")
    assert response.status_code == 200
    assert response.json()["state"] == "expired" and response.json()["message"] == run.EXPIRED


# ---- body caps ----


def multipart(chunks, name: str = "refs.bib", boundary: str = "b0undary"):
    """A multipart body streamed chunk by chunk, counting what was read."""
    sent = {"chunks": 0}

    async def body():
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        for chunk in chunks:
            sent["chunks"] += 1
            yield chunk
        yield f"\r\n--{boundary}--\r\n".encode()

    return body(), {"content-type": f"multipart/form-data; boundary={boundary}"}, sent


@pytest.mark.parametrize("path", ["/api/citations/import", "/api/citations/import/preview"])
async def test_a_body_over_the_cap_is_refused_as_it_streams_in(client, session, monkeypatch, path):
    monkeypatch.setattr(citations_api, "IMPORT_BODY_MAX", 10_000)
    body, headers, sent = multipart([b"%" * 1000] * 100)

    response = await client.post(path, content=body, headers=headers)

    assert response.status_code == 413
    assert response.json() == {"detail": run.UPLOAD_TOO_BIG}
    assert run.UPLOAD_TOO_BIG.startswith("This upload is larger than 200 MB")
    assert sent["chunks"] < 20  # stopped near the cap, not after all 100
    assert await paper_count(session) == 0


async def test_a_declared_length_over_the_cap_is_refused_before_reading(client, monkeypatch):
    monkeypatch.setattr(citations_api, "IMPORT_BODY_MAX", 10_000)
    body, headers, sent = multipart([b"%" * 1000] * 100)

    response = await client.post("/api/citations/import", content=body, headers=headers | {"content-length": "200000"})

    assert response.status_code == 413 and sent["chunks"] == 0


async def test_a_refs_file_over_its_own_cap_is_413_in_words(client, monkeypatch):
    monkeypatch.setattr(run, "FILE_MAX_BYTES", 100)
    response = await post(client, "/api/citations/import", bib("big"))
    assert response.status_code == 413
    assert response.json()["detail"] == run.too_big("refs.bib")
    assert response.json()["detail"].startswith("This file is larger than")


async def test_the_caps_are_20_mb_a_file_and_200_mb_a_zip():
    assert (run.cap("refs.bib"), run.cap("Library.ZIP")) == (20 * 1024 * 1024, 200 * 1024 * 1024)
    assert run.too_big("x.zip") == (
        "This zip is larger than 200 MB, which is more than PaperLab imports at once, so nothing was imported."
    )
    assert run.too_big("x.ris") == (
        "This file is larger than 20 MB, which is more than PaperLab imports at once, so nothing was imported."
    )


# ---- fix round 1: Redis down, a hard-killed worker, streaming, cleanup ----


@pytest.mark.parametrize("error", [RedisConnectionError("down"), OSError("no route")])
async def test_redis_down_is_unavailable_not_500(client, redis, monkeypatch, error):
    async def down(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(redis, "get", down)
    response = await client.get(f"/api/citations/import/{cia.JOB}:{uuid.uuid4()}")
    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert response.json()["message"] == (
        "PaperLab can't check this import right now. Try again in a moment; the import carries on."
    )


async def test_a_running_job_with_a_stale_heartbeat_is_restarted(client, redis, monkeypatch):
    job_id = f"{cia.JOB}:{uuid.uuid4()}"
    redis.start(job_id)
    stale = cia.progress_payload(cia.ImportResult(), 5, False) | {"at": time.time() - run.HEARTBEAT_STALE - 1}
    await redis.set(cia.progress_key(job_id), json.dumps(stale))
    body = (await client.get(f"/api/citations/import/{job_id}")).json()
    assert body["state"] == "restarted" and body["message"] == run.RESTARTED

    fresh = stale | {"at": time.time() - run.HEARTBEAT_STALE + 60}
    await redis.set(cia.progress_key(job_id), json.dumps(fresh))
    assert (await client.get(f"/api/citations/import/{job_id}")).json()["state"] == "running"


async def test_the_heartbeat_outlasts_an_entrys_worst_case():
    assert run.HEARTBEAT_STALE == 15 * 60


def zip_of(*names: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("Exported Items.bib", bib(*names, doi=True))
    return out.getvalue()


async def test_a_zip_is_read_from_the_upload_and_copied_for_the_job_once(client, session, redis, monkeypatch):
    reads = []

    def counted(source):
        assert not isinstance(source, bytes), "the zip was read whole into memory"
        reads.append(source)
        return read_bundle(source)

    monkeypatch.setattr(cia, "read_bundle", counted)
    data = zip_of("s1")
    name = f"Streamed {RUN}"

    response = await post(client, "/api/citations/import", data, name="Exported Items.zip", new_workspace_name=name)

    assert response.status_code == 202, response.text
    assert len(reads) == 1  # parsed once, even with a new workspace to make
    [(_, path, *_)] = redis.jobs
    assert open(path, "rb").read() == data


async def test_a_failed_enqueue_removes_the_workspace_it_made(client, session, redis, monkeypatch):
    async def broken(*_args, **_kwargs):
        raise RedisConnectionError("down")

    monkeypatch.setattr(redis, "enqueue_job", broken)
    name = f"Left empty {RUN}"

    response = await post(client, "/api/citations/import", bib("e1", doi=True), new_workspace_name=name)

    assert response.status_code == 503
    assert response.json()["detail"] == "PaperLab can't start a background import right now. Try again in a moment."
    assert await session.scalar(select(Workspace).where(Workspace.name == name)) is None


# ---- the needs-a-PDF record (the metadata-only papers work saves these as they are) ----


async def test_a_needs_pdf_item_keeps_every_field_of_its_entry_through_the_result(session):
    assert set(NeedsPdfOut.model_fields) == {*cia.ENTRY_RECORD, "tried", "free_copies"}
    entry = ImportEntry(
        title=title("whole"), authors=["A B"], year=2020, venue="V", doi=f"10.5555/m40b.{RUN}", arxiv_id="2001.00001",
        pmid="1", pmcid="PMC1", issn="1234-5678", abstract="Ab.", volume="1", issue="2", pages="3-4", editors=["E F"],
        source_type="journal", tags=["t"], collection="C", notes=["n"], files=["f.pdf"],
    )

    result = await cia.apply(session, [entry], fetch_free_pdfs=False)  # what the import itself builds

    record = {name: getattr(entry, name) for name in cia.ENTRY_RECORD}
    assert ImportResultOut(**asdict(result)).model_dump()["needs_pdf"] == [record | {"tried": [], "free_copies": []}]
    assert "files" not in record  # paths inside a zip mean nothing once the import is done
