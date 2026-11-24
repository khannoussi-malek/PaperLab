"""Notes a model wrote: a promoted answer fragment, a saved suggestion, and notes Claude or the local model place on
an exact quote."""

import asyncio
import uuid
from collections import Counter

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notes.notes import (
    Anchor,
    NoteView,
    Rect,
    _abstract_quote,
    _link,
    _quoted,
    _view,
    _with_anchors,
    fold,
    normalize_quote,
    note_blocks,
    parse_citations,
    queue_embed,
)
from app.core.papers.papers import get_paper, get_paper_file, list_chunks
from app.domain.constants import ABSTRACT_PAGE
from app.domain.errors import Conflict, InvalidInput, NotFound
from app.models import Chunk, LLMOutput, Note, Provenance, note_anchors
from app.providers.extraction import quote_rects

MCP_OUTPUT_KIND = "mcp"
QUOTE_NOT_FOUND_HINT = "Copy quoted_text exactly from one passage of this paper, as search_library returned it."
QUOTE_AMBIGUOUS_HINT = "This text appears more than once in the paper. Quote a longer stretch around it."


STALE_CHUNK = "a cited chunk no longer exists; the paper was re-ingested, so ask again"


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


async def _chunk_anchors(session: AsyncSession, chunk_ids: list[uuid.UUID]) -> tuple[list[uuid.UUID], list[dict]]:
    """The chunks' papers, and one anchor row (no note_id yet) per spot the chunks cover, both in their order:
    note_anchors' PK is (note_id, paper_id, page, bbox), and two chunks can share a spot. An abstract chunk (a paper
    saved without a PDF) has no spot: its paper is linked, unanchored. chunk_id stays NULL because a re-ingest replaces
    chunks (D10). Raises InvalidInput(STALE_CHUNK) when a chunk is gone."""
    wanted = list(dict.fromkeys(chunk_ids))
    if not wanted:
        return [], []
    chunks = {c.id: c for c in await session.scalars(select(Chunk).where(Chunk.id.in_(wanted)))}
    if len(chunks) != len(wanted):
        raise InvalidInput(STALE_CHUNK)
    rows: dict[tuple, dict] = {}
    for chunk_id in wanted:
        c = chunks[chunk_id]
        if c.page == ABSTRACT_PAGE:
            continue
        key = (c.paper_id, c.page, tuple(tuple(rect) for rect in c.bbox))
        rows.setdefault(key, {"paper_id": c.paper_id, "page": c.page, "bbox": c.bbox, "quoted_text": c.text})
    return list(dict.fromkeys(chunks[chunk_id].paper_id for chunk_id in wanted)), list(rows.values())


async def promote_llm_fragment(
    session: AsyncSession, output_id: uuid.UUID, body: str, chunk_ids: list[uuid.UUID]
) -> NoteView:
    """Save part of a stored answer as a note with provenance='llm' and source_id = the answer.

    The body must come from the answer, so text a person wrote can never be labelled as AI output.
    One anchor per spot the cited chunks cover (_chunk_anchors, shared with save_suggestion).
    """
    # Row lock: two requests for the same answer queue here, so the second sees the first's note below.
    output = await session.get(LLMOutput, output_id, with_for_update=True)
    if output is None:
        raise NotFound(f"answer {output_id} not found")
    if output.kind == "check":
        raise InvalidInput("check_not_promotable")
    text = body.strip()
    if not text:
        raise InvalidInput("a promoted note needs the selected text")
    if _collapse_whitespace(text) not in _collapse_whitespace(output.content):
        raise InvalidInput("body_not_in_output")
    wanted = list(dict.fromkeys(chunk_ids))
    if not wanted:
        raise InvalidInput("a promoted note needs at least one cited chunk")
    if not set(wanted) <= set(output.source_chunks):
        raise InvalidInput("a chunk is not a source of this answer")
    paper_ids, rows = await _chunk_anchors(session, wanted)

    # Saving the same text twice (a double click, a re-selection) returns the note already made, not a copy.
    same = select(Note).where(
        Note.source_id == output.id, Note.source_block.is_(None), Note.provenance == Provenance.LLM, Note.body == text
    )
    existing = await session.scalar(same.limit(1))
    if existing is not None:
        await session.rollback()  # releases the row lock
        await session.refresh(existing)
        return (await _with_anchors(session, [existing]))[0]

    note = Note(body=text, provenance=Provenance.LLM, source_id=output.id)
    session.add(note)
    await session.flush()
    await _link(session, note.id, paper_ids)
    if rows:
        await session.execute(insert(note_anchors), [{**row, "note_id": note.id} for row in rows])
    await session.commit()
    await session.refresh(note)
    await queue_embed(note.id)
    return (await _with_anchors(session, [note]))[0]


async def save_suggestion(session: AsyncSession, output_id: uuid.UUID, index: int) -> NoteView:
    """Saves the chat answer's `:::note` block `index` as a note (D94, D96): provenance='llm', source_id = the answer,
    source_block = the index. The body is the block as stored, markers kept, so it is always the model's words.

    Anchored on the passages the block itself cites ([N…] anchors nothing), and linked to their papers, plus the
    answer's paper in paper chat (N6). Raises NotFound("answer_not_found"), InvalidInput("no_such_block" | "empty_body"
    | STALE_CHUNK), Conflict("already_saved").
    """
    output = await session.get(LLMOutput, output_id)
    if output is None or output.kind != "chat":
        raise NotFound("answer_not_found")
    blocks = note_blocks(output.content)
    if not 0 <= index < len(blocks):
        raise InvalidInput("no_such_block")
    body = blocks[index]
    if not body:
        raise InvalidInput("empty_body")
    cited = [output.source_chunks[i - 1] for i in parse_citations(body, len(output.source_chunks))]
    paper_ids, rows = await _chunk_anchors(session, cited)
    papers = paper_ids + ([output.paper_id] if output.paper_id else [])

    note = Note(body=body, provenance=Provenance.LLM, source_id=output_id, source_block=index)
    session.add(note)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        # Name the refusal only when it is the unique index: another insert failure (the answer deleted meanwhile)
        # is not "already saved".
        saved = select(Note.id).where(Note.source_id == output_id, Note.source_block == index)
        if await session.scalar(saved) is None:
            raise
        raise Conflict("already_saved") from None
    await _link(session, note.id, papers)
    if rows:
        await session.execute(insert(note_anchors), [{**row, "note_id": note.id} for row in rows])
    await session.commit()
    await queue_embed(note.id)
    return await _view(session, note)


def quote_hits(chunk_text: str, quote: str) -> list[list[int]]:
    """Every occurrence of a folded quote in a chunk, as the indexes of the blocks it touches.

    A chunk's text is its blocks joined by a blank line and its bbox holds one rect per block (domain/chunking.py), so
    block i of the text is rect i of the bbox.
    """
    blocks = [fold(block) for block in chunk_text.split("\n\n")]
    spans, start = [], 0
    for block in blocks:
        spans.append((start, start + len(block)))
        start += len(block) + 1
    joined, hits = " ".join(blocks), []
    at = joined.find(quote)
    while at != -1:
        end = at + len(quote)
        hits.append([i for i, (first, last) in enumerate(spans) if first < end and at < last])
        at = joined.find(quote, at + 1)
    return hits


async def locate_quote(session: AsyncSession, paper_id: uuid.UUID, quoted_text: str) -> Anchor:
    """Where a quote sits in a paper: its page and rects, for a caller that knows only the words (MCP, Q1).

    The quote must occur exactly once in the paper's chunks. Its rects are the quoted lines when the PDF is on this
    machine, else the paragraphs they're in. Raises NotFound (the paper), InvalidInput("empty_quote" |
    "quote_not_found" with a hint | "quote_ambiguous" with pages and a hint), Conflict("paper_not_ready") when the
    paper has no chunks yet, Conflict("no_pdf") when it has no PDF.
    """
    chunks = await list_chunks(session, paper_id)
    quote = fold(quoted_text)
    if not quote:
        raise InvalidInput("empty_quote")
    if (await get_paper(session, paper_id)).file_path is None:  # its abstract chunk has no boxes to anchor on
        raise Conflict("no_pdf", detail="This paper has no PDF yet.")
    if not chunks:
        raise Conflict("paper_not_ready")
    # ponytail: a quote that crosses from one chunk into the next isn't found; the hint asks for one passage. Join
    # neighbouring chunks on a page if models keep quoting across them.
    # A place is a page and the paragraphs a hit touches. Chunks of a paper without headings repeat a paragraph at
    # the start of the next chunk, so one place can be hit from two chunks: each place counts as often as the one
    # chunk that hits it most (Counter's | keeps the larger count), so a sentence twice in one paragraph is still two.
    places: Counter[tuple[int, tuple[Rect, ...]]] = Counter()
    for chunk in chunks:
        hits = quote_hits(chunk.text, quote)
        places |= Counter((chunk.page, tuple(tuple(chunk.bbox[i]) for i in blocks)) for blocks in hits)
    if not places:
        raise InvalidInput("quote_not_found", hint=QUOTE_NOT_FOUND_HINT)
    if places.total() > 1:
        raise InvalidInput("quote_ambiguous", pages=sorted({page for page, _ in places}), hint=QUOTE_AMBIGUOUS_HINT)
    [(page, rects)] = places
    paragraphs = list(rects)
    try:
        path = await get_paper_file(session, paper_id)
    except NotFound:  # the PDF isn't on this machine: the paragraphs will do
        lines = []
    else:
        lines = await asyncio.to_thread(quote_rects, path, page, paragraphs, quoted_text)
    return Anchor(paper_id, page, lines or paragraphs, normalize_quote(quoted_text))


async def create_llm_note(session: AsyncSession, paper_id: uuid.UUID, body: str, quoted_text: str) -> NoteView:
    """A note an MCP client wrote, anchored on `quoted_text`: provenance='llm', with its text also kept as an
    llm_outputs row (kind 'mcp') the note's source_id points at, so the model's words survive an edit (D91). On a paper
    saved without a PDF the quote must be in its abstract, and the note is linked unanchored with the quote leading it.

    Raises InvalidInput("empty_body"), and whatever locate_quote (or, without a PDF, _abstract_quote) raises.
    """
    text = body.strip()
    if not text:
        raise InvalidInput("empty_body")
    paper = await get_paper(session, paper_id)
    if paper.has_pdf:
        anchor = await locate_quote(session, paper_id, quoted_text)
    else:
        anchor, text = None, _quoted(_abstract_quote(paper, quoted_text), text)
    # ponytail: model and prompt_version are NOT NULL, but an MCP client names no PaperLab model and uses no prompt.
    output = LLMOutput(paper_id=paper_id, kind=MCP_OUTPUT_KIND, content=text, model="mcp", prompt_version=0)
    session.add(output)
    await session.flush()
    return await _add_llm_note(session, paper_id, text, output.id, anchor)


async def create_ai_note(
    session: AsyncSession, paper_id: uuid.UUID, body: str, output_id: uuid.UUID, quoted_text: str | None = None
) -> NoteView:
    """A note PaperLab's own model wrote (a claim check): provenance='llm', source_id = the llm_outputs row it came
    from (no second row). Anchored when `quoted_text` locates in the paper, else just linked to it.

    Raises InvalidInput("empty_body").
    """
    text = body.strip()
    if not text:
        raise InvalidInput("empty_body")
    anchor = None
    if quoted_text:
        try:
            anchor = await locate_quote(session, paper_id, quoted_text)
        except (InvalidInput, Conflict):
            pass  # a quote spanning chunks, or an abstract-only paper: keep the note, drop the anchor
    return await _add_llm_note(session, paper_id, text, output_id, anchor)


async def _add_llm_note(
    session: AsyncSession, paper_id: uuid.UUID, text: str, output_id: uuid.UUID, anchor: Anchor | None
) -> NoteView:
    note = Note(body=text, provenance=Provenance.LLM, source_id=output_id)
    session.add(note)
    await session.flush()
    await _link(session, note.id, [paper_id])
    if anchor:
        await session.execute(
            insert(note_anchors).values(
                note_id=note.id,
                paper_id=paper_id,
                page=anchor.page,
                bbox=[list(rect) for rect in anchor.bbox],
                quoted_text=anchor.quoted_text,
            )
        )
    await session.commit()
    await queue_embed(note.id)
    return await _view(session, note)
