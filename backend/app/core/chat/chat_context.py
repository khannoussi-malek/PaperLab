"""Writing the passages and notes a chat prompt carries, each with its citation label."""

import uuid
from dataclasses import dataclass

from app.core.chat.retrieval import RetrievedChunk
from app.core.notes.notes import _CITATION, Anchor, NoteView
from app.models import Paper, Provenance

# Notes, in both chats. With OLLAMA_NUM_CTX = 16_384: ~0.5k tokens of instructions, up to ~6k for passages (a whole
# small paper, or SMALL_PAPER_CHARS of a long paper's or a workspace's), ~4k for notes: about 10.5k, leaving ~5.5k.
NOTE_QUOTE_CHARS = 160
NOTE_BODY_CHARS = 400
# ponytail: newest-first is a guess at relevance; rank by similarity to the question if users hit the budget.
NOTES_CHAR_BUDGET = 16_000


BADGES = {Provenance.HUMAN: "You", Provenance.LLM: "AI", Provenance.LLM_EDITED: "AI · edited"}


@dataclass(frozen=True)
class NoteSource:
    id: uuid.UUID
    paper_id: uuid.UUID  # the paper the notes block named it by
    page: int | None  # its first passage there; None for a note on the whole paper
    provenance: str


def source_label(paper: Paper) -> str:
    """'Devlin 2019', or 'Devlin' without a year. The title when no author name is known."""
    # ponytail: the last word of the first non-blank name. "Le Cun" gives "Cun"; the label only orients the model.
    family = next((name.split()[-1] for name in paper.authors if name.strip()), None)
    if family is None:
        return paper.title
    return f"{family} {paper.year}" if paper.year else family


def format_context(paper: Paper | dict[uuid.UUID, Paper], sources: list[RetrievedChunk]) -> str:
    """One Paper labels every source; a paper_id → Paper map labels each source with its own paper."""

    def label(source: RetrievedChunk) -> str:
        return source_label(paper if isinstance(paper, Paper) else paper[source.paper_id])

    def where(source: RetrievedChunk) -> list[str | None]:
        return ["abstract only"] if source.from_abstract else [f"p.{source.page}", source.section]

    return "\n\n".join(
        f"[C{i}] ({', '.join(filter(None, [label(s), *where(s)]))})\n{s.text}" for i, s in enumerate(sources, start=1)
    )


def _cut(text: str, limit: int) -> str:
    """Whitespace collapsed, then at most `limit` characters; a cut text ends with …."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _first_anchor(note: NoteView, paper_ids) -> Anchor | None:
    """The note's first passage on these papers in reading order; None when it has none there."""
    anchors = [a for a in note.anchors if a.paper_id in paper_ids]
    return min(anchors, key=lambda a: (a.page, min(r[1] for r in a.bbox), str(a.paper_id)), default=None)


def _source(note: NoteView, paper_ids) -> NoteSource | None:
    """The note as chat names it: by its first passage on these papers; else by its first linked paper among them, with
    no page (D95); None when it is linked to none of them."""
    anchor = _first_anchor(note, paper_ids)
    if anchor is not None:
        return NoteSource(id=note.id, paper_id=anchor.paper_id, page=anchor.page, provenance=note.provenance)
    paper_id = next((pid for pid in note.paper_ids if pid in paper_ids), None)
    if paper_id is None:
        return None
    return NoteSource(id=note.id, paper_id=paper_id, page=None, provenance=note.provenance)


def format_notes_block(notes: list[NoteView], papers: dict[uuid.UUID, Paper]) -> tuple[str, list[NoteSource]]:
    """One [N{i}] line per note, newest first, while the block fits NOTES_CHAR_BUDGET. A line is never split.

    A note with a passage on one of `papers` is named by its first one, with its page and quote. A note with none there
    is named by its first linked paper among them, with no page or quote, and left out if it has no body either.
    Returns the block and the notes it holds (N{i} is the i-th).
    """
    lines: list[str] = []
    used: list[NoteSource] = []
    for note in sorted(notes, key=lambda n: n.updated_at, reverse=True):
        source, anchor = _source(note, papers), _first_anchor(note, papers)
        # A promoted AI note's body/quote is a verbatim answer slice and may still carry that answer's own
        # [C#]/[N#] markers; strip them first so the model can't echo one that now points elsewhere.
        body = _cut(_CITATION.sub("", note.body), NOTE_BODY_CHARS)
        if source is None or (anchor is None and not body):
            continue
        where = source_label(papers[source.paper_id]) + ("" if source.page is None else f" p.{source.page}")
        line = f"[N{len(lines) + 1}] ({BADGES[note.provenance]} · {where})"
        if anchor is not None:
            line += f' "{_cut(_CITATION.sub("", anchor.quoted_text), NOTE_QUOTE_CHARS)}"'
        if body:
            line += f" — {body}"
        if sum(map(len, lines)) + len(lines) + len(line) > NOTES_CHAR_BUDGET:  # len(lines): the newlines
            break
        lines.append(line)
        used.append(source)
    return "\n".join(lines), used
