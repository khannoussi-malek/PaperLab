import uuid
from datetime import datetime, timedelta, timezone

import pytest
from conftest import unit_vector
from sqlalchemy import delete, insert
from test_note_papers import paper_only_note

from app.core import chat
from app.core.errors import Conflict, NotFound
from app.core.notes import Anchor, NoteView
from app.models import Chunk, LLMOutput, Note, Paper, Workspace, note_anchors, note_papers, workspace_papers

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
DPR = Paper(id=uuid.uuid4(), title="Dense Passage Retrieval", authors=["Vladimir Karpukhin"], year=2020)
BERT = Paper(id=uuid.uuid4(), title="BERT", authors=[])
PAPERS = {DPR.id: DPR, BERT.id: BERT}


def view(paper: Paper, *, body="", quote="a quote", provenance="human", page=1, minutes_ago=0) -> NoteView:
    anchor = Anchor(paper_id=paper.id, page=page, bbox=[(72.0, 100.0, 300.0, 110.0)], quoted_text=quote)
    updated = NOW - timedelta(minutes=minutes_ago)
    return NoteView(uuid.uuid4(), body, provenance, "#facc15", None, updated, updated, [anchor], [paper.id])


def test_notes_block_all_fit_newest_first_with_badges_labels_and_pages():
    oldest = view(BERT, body="Masked LM is the key.", quote="masked  language\nmodel", page=4, minutes_ago=2)
    middle = view(DPR, body="Dual encoders.", quote="dense retrieval", provenance="llm", page=3, minutes_ago=1)
    newest = view(DPR, body="Negatives\n matter.", quote="in-batch negatives", provenance="llm_edited", page=5)

    block, used = chat.format_notes_block([oldest, middle, newest], PAPERS)

    assert block == (
        '[N1] (AI · edited · Karpukhin 2020 p.5) "in-batch negatives" — Negatives matter.\n'
        '[N2] (AI · Karpukhin 2020 p.3) "dense retrieval" — Dual encoders.\n'
        '[N3] (You · BERT p.4) "masked language model" — Masked LM is the key.'
    )
    assert used == [
        chat.NoteSource(id=newest.id, paper_id=DPR.id, page=5, provenance="llm_edited"),
        chat.NoteSource(id=middle.id, paper_id=DPR.id, page=3, provenance="llm"),
        chat.NoteSource(id=oldest.id, paper_id=BERT.id, page=4, provenance="human"),
    ]
    assert chat.format_notes_block([], PAPERS) == ("", [])


def test_notes_block_cuts_quote_and_body_at_the_exact_limits():
    assert (chat.NOTE_QUOTE_CHARS, chat.NOTE_BODY_CHARS, chat.NOTES_CHAR_BUDGET) == (160, 400, 16_000)
    fits = view(BERT, quote="q" * 160, body="b" * 400, minutes_ago=1)
    cut = view(BERT, quote="q" * 161, body="b" * 401)

    block, _ = chat.format_notes_block([fits, cut], PAPERS)

    first, second = block.split("\n")
    assert first == f'[N1] (You · BERT p.1) "{"q" * 159}…" — {"b" * 399}…'
    assert second == f'[N2] (You · BERT p.1) "{"q" * 160}" — {"b" * 400}'


def test_notes_block_strips_stale_citation_markers_from_quote_and_body():
    note = view(BERT, quote="in-batch negatives [C1][C2]", body="DPR uses in-batch negatives [C1][C2] as noted [N2].")

    block, _ = chat.format_notes_block([note], PAPERS)

    assert block == '[N1] (You · BERT p.1) "in-batch negatives" — DPR uses in-batch negatives as noted .'


def test_notes_block_strips_markers_before_the_length_limit_is_applied():
    quote = "q" * 160 + "[C1]"  # only fits the 160-char budget once the marker is stripped first
    note = view(BERT, quote=quote, body="")

    block, _ = chat.format_notes_block([note], PAPERS)

    assert block == f'[N1] (You · BERT p.1) "{"q" * 160}"'


def test_notes_block_omits_an_empty_body():
    block, _ = chat.format_notes_block([view(BERT, body="  \n ", quote="just a highlight")], PAPERS)

    assert block == '[N1] (You · BERT p.1) "just a highlight"'


def test_notes_block_overflow_keeps_the_newest_whole_lines():
    notes = [view(BERT, quote="q" * 160, body="b" * 400, minutes_ago=i) for i in range(40)]

    block, used = chat.format_notes_block(list(reversed(notes)), PAPERS)

    # N1-N9 lines are 587 characters, N10+ 588: 27 lines make 15,893; a 28th would need 589 more.
    assert (len(used), len(block)) == (27, 15_893)
    assert [s.id for s in used] == [n.id for n in notes[:27]]  # the newest ones, in order
    assert all(line.endswith('" — ' + "b" * 400) for line in block.split("\n"))  # no line was split


def test_notes_block_keeps_every_line_when_the_block_lands_exactly_on_the_budget():
    # 27 full-size lines are 15,893 chars (see above); a 28th line of exactly 106 chars (quote "x"*81, no
    # body) brings the joined block to exactly 15,893 + 1 (newline) + 106 = 16,000: the budget itself.
    full = [view(BERT, quote="q" * 160, body="b" * 400, minutes_ago=i) for i in range(27)]
    boundary = view(BERT, quote="x" * 81, body="", minutes_ago=27)

    block, used = chat.format_notes_block(full + [boundary], PAPERS)

    assert len(block) == 16_000
    assert [s.id for s in used] == [n.id for n in full] + [boundary.id]


def test_notes_block_drops_the_line_that_would_push_past_the_budget():
    # One character more than the exact-fit case above (quote "x"*82) makes the would-be block 16,001: over
    # budget, so the whole 28th line is dropped rather than truncated.
    full = [view(BERT, quote="q" * 160, body="b" * 400, minutes_ago=i) for i in range(27)]
    over = view(BERT, quote="x" * 82, body="", minutes_ago=27)

    block, used = chat.format_notes_block(full + [over], PAPERS)

    assert len(block) == 15_893
    assert [s.id for s in used] == [n.id for n in full]  # notes_used (27) is one less than notes_total (28)


def test_notes_block_names_a_note_on_the_whole_paper_by_its_first_linked_paper_with_no_page_or_quote():
    whole = NoteView(
        uuid.uuid4(), "Dual encoders [C1] scale.", "human", "#facc15", None, NOW, NOW, [], [BERT.id, DPR.id]
    )

    block, used = chat.format_notes_block([whole], PAPERS)

    assert block == "[N1] (You · BERT) — Dual encoders scale."
    assert used == [chat.NoteSource(id=whole.id, paper_id=BERT.id, page=None, provenance="human")]


def test_notes_block_names_a_note_by_its_linked_paper_in_scope_when_its_passage_is_elsewhere():
    elsewhere = Anchor(uuid.uuid4(), 3, [(72.0, 100.0, 300.0, 110.0)], "a quote from a paper outside the scope")
    note = NoteView(
        uuid.uuid4(), "Compare.", "llm", "#facc15", None, NOW, NOW, [elsewhere], [DPR.id, elsewhere.paper_id]
    )

    block, used = chat.format_notes_block([note], PAPERS)

    assert block == "[N1] (AI · Karpukhin 2020) — Compare."
    assert used == [chat.NoteSource(id=note.id, paper_id=DPR.id, page=None, provenance="llm")]


def test_notes_block_leaves_out_a_note_with_no_passage_in_scope_and_no_body():
    empty = NoteView(uuid.uuid4(), "  ", "human", "#facc15", None, NOW, NOW, [], [DPR.id])

    assert chat.format_notes_block([empty], PAPERS) == ("", [])


async def make_workspace(session, papers: list[Paper]) -> Workspace:
    workspace = Workspace(name=f"Workspace {uuid.uuid4().hex[:6]}")
    session.add(workspace)
    await session.flush()
    if papers:
        rows = [{"workspace_id": workspace.id, "paper_id": p.id} for p in papers]
        await session.execute(insert(workspace_papers), rows)
    await session.commit()
    return workspace


async def make_paper(session, title: str, texts: list[str], *, status="ready", embedded=True, **fields) -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", status=status, page_count=len(texts), **fields)
    session.add(paper)
    await session.flush()
    session.add_all(
        Chunk(
            paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[72, 100, 300, 120]], section_title="Method",
            text=text, embedding=unit_vector(text) if embedded else None, embed_model="test", strategy_ver=1,
        )
        for i, text in enumerate(texts)
    )
    await session.commit()
    return paper


async def add_note(session, paper: Paper, body: str, *, page=1, updated_at=NOW, provenance="human") -> Note:
    naive = updated_at.replace(tzinfo=None)  # notes.updated_at is mapped without a timezone
    stored = Note(body=body, provenance=provenance, created_at=naive, updated_at=naive)
    session.add(stored)
    await session.flush()
    await session.execute(insert(note_papers).values(note_id=stored.id, paper_id=paper.id))
    await session.execute(
        insert(note_anchors).values(
            note_id=stored.id, paper_id=paper.id, page=page, bbox=[[72, 100, 300, 110]], quoted_text=f"quote {body}"
        )
    )
    await session.commit()
    return stored


async def test_workspace_prepare_retrieves_across_papers_with_per_paper_labels_and_every_note(session, embedder):
    run = uuid.uuid4().hex  # unique vectors: dead HNSW entries from earlier runs never crowd this query
    dpr = await make_paper(
        session, "Dense Passage Retrieval", [f"{run} dpr {i}" for i in range(4)],
        authors=["Vladimir Karpukhin"], year=2020,
    )
    bert = await make_paper(session, "BERT", [f"{run} bert {i}" for i in range(4)])
    workspace = await make_workspace(session, [dpr, bert])
    older = await add_note(session, bert, "Masked LM.", page=2, updated_at=NOW - timedelta(days=1))
    newer = await add_note(session, dpr, "Dual encoders.", provenance="llm")
    embedder.vectors["search_query: How do they retrieve?"] = unit_vector(f"{run} dpr 2")

    prepared = await chat.prepare(session, chat.Scope(workspace_id=workspace.id), "How do they retrieve?", embedder)

    assert (prepared.system, prepared.whole_paper, prepared.prompt_version) == (chat.WORKSPACE_SYSTEM_PROMPT, False, 2)
    assert prepared.sources[0].text == f"{run} dpr 2"
    assert len(prepared.sources) == 6 and {s.paper_id for s in prepared.sources} == {dpr.id, bert.id}  # 3 each
    assert f"[C1] (Karpukhin 2020, p.3, Method)\n{run} dpr 2" in prepared.prompt
    assert "(BERT, p." in prepared.prompt
    notes_block = '[N1] (AI · Karpukhin 2020 p.1) "quote Dual encoders." — Dual encoders.\n[N2] (You · BERT p.2)'
    assert notes_block in prepared.prompt
    assert [n.id for n in prepared.notes] == [newer.id, older.id]
    assert (prepared.notes_used, prepared.notes_total) == (2, 2)
    assert prepared.prompt.rstrip().endswith("Question: How do they retrieve?")


async def test_workspace_prepare_without_notes_says_so(session, embedder):
    paper = await make_paper(session, "BERT", [uuid.uuid4().hex])
    workspace = await make_workspace(session, [paper])

    prepared = await chat.prepare(session, chat.Scope(workspace_id=workspace.id), "why?", embedder)

    assert "Notes (newest first):\n\nNo notes have been written yet.\n" in prepared.prompt
    assert (prepared.notes, prepared.notes_used, prepared.notes_total) == ([], 0, 0)


async def test_workspace_prepare_rejects_unknown_empty_and_unindexed_workspaces(session, embedder):
    empty = await make_workspace(session, [])
    embedded_but_not_ready = await make_paper(session, "Mid re-ingest", ["one"], status="embedding")
    ready_without_vectors = await make_paper(session, "Old paper", ["two"], embedded=False)
    unindexed = await make_workspace(session, [embedded_but_not_ready, ready_without_vectors])

    with pytest.raises(NotFound, match="^workspace .* not found$"):
        await chat.prepare(session, chat.Scope(workspace_id=uuid.uuid4()), "q", embedder)
    with pytest.raises(Conflict, match="^workspace_empty$"):
        await chat.prepare(session, chat.Scope(workspace_id=empty.id), "q", embedder)
    with pytest.raises(Conflict, match="^workspace_not_indexed$"):
        await chat.prepare(session, chat.Scope(workspace_id=unindexed.id), "q", embedder)
    assert embedder.calls == []


async def test_workspace_prepare_retrieves_only_from_ready_papers(session, embedder):
    run = uuid.uuid4().hex
    ready = await make_paper(session, "Ready paper", [f"{run} ready {i}" for i in range(3)])
    # Mid re-ingest: not ready, but still carries embedded chunks from before the re-ingest started.
    reingesting = await make_paper(
        session, "Mid re-ingest", [f"{run} reingest {i}" for i in range(3)], status="embedding"
    )
    workspace = await make_workspace(session, [ready, reingesting])
    embedder.vectors["search_query: q"] = unit_vector(f"{run} reingest 1")  # an exact match, but not ready

    prepared = await chat.prepare(session, chat.Scope(workspace_id=workspace.id), "q", embedder)

    assert prepared.sources and {s.paper_id for s in prepared.sources} == {ready.id}


def test_scope_requires_exactly_one_of_paper_id_or_workspace_id():
    with pytest.raises(ValueError, match="exactly one"):
        chat.Scope()
    with pytest.raises(ValueError, match="exactly one"):
        chat.Scope(paper_id=uuid.uuid4(), workspace_id=uuid.uuid4())


def test_parse_citations_reads_passage_and_note_labels_separately():
    text = "[N2] backs [C1]; see [N1][N2] and [C3], not [N9] or [X1]."

    assert chat.parse_citations(text, 3) == [1, 3]
    assert chat.parse_citations(text, 2, "N") == [2, 1]


async def test_workspace_answers_are_saved_and_listed_per_workspace(session, embedder):
    run = uuid.uuid4().hex
    dpr = await make_paper(session, "DPR", [f"{run} a", f"{run} b"])
    bert = await make_paper(session, "BERT", [f"{run} c"])
    workspace = await make_workspace(session, [dpr, bert])
    other = await make_workspace(session, [dpr])
    kept = await add_note(session, bert, "kept", page=1)
    deleted = await add_note(session, dpr, "deleted", page=2, updated_at=NOW - timedelta(days=1))
    prepared = await chat.prepare(session, chat.Scope(workspace_id=workspace.id), "why?", embedder)
    content = "Both [C2][C1], as [N2] and [N1] say. Not [N7]."

    output_id = await chat.save_answer(
        session, chat.Scope(workspace_id=workspace.id), "why?", prepared, content, "m", "Conn"
    )
    await chat.save_answer(session, chat.Scope(workspace_id=other.id), "elsewhere", prepared, "x", "m", "Conn")
    single = chat.Prepared(sources=[], system="", prompt="", whole_paper=True)
    await chat.save_answer(session, dpr.id, "single paper", single, "y", "m", "Conn")
    await session.execute(delete(Note).where(Note.id == deleted.id))

    row = await session.get(LLMOutput, output_id)
    chunk_ids = [s.id for s in prepared.sources]
    assert (row.paper_id, row.workspace_id, row.prompt_version) == (None, workspace.id, 2)
    assert (row.source_chunks, row.cited_chunks) == (chunk_ids, [chunk_ids[1], chunk_ids[0]])
    assert (row.source_notes, row.notes_used, row.notes_total) == ([kept.id, deleted.id], 2, 2)

    [answer] = await chat.list_answers(session, chat.Scope(workspace_id=workspace.id))
    assert answer.output.id == output_id
    assert answer.notes == [chat.NoteSource(id=kept.id, paper_id=bert.id, page=1, provenance="human"), None]
    assert [a.output.question for a in await chat.list_answers(session, dpr.id)] == ["single paper"]
    assert (await chat.list_answers(session, dpr.id))[0].notes == []
    with pytest.raises(NotFound):
        await chat.list_answers(session, chat.Scope(workspace_id=uuid.uuid4()))


async def test_listed_answers_name_a_whole_paper_note_by_its_paper_and_drop_one_taken_off_the_scope(session, embedder):
    run = uuid.uuid4().hex
    dpr = await make_paper(session, "DPR", [f"{run} a"])
    workspace = await make_workspace(session, [dpr])
    naive = NOW.replace(tzinfo=None)  # notes' dates are mapped without a timezone
    kept = await paper_only_note(session, dpr, body="On the whole of DPR.", created=naive)
    moved = await paper_only_note(session, dpr, body="Moved away.", created=naive - timedelta(days=1))
    scope = chat.Scope(workspace_id=workspace.id)
    prepared = await chat.prepare(session, scope, "why?", embedder)
    await chat.save_answer(session, scope, "why?", prepared, "Both [N1][N2].", "m", "Conn")
    await session.execute(delete(note_papers).where(note_papers.c.note_id == moved.id))

    [answer] = await chat.list_answers(session, scope)

    assert "[N1] (You · DPR) — On the whole of DPR.\n[N2] (You · DPR) — Moved away." in prepared.prompt
    assert answer.notes == [chat.NoteSource(id=kept.id, paper_id=dpr.id, page=None, provenance="human"), None]
