import asyncio
import base64
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from conftest import FakeEmbedder, parse_sse, unit_vector
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from sqlalchemy import delete, func, select, update

from app.core import (
    chat,
    chunking,
    claims,
    evidence_cards,
    library,
    notes,
    papers,
    retrieval,
    screening,
    tags,
    workspaces,
)
from app.core.errors import Conflict, InvalidInput
from app.models import Chunk, EvidenceCard, LLMOutput, Paper
from app.providers import embedding
from app.workers import ingest

pytestmark = pytest.mark.anyio


async def _chunked_paper(session, file_path: str | None) -> Paper:
    paper = Paper(title="Abstract only", abstract="An abstract.", file_path=file_path, status="ready")
    session.add(paper)
    await session.flush()
    session.add(
        Chunk(paper_id=paper.id, ordinal=0, page=0, bbox=[], text="An abstract.", embed_model="t", strategy_ver=1)
    )
    await session.commit()
    await session.refresh(paper)
    return paper


async def pdf_less_paper(session, title: str = "No PDF", abstract: str = "An abstract.", **fields) -> Paper:
    """A paper saved without a file, with its abstract as the page-0 chunk (Task 4 makes these for real)."""
    paper = Paper(title=title, abstract=abstract, file_path=None, **fields)
    session.add(paper)
    await session.flush()
    session.add(
        Chunk(
            paper_id=paper.id, ordinal=0, page=0, bbox=[], section_title="Abstract", text=f"{title}. {abstract}",
            embed_model="test", strategy_ver=chunking.STRATEGY_VERSION,
        )
    )  # fmt: skip
    await session.commit()
    await session.refresh(paper)
    return paper


async def chunk_count(session, paper_id) -> int:
    return await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == paper_id))


async def test_a_paper_without_a_pdf_with_a_chunked_abstract_reports_abstract(session):
    bare = await _chunked_paper(session, None)
    assert (bare.has_pdf, bare.evidence_access) == (False, "abstract")
    filed = await _chunked_paper(session, "/x.pdf")
    assert (filed.has_pdf, filed.evidence_access) == (True, "full_text")


async def test_paper_out_carries_has_pdf_and_details_source(client, session):
    paper = Paper(title="No file", file_path=None, details_source="crossref")
    session.add(paper)
    await session.commit()
    await session.refresh(paper)  # loads the column properties the response reads
    body = (await client.get(f"/api/papers/{paper.id}")).json()
    assert (body["has_pdf"], body["details_source"], body["evidence_access"]) == (False, "crossref", "metadata")


async def test_details_source_only_stores_known_sources(session):
    from sqlalchemy.exc import IntegrityError

    session.add(Paper(title="Bad", file_path=None, details_source="the-moon"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_the_tags_full_text_filter_skips_papers_without_a_pdf(session):
    ws = (await workspaces.create(session, f"nopdf-{uuid.uuid4().hex[:6]}")).id
    bare = await _chunked_paper(session, None)
    filed = await _chunked_paper(session, "/x.pdf")
    for p in (bare, filed):
        await workspaces.add_paper(session, ws, p.id)
    await tags.tag_papers(session, ws, "t", paper_ids=[bare.id, filed.id])
    (row,) = await tags.summaries(session, ws)
    assert (row.full_text, row.abstract) == (1, 1)


async def test_file_of_a_paper_without_a_pdf_is_404_no_pdf(client, session):
    paper = await pdf_less_paper(session)
    response = await client.get(f"/api/papers/{paper.id}/file")
    assert (response.status_code, response.json()["detail"]) == (404, "no_pdf")


async def test_deleting_a_paper_without_a_pdf_is_204(client, session):
    paper = await pdf_less_paper(session)
    assert (await client.delete(f"/api/papers/{paper.id}")).status_code == 204
    assert await chunk_count(session, paper.id) == 0
    assert (await client.get(f"/api/papers/{paper.id}")).status_code == 404


async def test_export_for_zotero_skips_only_the_missing_file(client, session, tmp_path):
    ws = (await client.post("/api/workspaces", json={"name": f"Zotero {uuid.uuid4().hex[:6]}"})).json()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    filed = Paper(title="Has a file", file_path=str(pdf), year=2020, authors=["Jane Smith"])
    session.add(filed)
    await session.commit()
    bare = await pdf_less_paper(session, title="Has no file")
    for p in (filed, bare):
        await client.put(f"/api/workspaces/{ws['id']}/papers/{p.id}")
    response = await client.get(f"/api/workspaces/{ws['id']}/citations.zip", params={"format": "bibtex"})
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert sorted(n.rsplit("/", 1)[-1] for n in names if n.startswith("files/")) == ["smith2020has.pdf"]
    refs = zipfile.ZipFile(io.BytesIO(response.content)).read("PaperLab export.bib").decode()
    assert "Has no file" in refs  # still listed in the references, just without an attachment


async def test_ingest_and_rechunk_leave_a_paper_without_a_pdf_alone(worker_session, ctx):
    paper = await pdf_less_paper(worker_session, status="ready")
    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)
    assert (paper.status, paper.status_error, await chunk_count(worker_session, paper.id)) == ("ready", None, 1)


async def test_reingest_refuses_no_pdf(client, session, arq):
    paper = await pdf_less_paper(session, status="ready")
    response = await client.post(f"/api/papers/{paper.id}/reingest")
    assert (response.status_code, response.json()["detail"]) == (409, "no_pdf")
    await session.refresh(paper)
    assert (paper.status, arq.jobs) == ("ready", [])  # not flipped to uploaded, nothing queued


async def test_evidence_card_needs_the_full_text(client, session, jobs):
    paper = await pdf_less_paper(session, status="ready")
    response = await client.post(f"/api/papers/{paper.id}/evidence-card")
    assert (response.status_code, response.json()["detail"]) == (422, "needs_full_text")
    assert jobs.jobs == [] and not await session.scalar(select(EvidenceCard).where(EvidenceCard.paper_id == paper.id))
    with pytest.raises(InvalidInput, match="needs_full_text"):
        await evidence_cards.request_cards(session, paper_ids=[paper.id])
    built = await evidence_cards.build_card(session, paper.id)  # the worker path never asks the model either
    assert (built.status, built.error) == ("failed", "needs_full_text")


async def test_generating_missing_cards_skips_papers_without_a_pdf(client, session, jobs, tmp_path):
    ws = (await client.post("/api/workspaces", json={"name": f"Cards {uuid.uuid4().hex[:6]}"})).json()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    filed = Paper(title="Has a file", file_path=str(pdf), status="ready")
    session.add(filed)
    await session.commit()
    bare = await pdf_less_paper(session, status="ready")
    for p in (filed, bare):
        await client.put(f"/api/workspaces/{ws['id']}/papers/{p.id}")
    response = await client.post(f"/api/workspaces/{ws['id']}/evidence-cards")
    assert response.status_code == 202
    assert {r["paper_id"]: r["error"] for r in response.json()}[str(bare.id)] == "needs_full_text"
    assert jobs.jobs == [("generate_evidence_cards", ws["id"], [str(filed.id)])]


async def test_upload_by_doi_onto_a_paper_without_a_pdf_does_not_crash(session, jobs, pdf_dir):
    doi = "10.1234/nopdf"
    paper = await pdf_less_paper(session, doi=doi, status="failed")
    ws = f"NoPdf {uuid.uuid4().hex[:6]}"
    await workspaces.create(session, ws)
    pdf = base64.b64encode(b"%PDF-1.7\n%x\n").decode()
    added = result(await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=pdf, doi=doi))
    assert (added["status"], added["paper_id"]) == ("already_in_library", str(paper.id))
    await session.refresh(paper)
    assert (paper.file_path, jobs.jobs) == (None, [])


async def test_quoting_a_paper_without_a_pdf_saves_an_unanchored_note_led_by_the_quote(session):
    paper = await pdf_less_paper(session, abstract="Sleep helps memory\nconsolidation in adults.")
    note = await notes.create_llm_note(session, paper.id, "Worth citing.", "sleep helps  memory consolidation")
    assert (note.body, note.anchors, note.paper_ids) == (
        "“sleep helps memory consolidation”\n\nWorth citing.",
        [],
        [paper.id],
    )
    with pytest.raises(InvalidInput, match="quote_not_found"):
        await notes.create_llm_note(session, paper.id, "Worth citing.", "Naps help too.")


async def test_locating_a_quote_on_a_paper_without_a_pdf_still_refuses_no_pdf(session):
    """create_ai_note keeps the note and drops the anchor on this Conflict; an abstract has no spot to anchor on."""
    paper = await pdf_less_paper(session, abstract="Sleep helps memory consolidation.")
    with pytest.raises(Conflict, match="no_pdf"):
        await notes.locate_quote(session, paper.id, "Sleep helps memory consolidation.")


async def test_mcp_create_note_on_a_paper_without_a_pdf_quotes_its_abstract(session):
    paper = await pdf_less_paper(session, abstract="Sleep helps memory consolidation.")
    made = result(await call("create_note", body="AI note.", paper_id=str(paper.id), quoted_text="Sleep helps memory"))
    assert (made["body"], made["anchors"], made["paper_ids"]) == (
        "“Sleep helps memory”\n\nAI note.",
        [],
        [str(paper.id)],
    )
    assert made["provenance"] == "llm"


async def test_a_note_on_the_abstract_is_saved_unanchored_with_its_quote_first(client, session):
    paper = await pdf_less_paper(session, abstract="Sleep helps memory consolidation in adults.")
    quoted = await client.post(
        "/api/notes", json={"paper_id": str(paper.id), "quote": "memory consolidation", "body": " Key claim. "}
    )
    plain = await client.post("/api/notes", json={"paper_id": str(paper.id), "body": "Read later."})
    assert quoted.status_code == 201, quoted.text
    body = quoted.json()
    assert (body["body"], body["anchors"], body["paper_ids"]) == (
        "“memory consolidation”\n\nKey claim.",
        [],
        [str(paper.id)],
    )
    assert body["provenance"] == "human"
    assert plain.status_code == 201 and plain.json()["body"] == "Read later."
    listed = (await client.get(f"/api/papers/{paper.id}/notes")).json()
    assert {n["body"] for n in listed} == {"“memory consolidation”\n\nKey claim.", "Read later."}


async def test_a_quote_not_in_the_abstract_is_422_quote_not_found(client, session):
    paper = await pdf_less_paper(session, abstract="Sleep helps memory consolidation.")
    answer = await client.post("/api/notes", json={"paper_id": str(paper.id), "quote": "Naps help.", "body": "x"})
    assert (answer.status_code, answer.json()["detail"]) == (422, "quote_not_found")


async def test_a_paper_note_without_an_anchor_on_a_paper_with_a_pdf_is_422_anchor_required(client, session):
    paper = await _chunked_paper(session, "/x.pdf")
    answer = await client.post("/api/notes", json={"paper_id": str(paper.id), "body": "x"})
    assert (answer.status_code, answer.json()["detail"]) == (422, "anchor_required")


async def test_a_failed_paper_without_a_pdf_re_added_by_identifier_is_left_alone(session, jobs):
    from app.core import pipeline

    paper = await pdf_less_paper(session, status="failed")
    added = await pipeline._in_library(session, paper.id, None)
    await session.refresh(paper)
    assert (paper.status, jobs.jobs, added.paper_id) == ("failed", [], paper.id)


async def test_the_max_tries_branch_does_not_touch_a_paper_without_a_pdf(worker_session, ctx):
    paper = await pdf_less_paper(worker_session, status="ready")
    await ingest.ingest_paper({**ctx, "job_try": ingest.MAX_TRIES}, str(paper.id))
    await worker_session.refresh(paper)
    assert (paper.status, paper.status_error) == ("ready", None)


ABSTRACT = "Sleep helps memory consolidation in adults."
PREFILL = {"title": "Sleep and memory", "abstract": ABSTRACT, "authors": ["Ada Quillfeather"], "year": 2020}
QUESTION = "does sleep help memory?"
PAGE_0 = re.compile(r"\b(p\.?|page)\s?=?\s?0\b")  # p.0, p 0, page 0, ?page=0


async def indexed_abstract_paper(session, ctx) -> tuple[Paper, Chunk]:
    """A paper saved without a PDF, its abstract chunk embedded by index_abstract, as Save without PDF leaves it."""
    paper = await papers.create_metadata_paper(session, PREFILL, "crossref")
    await ingest.index_abstract(ctx, str(paper.id))
    await session.refresh(paper)
    (chunk,) = await papers.list_chunks(session, paper.id)
    return paper, chunk


async def test_create_metadata_paper_writes_one_abstract_chunk_and_no_file(session):
    paper = await papers.create_metadata_paper(session, PREFILL, "crossref")
    (chunk,) = await papers.list_chunks(session, paper.id)
    assert (paper.file_path, paper.status, paper.details_source) == (None, "embedding", "crossref")
    assert (chunk.ordinal, chunk.page, chunk.bbox, chunk.section_title) == (0, papers.ABSTRACT_PAGE, [], "Abstract")
    assert chunk.text == f"Sleep and memory. {ABSTRACT}" == papers.abstract_chunk_text("Sleep and memory", ABSTRACT)
    bare = await papers.create_metadata_paper(session, {"title": "Bare", "abstract": "  "}, "manual")
    assert (bare.status, bare.has_pdf, bare.abstract, await chunk_count(session, bare.id)) == ("ready", False, None, 0)
    assert bare.evidence_access == "metadata"


async def test_create_metadata_paper_refuses_what_it_cannot_store(session):
    with pytest.raises(InvalidInput, match="unknown_details_source"):
        await papers.create_metadata_paper(session, {"title": "Moon"}, "the-moon")
    for title in (None, "", "   "):
        with pytest.raises(InvalidInput, match="empty_title"):
            await papers.create_metadata_paper(session, {"title": title, "abstract": ABSTRACT}, "manual")
    for key in ("file_path", "status", "details_source", "id"):
        with pytest.raises(InvalidInput, match="reserved_field") as refused:
            await papers.create_metadata_paper(session, {**PREFILL, key: None}, "manual")
        assert refused.value.details == {"fields": [key]}


async def test_index_abstract_embeds_and_marks_ready(worker_session, ctx, embedder):
    paper, chunk = await indexed_abstract_paper(worker_session, ctx)
    assert (paper.status, chunk.embed_model, chunk.embedding is not None) == ("ready", "test", True)
    assert [texts for texts, _ in embedder.calls] == [[f"search_document: {chunk.text}"]]
    assert paper.evidence_access == "abstract"


async def test_index_abstract_marks_ready_even_when_embedding_fails(worker_session):
    for ctx in ({"embedder": FakeEmbedder(refuse="The key was revoked.")}, {"embedder": None}):  # failing, none
        paper, chunk = await indexed_abstract_paper(worker_session, ctx)
        assert (paper.status, paper.status_error, chunk.embedding) == ("ready", None, None)


class Breaks(FakeEmbedder):
    """A source that fails in a way _embed doesn't catch: a bug (RuntimeError), or arq's cancel at job_timeout."""

    def __init__(self, error: BaseException):
        super().__init__()
        self.error = error

    async def encode(self, texts):
        raise self.error


async def test_index_abstract_marks_ready_after_an_unexpected_error(worker_session):
    paper, chunk = await indexed_abstract_paper(worker_session, {"embedder": Breaks(RuntimeError("a bug"))})
    assert (paper.status, chunk.embedding) == ("ready", None)


async def test_index_abstract_marks_ready_when_cancelled_and_still_cancels(worker_session):
    paper = await papers.create_metadata_paper(worker_session, PREFILL, "crossref")
    with pytest.raises(asyncio.CancelledError):
        await ingest.index_abstract({"embedder": Breaks(asyncio.CancelledError())}, str(paper.id))
    await worker_session.refresh(paper)
    assert paper.status == "ready"


async def test_index_abstract_leaves_a_paper_gone_or_with_a_pdf_alone(worker_session, ctx, embedder):
    filed = Paper(title="Has a file", file_path="/x.pdf", status="uploaded")
    worker_session.add(filed)
    await worker_session.commit()
    await ingest.index_abstract(ctx, str(filed.id))
    await ingest.index_abstract(ctx, str(uuid.uuid4()))
    await worker_session.refresh(filed)
    assert (filed.status, embedder.calls) == ("uploaded", [])


async def test_library_search_and_chat_retrieval_find_a_paper_by_its_abstract(worker_session, ctx, embedder):
    session = worker_session
    await session.execute(delete(Chunk))  # the dev database's chunks, on another model (see test_library)
    paper, chunk = await indexed_abstract_paper(session, ctx)
    embedder.vectors[f"search_query: {QUESTION}"] = unit_vector(f"search_document: {chunk.text}")
    (found,) = await retrieval.retrieve(session, QUESTION, embedder=embedder)
    assert (found.id, found.from_abstract) == (chunk.id, True)
    (passage,) = await library.search(session, QUESTION, embedder=embedder)
    assert (passage.chunk_id, passage.from_abstract, passage.evidence_access) == (chunk.id, True, "abstract")
    assert passage.page is None  # an MCP client cites it as the abstract, never by page
    assert passage.text == f"(abstract only) {chunk.text}"


async def test_chat_context_names_the_abstract_not_page_0(session):
    paper = await papers.create_metadata_paper(session, PREFILL, "crossref")
    sources = await chat.chunk_sources(session, Chunk.paper_id == paper.id)
    context = chat.format_context(paper, sources)
    assert context == f"[C1] (Quillfeather 2020, abstract only)\nSleep and memory. {ABSTRACT}"
    assert not PAGE_0.search(context)


async def test_saving_an_answer_citing_an_abstract_makes_an_unanchored_linked_note(session):
    paper = await papers.create_metadata_paper(session, PREFILL, "crossref")
    (chunk,) = await papers.list_chunks(session, paper.id)
    ws = await workspaces.create(session, f"Abstract notes {uuid.uuid4().hex[:6]}")
    # A workspace answer: no paper of its own, so the note's paper can only come from the cited chunk.
    output = LLMOutput(
        workspace_id=ws.id, kind="chat", question="Why sleep?", model="fake", prompt_version=1,
        content="Sleep helps memory [C1].\n:::note\nSleep helps memory consolidation [C1].\n:::",
        source_chunks=[chunk.id],
    )  # fmt: skip
    session.add(output)
    await session.commit()
    saved = await notes.save_suggestion(session, output.id, 0)
    promoted = await notes.promote_llm_fragment(session, output.id, "Sleep helps memory", [chunk.id])
    assert [(n.paper_ids, n.anchors) for n in (saved, promoted)] == [([paper.id], [])] * 2


async def test_reembed_keeps_the_abstract_chunk_searchable(worker_session, ctx):
    paper, chunk = await indexed_abstract_paper(worker_session, ctx)
    await worker_session.execute(update(Chunk).where(Chunk.id == chunk.id).values(embedding=None))
    await ingest.reembed_paper(ctx, str(paper.id))
    (again,) = await papers.list_chunks(worker_session, paper.id)
    await worker_session.refresh(again)
    assert (again.id, again.page, again.embedding is not None) == (chunk.id, papers.ABSTRACT_PAGE, True)


def _page_0_leaks(value) -> list:
    """Every object in a response body with a page of 0 (page, quote_page, ...) that doesn't say from_abstract."""
    if isinstance(value, list):
        return [leak for item in value for leak in _page_0_leaks(item)]
    if not isinstance(value, dict):
        return []
    here = any(key.endswith("page") and v == 0 and v is not False for key, v in value.items())
    return ([value] if here and value.get("from_abstract") is not True else []) + _page_0_leaks(list(value.values()))


class SupportedByTheAbstract:
    model, connection_name = "fake:abstract", "Test"

    async def stream(self, system, prompt):
        yield json.dumps({"verdict": "supported", "passage": 1, "quote": "Sleep helps memory", "reason": "Says so."})


async def test_no_api_response_leaks_page_0(client, worker_session, ctx, embedder, fake_llm, monkeypatch):
    session = worker_session
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)  # the search source the API and MCP build
    llm = SupportedByTheAbstract()

    async def given(_session, _llm):
        return llm

    async def local_model(_session):
        return ("Test · model", True, "localhost")

    monkeypatch.setattr(claims, "_llm", given)
    monkeypatch.setattr(screening, "_default_model", local_model)
    paper, chunk = await indexed_abstract_paper(session, ctx)
    name = f"Abstract leaks {uuid.uuid4().hex[:6]}"
    ws = await workspaces.create(session, name)
    await workspaces.add_paper(session, ws.id, paper.id)
    pid, wid = paper.id, ws.id

    asked = await client.post(f"/api/papers/{pid}/chat", json={"question": "What helps memory?"})
    events = parse_sse(asked.text)
    output_id = events[-1][1]["output_id"]
    workspace_asked = await client.post(f"/api/workspaces/{wid}/chat", json={"question": "What helps memory?"})
    promoted = await client.post(
        "/api/notes/promote", json={"output_id": output_id, "body": "Fake answer", "chunk_ids": [str(chunk.id)]}
    )
    export = await client.get(f"/api/workspaces/{wid}/notes.zip")
    exported = zipfile.ZipFile(io.BytesIO(export.content))
    bodies = {
        "paper chat": [data for _, data in events],
        "workspace chat": [data for _, data in parse_sse(workspace_asked.text)],
        "paper answers": (await client.get(f"/api/papers/{pid}/chat")).json(),
        "workspace answers": (await client.get(f"/api/workspaces/{wid}/chat")).json(),
        "promoted note": promoted.json(),
        "paper notes": (await client.get(f"/api/papers/{pid}/notes")).json(),
        "notes export": [exported.read(n).decode() for n in exported.namelist()],
        "chunks": (await client.get(f"/api/papers/{pid}/chunks")).json(),
        "note suggestions": (await client.post(f"/api/papers/{pid}/notes/suggest")).json(),
        "evidence card": (await client.post(f"/api/papers/{pid}/evidence-card")).json(),
        "search_library": result(await call("search_library", query=QUESTION, workspace=name)),
        "get_paper": result(await call("get_paper", paper_id=str(pid))),
        "verify_claim": result(await call("verify_claim", claim="Sleep helps memory.", paper_id=str(pid))),
        "verify_claims": result(
            await call("verify_claims", text="Sleep helps memory (Quillfeather, 2020).", workspace=name)
        ),
    }
    assert all(PAGE_0.search(s) for s in ("p.0", "p. 0", "page 0", "paperlab://papers/x?page=0&chunk=y"))
    for where, body in bodies.items():
        assert not PAGE_0.search(json.dumps(body)), where
        assert _page_0_leaks(body) == [], where

    assert [s["from_abstract"] for s in events[0][1]["sources"]] == [True]
    assert bodies["promoted note"]["anchors"] == [] and bodies["promoted note"]["paper_ids"] == [str(pid)]
    assert [c["from_abstract"] for c in bodies["chunks"]] == [True]
    assert bodies["note suggestions"]["detail"] == "no_pdf"
    assert bodies["evidence card"]["detail"] == "needs_full_text"
    assert [(p["page"], p["from_abstract"]) for p in bodies["search_library"]] == [(None, True)]
    assert bodies["get_paper"]["sections"] == []
    assert (bodies["verify_claim"]["evidence_level"], bodies["verify_claim"]["quote_page"]) == ("abstract_only", None)
    (item,) = bodies["verify_claims"]
    assert item["check"]["evidence_level"] == "abstract_only", item


async def _chunk_texts(session, paper_id) -> list[str]:
    return list(await session.scalars(select(Chunk.text).where(Chunk.paper_id == paper_id)))


async def _saved(session, **fields) -> Paper:
    return await papers.create_metadata_paper(session, {"title": "Saved Paper", **fields}, "manual")


async def test_editing_a_pdfless_papers_abstract_rebuilds_its_chunk_and_queues_indexing(client, session, arq):
    paper = await _saved(session)  # no abstract: ready, no chunk
    assert await _chunk_texts(session, paper.id) == []

    added = await client.patch(f"/api/papers/{paper.id}", json={"abstract": "First words."})
    changed = await client.patch(f"/api/papers/{paper.id}", json={"abstract": "Second words.", "title": "New Title"})

    assert (added.status_code, changed.status_code) == (200, 200)
    assert changed.json()["status"] == "embedding"
    assert await _chunk_texts(session, paper.id) == ["New Title. Second words."]
    assert arq.jobs == [("index_abstract", str(paper.id))] * 2


async def test_clearing_a_pdfless_papers_abstract_deletes_its_chunk_and_queues_nothing(client, session, arq):
    paper = await _saved(session, abstract="Some words.")
    assert await _chunk_texts(session, paper.id) == ["Saved Paper. Some words."]

    response = await client.patch(f"/api/papers/{paper.id}", json={"abstract": None})

    assert (response.status_code, response.json()["status"]) == (200, "ready")
    assert await _chunk_texts(session, paper.id) == []
    assert arq.jobs == []


async def test_editing_other_fields_of_a_pdfless_paper_leaves_its_chunk_alone(client, session, arq):
    paper = await _saved(session, abstract="Some words.")

    response = await client.patch(f"/api/papers/{paper.id}", json={"year": 2020})

    assert response.json()["status"] == "embedding"  # untouched: still waiting for the job create queued
    assert await _chunk_texts(session, paper.id) == ["Saved Paper. Some words."]
    assert arq.jobs == []


async def test_editing_a_paper_with_a_pdf_never_touches_its_chunks(client, session, arq):
    paper = await _chunked_paper(session, "/some.pdf")

    response = await client.patch(f"/api/papers/{paper.id}", json={"abstract": "Changed.", "title": "Other"})

    assert (response.status_code, response.json()["status"]) == (200, "ready")
    assert await _chunk_texts(session, paper.id) == ["An abstract."]
    assert arq.jobs == []


async def test_a_failed_index_abstract_enqueue_on_edit_leaves_the_paper_ready(client, session, arq, monkeypatch):
    pid = (await _saved(session)).id

    async def down(*_a, **_k):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(arq, "enqueue_job", down)
    with pytest.raises(ConnectionError):
        await client.patch(f"/api/papers/{pid}", json={"abstract": "Added by hand."})

    session.expire_all()
    assert (await session.get(Paper, pid)).status == "ready"  # never stuck at embedding


async def test_uploading_onto_a_hit_never_asks_for_its_other_version(session, monkeypatch):
    """upload_hit_pdf only needs a holder found by identifier; held_version can write a DOI onto an arXiv copy."""
    from app.core import discovery, workspace_search
    from app.models import Workspace
    from app.models.references import ExternalRef
    from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

    async def never(*_a, **_k):
        raise AssertionError("upload_hit_pdf asked for the other version")

    monkeypatch.setattr(discovery, "held_version", never)
    workspace = Workspace(name=f"Upload {uuid.uuid4().hex[:8]}")
    ref = ExternalRef(title="Upload Probe Paper", pdf_urls=[])
    session.add_all([workspace, ref])
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="q", filters_json={}, query_overrides_json={}, sources_json=[],
        status="exhausted", started_at=datetime.now(timezone.utc), stats_json={},
    )  # fmt: skip
    session.add(run)
    await session.flush()
    hit = WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id, source_method="database_search",
        normalized_title="upload probe paper", stage1_status="relevant", first_seen_at=datetime.now(timezone.utc),
    )  # fmt: skip
    session.add(hit)
    await session.commit()

    _, created = await workspace_search.upload_hit_pdf(session, workspace.id, hit.id, "p.pdf", b"%PDF-1.4 probe")

    assert created
