"""Notes and their anchors. The provenance rules live here and nowhere else:

- LLM responses go to llm_outputs, never directly into notes.            (core/chat/chat.py)
- Promoting an LLM fragment creates a note with provenance='llm' + source_id. (here)
- Saving a chat suggestion creates a note with provenance='llm', source_id = the answer and source_block = the
  block's index.  (here)
- Editing an 'llm' note flips it to 'llm_edited'.                          (here)
- Changing a note's colour never changes its provenance.                     (here)
- Changing a note's papers never changes its provenance (D97).                (here)
- Notes created through MCP get provenance='llm' and source_id = an llm_outputs row of kind 'mcp'.  (here)
- Showing a chart in a note never changes its provenance, and a note made from a chart is the owner's
  ('human'): a chart holds no generated text, only the owner's choice of data.  (here)
- A kind never changes provenance.                                           (here)
- A check (`llm_outputs` kind 'check') is never a note: promote refuses it, and a suggestion can only come from a
  chat answer.
"""

import asyncio
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers.papers import get_paper, get_paper_file
from app.core.platform import queue
from app.domain.chunking import join_lines
from app.domain.constants import DEFAULT_COLOR
from app.domain.errors import InvalidInput, NotFound
from app.domain.table_grid import caption_name
from app.models import Chart, LLMOutput, Note, Paper, Provenance, note_anchors, note_charts, note_papers
from app.providers.extraction import read_region

Rect = tuple[float, float, float, float]

_HEX_COLOR = re.compile(r"#[0-9a-f]{6}")
# What an MCP client's quote and a chunk's text are compared as: typographic quotes and dashes made plain, soft
# hyphens dropped (then NFKC, collapsed whitespace, casefold).
_PLAIN = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                        "­": None})  # fmt: skip
# A citation marker in a stored answer: [C3] is a passage, [N2] a note. Chat parses answers with the same pattern.
_CITATION = re.compile(r"\[([CN])(\d+)\]")
# A suggested note in a chat answer (D94): a line ":::note", the note, then a line ":::".
NOTE_OPEN, NOTE_CLOSE = ":::note", ":::"


@dataclass(frozen=True)
class Anchor:
    paper_id: uuid.UUID
    page: int
    bbox: list[Rect]
    quoted_text: str


@dataclass(frozen=True)
class ChartRef:
    id: uuid.UUID
    title: str


@dataclass(frozen=True)
class NoteView:
    id: uuid.UUID
    body: str
    provenance: str
    color: str
    source_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    anchors: list[Anchor]
    paper_ids: list[uuid.UUID]  # its papers by title, then id (D95); a passage is only ever on one of them
    charts: list[ChartRef] = field(default_factory=list)
    kind: str | None = None


def edited_provenance(current: str) -> str:
    return Provenance.LLM_EDITED if current == Provenance.LLM else current


def normalize_quote(text: str) -> str:
    """Browser selections keep the PDF's line breaks ("trans-\\nfer"); store reading text."""
    return join_lines(text.splitlines())


def normalize_color(color: str) -> str:
    value = color.strip().lower()
    if not _HEX_COLOR.fullmatch(value):
        raise InvalidInput(f"colour {color!r} is not a #rrggbb hex value")
    return value


def parse_citations(text: str, n: int, kind: str = "C") -> list[int]:
    """[C{i}] (or [N{i}]) numbers cited in the final text: first-seen order, no repeats, unknown labels dropped."""
    cited = (int(number) for label, number in _CITATION.findall(text) if label == kind)
    return list(dict.fromkeys(i for i in cited if 1 <= i <= n))


def note_blocks(content: str) -> list[str]:
    """The suggested notes in a chat answer, in order: blocks numbered from 0, empty ones included, so an index never
    shifts. A line that is exactly `:::note` once stripped opens a block and one that is exactly `:::` closes it; the
    block is the lines between, joined and stripped as a whole. A block still open at the end runs to the end, and a
    `:::note` line inside a block is text (they don't nest). Lines split on "\\n" only, so features/chat/noteBlocks.ts
    reads an answer the same way (both are tested on its noteBlocks.cases.json)."""
    blocks: list[str] = []
    lines: list[str] | None = None  # the open block's lines; None outside a block
    for line in content.split("\n"):
        if lines is None:
            if line.strip() == NOTE_OPEN:
                lines = []
        elif line.strip() == NOTE_CLOSE:
            blocks.append("\n".join(lines).strip())
            lines = None
        else:
            lines.append(line)
    if lines is not None:
        blocks.append("\n".join(lines).strip())
    return blocks


def reading_position(note: NoteView, paper_id: uuid.UUID) -> tuple[int, float, float]:
    return min((a.page, r[1], r[0]) for a in note.anchors if a.paper_id == paper_id for r in a.bbox)


async def queue_embed(*note_ids: uuid.UUID) -> None:
    """Queues the embedding of these notes as ONE job (workers/references.embed_note): an import of many notes is one
    job, not one per note. Call after the commit that saved their bodies. A queue that is down only logs: the next
    references fetch embeds them."""
    if not note_ids:
        return
    try:
        await queue.enqueue("embed_note", [str(note_id) for note_id in note_ids])
    except Exception:
        logging.getLogger(__name__).exception("could not queue the embedding of notes %s", note_ids)


async def _get_note(session: AsyncSession, note_id: uuid.UUID) -> Note:
    note = await session.get(Note, note_id)
    if note is None:
        raise NotFound(f"note {note_id} not found")
    return note


async def _link(session: AsyncSession, note_id: uuid.UUID, paper_ids) -> None:
    """Links the note to these papers (D95), each once; a link it has already is kept. Every writer calls it before it
    inserts anchors: note_anchors references note_papers, so an anchor on an unlinked paper is refused."""
    rows = [{"note_id": note_id, "paper_id": paper_id} for paper_id in dict.fromkeys(paper_ids)]
    if rows:
        await session.execute(pg_insert(note_papers).values(rows).on_conflict_do_nothing())


async def papers_of(session: AsyncSession, note_ids) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Each note's papers (D95), by title then id: what "a note's first paper" means everywhere. A note with no paper
    is absent. Sorted here, as workspaces.notes and the frontend sort, not by the database's collation."""
    rows = await session.execute(
        select(note_papers.c.note_id, Paper.id, Paper.title)
        .join(Paper, Paper.id == note_papers.c.paper_id)
        .where(note_papers.c.note_id.in_(list(note_ids)))
    )
    by_note: dict[uuid.UUID, list[tuple[str, str, uuid.UUID]]] = {}
    for note_id, paper_id, title in rows:
        by_note.setdefault(note_id, []).append((title, str(paper_id), paper_id))
    return {note_id: [paper_id for *_, paper_id in sorted(papers)] for note_id, papers in by_note.items()}


async def _with_anchors(session: AsyncSession, notes: list[Note]) -> list[NoteView]:
    """The notes as views: their passages, their papers and the charts they show."""
    rows = await session.execute(select(note_anchors).where(note_anchors.c.note_id.in_([n.id for n in notes])))
    anchors: dict[uuid.UUID, list[Anchor]] = {}
    for row in rows:
        anchor = Anchor(
            paper_id=row.paper_id,
            page=row.page,
            bbox=[tuple(r) for r in row.bbox],
            quoted_text=row.quoted_text or "",
        )
        anchors.setdefault(row.note_id, []).append(anchor)
    linked = await papers_of(session, [n.id for n in notes])
    shown = await session.execute(
        select(note_charts.c.note_id, Chart.id, Chart.title)
        .join(Chart, Chart.id == note_charts.c.chart_id)
        .where(note_charts.c.note_id.in_([n.id for n in notes]))
        .order_by(Chart.title)
    )
    charts: dict[uuid.UUID, list[ChartRef]] = {}
    for note_id, chart_id, title in shown:
        charts.setdefault(note_id, []).append(ChartRef(chart_id, title))
    return [
        NoteView(
            id=n.id,
            body=n.body,
            provenance=n.provenance,
            color=n.color,
            source_id=n.source_id,
            created_at=n.created_at,
            updated_at=n.updated_at,
            anchors=anchors.get(n.id, []),
            paper_ids=linked.get(n.id, []),
            charts=charts.get(n.id, []),
            kind=n.kind,
        )
        for n in notes
    ]


async def create_human_note(
    session: AsyncSession, body: str, anchor: Anchor, color: str = DEFAULT_COLOR, *, kind: str | None = None
) -> NoteView:
    paper = await get_paper(session, anchor.paper_id)
    if paper.page_count is not None and not 1 <= anchor.page <= paper.page_count:
        raise InvalidInput(f"page {anchor.page} is outside 1..{paper.page_count}")
    if not anchor.bbox:
        raise InvalidInput("an anchor needs at least one rect")
    quote = normalize_quote(anchor.quoted_text)
    if not quote:
        raise InvalidInput("an anchor needs the quoted text")

    note = Note(body=body.strip(), provenance=Provenance.HUMAN, color=normalize_color(color), kind=kind)
    session.add(note)
    await session.flush()
    await _link(session, note.id, [anchor.paper_id])
    await session.execute(
        insert(note_anchors).values(
            note_id=note.id,
            paper_id=anchor.paper_id,
            page=anchor.page,
            bbox=[list(r) for r in anchor.bbox],
            quoted_text=quote,
        )
    )
    await session.commit()
    await session.refresh(note)
    await queue_embed(note.id)
    return (await _with_anchors(session, [note]))[0]


async def create_figure_note(
    session: AsyncSession, paper_id: uuid.UUID, page: int, region: Rect, body: str, color: str = DEFAULT_COLOR
) -> NoteView:
    """A note on a box drawn round a figure, quoting the figure's caption. Raises InvalidInput("no_pdf") for a paper
    saved without a PDF."""
    paper = await get_paper(session, paper_id)
    if paper.file_path is None:
        raise InvalidInput("no_pdf")
    if page < 1 or (paper.page_count is not None and page > paper.page_count):
        raise InvalidInput(f"page {page} is outside 1..{paper.page_count}")
    if not (region[0] < region[2] and region[1] < region[3]):
        raise InvalidInput("a region needs x0 < x1 and y0 < y1")
    quote = None
    try:
        path = await get_paper_file(session, paper_id)
        text = await asyncio.to_thread(read_region, path, page, region)
        quote = caption_name(text.blocks, region, label="figure")
    except NotFound:
        pass  # the file is not on this machine: the box alone anchors the note
    # ponytail: the fallback quote is PaperLab's words, and shows only with no caption within CAPTION_GAP.
    anchor = Anchor(paper_id, page, [region], quote or f"Figure on p. {page}")
    return await create_human_note(session, body, anchor, color, kind="figure")


def _abstract_quote(paper: Paper, quoted_text: str) -> str:
    """The quote, its whitespace collapsed, once it is found in the abstract of a paper saved without a PDF: matched as
    locate_quote matches a passage (fold). Raises InvalidInput("empty_quote" | "quote_not_found")."""
    quote = " ".join(quoted_text.split())
    if not fold(quote):
        raise InvalidInput("empty_quote")
    if fold(quote) not in fold(paper.abstract or ""):
        raise InvalidInput("quote_not_found", hint="Copy the quote exactly from this paper's abstract.")
    return quote


def _quoted(quote: str, body: str) -> str:
    """An abstract note's body: the quote in curly quotes, then the note. Note cards show plain text, not Markdown."""
    return f"“{quote}”\n\n{body}" if body else f"“{quote}”"


async def create_paper_note(
    session: AsyncSession,
    paper_id: uuid.UUID,
    body: str,
    quote: str | None = None,
    color: str = DEFAULT_COLOR,
    *,
    kind: str | None = None,
) -> NoteView:
    """A person's note on the whole of a paper: linked to it, with no anchor. With `quote`, text from its abstract (a
    paper saved without a PDF), the body starts with that quote; a quote on a paper with a PDF needs an anchored note
    (create_human_note). Raises NotFound, InvalidInput("anchor_required" | "empty_body" | "empty_quote" |
    "quote_not_found")."""
    paper = await get_paper(session, paper_id)
    if paper.has_pdf and quote is not None:
        raise InvalidInput("anchor_required")
    text = body.strip()
    if quote is not None:
        text = _quoted(_abstract_quote(paper, quote), text)
    if not text:
        raise InvalidInput("empty_body")
    note = Note(body=text, provenance=Provenance.HUMAN, color=normalize_color(color), kind=kind)
    session.add(note)
    await session.flush()
    await _link(session, note.id, [paper_id])
    await session.commit()
    await queue_embed(note.id)
    return await _view(session, note)


def _placed_on(note: NoteView, paper_id: uuid.UUID) -> bool:
    return any(anchor.paper_id == paper_id for anchor in note.anchors)


async def list_notes_for_paper(session: AsyncSession, paper_id: uuid.UUID) -> list[NoteView]:
    """The notes linked to the paper (D95): those with no passage on it first, newest first; then the rest in reading
    order. Raises NotFound."""
    await get_paper(session, paper_id)
    linked_here = select(note_papers.c.note_id).where(note_papers.c.paper_id == paper_id)
    views = await _with_anchors(session, list(await session.scalars(select(Note).where(Note.id.in_(linked_here)))))
    whole = sorted((v for v in views if not _placed_on(v, paper_id)), key=lambda v: v.created_at, reverse=True)
    placed = sorted((v for v in views if _placed_on(v, paper_id)), key=lambda v: reading_position(v, paper_id))
    return whole + placed


async def list_notes(
    session: AsyncSession, paper_id: uuid.UUID | None = None, unlinked: bool = False
) -> list[NoteView]:
    """Newest first (D98): every note; with `paper_id`, the notes linked to that paper (NotFound when there is no such
    paper); with `unlinked`, the notes linked to no paper."""
    query = select(Note).order_by(Note.created_at.desc(), Note.id)
    if paper_id is not None:
        await get_paper(session, paper_id)
        query = query.where(Note.id.in_(select(note_papers.c.note_id).where(note_papers.c.paper_id == paper_id)))
    elif unlinked:
        query = query.where(Note.id.not_in(select(note_papers.c.note_id)))
    return await _with_anchors(session, list(await session.scalars(query)))


async def set_papers(session: AsyncSession, note_id: uuid.UUID, paper_ids: list[uuid.UUID]) -> NoteView:
    """Links the note to exactly these papers (D95). A link not listed goes, and the note's passages on that paper go
    with it (the database cascades); a new link is to the whole paper. Duplicates count once. Provenance never changes
    (D97), and updated_at moves only when the set does. Raises NotFound (the note), NotFound("unknown_paper")."""
    note = await _get_note(session, note_id)
    wanted = set(paper_ids)
    if set(await session.scalars(select(Paper.id).where(Paper.id.in_(list(wanted))))) != wanted:
        raise NotFound("unknown_paper")
    current = set(await session.scalars(select(note_papers.c.paper_id).where(note_papers.c.note_id == note_id)))
    if current != wanted:
        gone = note_papers.c.paper_id.not_in(list(wanted))  # an empty list takes the note off every paper
        await session.execute(delete(note_papers).where(note_papers.c.note_id == note_id, gone))
        await _link(session, note_id, wanted - current)
        await session.execute(update(Note).where(Note.id == note_id).values(updated_at=func.now()))
        await session.commit()
    return await _view(session, note)


UNSET: Any = object()  # update_note's kind: left out, as against None, which clears it


async def update_note(
    session: AsyncSession, note_id: uuid.UUID, *, body: str | None = None, color: str | None = None, kind=UNSET
) -> NoteView:
    note = await _get_note(session, note_id)
    changes: dict[str, str | None] = {}
    if body is not None and body.strip() != note.body:
        changes.update(body=body.strip(), provenance=edited_provenance(note.provenance))
    if color is not None and normalize_color(color) != note.color:
        changes["color"] = normalize_color(color)
    if kind is not UNSET and kind != note.kind:
        changes["kind"] = None if kind is None else str(kind)
    if changes:
        await session.execute(update(Note).where(Note.id == note_id).values(**changes, updated_at=func.now()))
        await session.commit()
        await session.refresh(note)
    if "body" in changes:  # a colour or kind change keeps the vector
        await queue_embed(note.id)
    return (await _with_anchors(session, [note]))[0]


async def delete_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    await _get_note(session, note_id)
    # a check lives beside its note (no FK on the array): it goes with it, in the same transaction
    await session.execute(delete(LLMOutput).where(LLMOutput.kind == "check", LLMOutput.source_notes.any(note_id)))
    await session.execute(delete(Note).where(Note.id == note_id))
    await session.commit()


async def _view(session: AsyncSession, note: Note) -> NoteView:
    await session.refresh(note)
    return (await _with_anchors(session, [note]))[0]


def fold(text: str) -> str:
    """Text as a quote is matched: NFKC, plain quotes and dashes, no soft hyphens, collapsed whitespace, casefolded."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(_PLAIN).split()).casefold()


