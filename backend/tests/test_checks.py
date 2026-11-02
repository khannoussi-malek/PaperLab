"""What a check reads (M22 spec §3.3, D170), on real Postgres in a rolled-back transaction."""

import uuid

import pytest
from conftest import unit_vector
from test_note_papers import paper_only_note
from test_sections import paper_with_headings

from app.core import checks, embedding_index, lenses, sections
from app.core.chat import SMALL_PAPER_CHARS
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Chunk, Note, Provenance
from app.providers import embedding

pytestmark = pytest.mark.anyio

HEADINGS = ["Abstract", "1 Introduction", "3 Method", "4 Results", "5 Conclusion", "References"]
SUMMARY = "We study sparse attention. It cuts memory a lot. The result holds on every task."


async def note_on(session, paper, body=SUMMARY, kind="summary", provenance=Provenance.HUMAN, linked=True) -> Note:
    note = await paper_only_note(session, *([paper] if linked else []), body=body, provenance=provenance)
    note.kind = kind
    await session.commit()
    return note


async def embed(session, chunks) -> None:
    for chunk in chunks:
        chunk.embedding = unit_vector(chunk.text)
    await session.commit()


async def long_paper(session, headings=HEADINGS, size=5_000, embedded=True):
    texts = [f"{h} {i} " + "word " * (size // 5) for i, h in enumerate(headings)]
    paper, chunks = await paper_with_headings(session, headings, texts)
    if embedded:
        await embed(session, chunks)
    return paper, chunks


class Spy:
    """Wraps checks.retrieve, recording the keyword arguments of each call."""

    def __init__(self, monkeypatch):
        self.calls: list[dict] = []
        real = checks.retrieve

        async def spy(session, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            return await real(session, query, **kwargs)

        monkeypatch.setattr(checks, "retrieve", spy)


@pytest.mark.parametrize("provenance", [Provenance.LLM, Provenance.LLM_EDITED])
async def test_only_the_readers_own_text_is_checked(session, provenance):
    paper, _ = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper, provenance=provenance)
    with pytest.raises(Conflict, match="^not_your_text$"):
        await checks.prepare_check(session, note.id)


@pytest.mark.parametrize("kind", [None, "assumption"])
async def test_a_note_of_another_kind_is_not_checkable(session, kind):
    paper, _ = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper, kind=kind)
    with pytest.raises(InvalidInput, match="^not_checkable$"):
        await checks.prepare_check(session, note.id)


async def test_headings_only_is_nothing_written(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    template = "Category:\nContext:\nCorrectness:\nContributions:\nClarity:"
    note = await note_on(session, paper, template, kind="five_cs")
    with pytest.raises(InvalidInput, match="^nothing_written$"):
        await checks.prepare_check(session, note.id)


async def test_a_note_over_8000_characters_is_too_long_and_8000_passes(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    long = await note_on(session, paper, "a" * 8_001)
    ok = await note_on(session, paper, "a" * 8_000)
    with pytest.raises(InvalidInput, match="^note_too_long$"):
        await checks.prepare_check(session, long.id)
    assert (await checks.prepare_check(session, ok.id)).prepared.whole_paper is True


async def test_a_note_on_no_paper_or_two_is_not_on_one_paper(session):
    one, _ = await paper_with_headings(session, HEADINGS)
    two, _ = await paper_with_headings(session, HEADINGS)
    none = await note_on(session, one, linked=False)
    both = await paper_only_note(session, one, two, body=SUMMARY)
    both.kind = "summary"
    await session.commit()
    for note in (none, both):
        with pytest.raises(Conflict, match="^note_not_on_one_paper$"):
            await checks.prepare_check(session, note.id)


async def test_a_paper_without_a_pdf_needs_full_text(session):
    paper, _ = await paper_with_headings(session, ["Abstract"], has_pdf=False)
    with pytest.raises(Conflict, match="^needs_full_text$"):
        await checks.prepare_check(session, (await note_on(session, paper)).id)


async def test_a_paper_still_extracting_is_not_ready(session):
    paper, _ = await paper_with_headings(session, HEADINGS, status="extracting")
    with pytest.raises(Conflict, match="^paper_not_ready$"):
        await checks.prepare_check(session, (await note_on(session, paper)).id)


async def test_a_reconstruction_with_no_method_section_is_lens_empty(session):
    paper, _ = await paper_with_headings(session, ["Abstract", "1 Introduction", "5 Conclusion"])
    note = await note_on(session, paper, "I rebuilt the whole method from memory.", kind="reconstruction")
    with pytest.raises(Conflict, match="^lens_empty$"):
        await checks.prepare_check(session, note.id)


async def test_a_five_cs_on_back_matter_only_is_lens_empty(session):
    paper, _ = await paper_with_headings(session, ["References", "References"])
    note = await note_on(session, paper, "Category: a survey", kind="five_cs")
    with pytest.raises(Conflict, match="^lens_empty$"):
        await checks.prepare_check(session, note.id)


async def test_a_long_paper_with_no_search_model_says_so(session, monkeypatch):
    monkeypatch.setattr(embedding, "get_model", lambda: None)
    paper, _ = await long_paper(session)
    with pytest.raises(Conflict, match="^search_not_set_up$"):
        await checks.prepare_check(session, (await note_on(session, paper)).id)


async def test_a_long_paper_with_no_vectors_is_not_indexed(session, embedder):
    paper, _ = await long_paper(session, embedded=False)
    with pytest.raises(Conflict, match="^paper_not_indexed$"):
        await checks.prepare_check(session, (await note_on(session, paper)).id, embedder)


async def test_a_long_paper_mid_rebuild_pauses(session, embedder, monkeypatch):
    paper, _ = await long_paper(session)
    rebuild = embedding_index.Rebuild(done=1, total=2)

    async def rebuilding(*_):
        return rebuild

    async def waiting(*_):
        return [paper.id]

    monkeypatch.setattr(embedding_index, "rebuild", rebuilding)
    monkeypatch.setattr(embedding_index, "pending_in", waiting)
    with pytest.raises(Conflict, match="^search_rebuilding$"):
        await checks.prepare_check(session, (await note_on(session, paper)).id, embedder)


async def test_an_unknown_note_is_not_found(session):
    with pytest.raises(NotFound):
        await checks.prepare_check(session, uuid.uuid4())


async def test_a_small_lens_goes_whole_without_touching_the_embedder(session, embedder, monkeypatch):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    spy = Spy(monkeypatch)

    got = await checks.prepare_check(session, (await note_on(session, paper)).id, embedder)

    assert embedder.calls == [] and spy.calls == []
    assert got.prepared.whole_paper is True
    ids = [s.id for s in got.prepared.sources]
    assert ids == [c.id for c in chunks[:5]]  # Key ideas + Critical check in reading order; References is neither
    assert got.question == SUMMARY and got.paper_id == paper.id


async def test_a_large_paper_keeps_key_ideas_and_searches_critical_check(session, embedder, monkeypatch):
    paper, chunks = await long_paper(session)
    spy = Spy(monkeypatch)

    got = await checks.prepare_check(session, (await note_on(session, paper)).id, embedder)

    ids = [s.id for s in got.prepared.sources]
    assert {chunks[0].id, chunks[1].id, chunks[4].id} <= set(ids)  # Abstract, Introduction, Conclusion
    assert len(spy.calls) == len(checks.queries("summary", SUMMARY)) == 3
    assert all(c["chunk_ids"] == [chunks[2].id, chunks[3].id] and c["k"] == checks.CHECK_K for c in spy.calls)
    assert sum(len(s.text) for s in got.prepared.sources) <= SMALL_PAPER_CHARS
    assert ids == [c.id for c in chunks if c.id in ids] and got.prepared.whole_paper is False


async def test_an_empty_critical_check_searches_every_non_back_chunk(session, embedder, monkeypatch):
    heads = ["Abstract", "1 Introduction", "Odd heading", "Another odd one", "5 Conclusion", "References"]
    paper, chunks = await long_paper(session, heads)
    spy = Spy(monkeypatch)

    await checks.prepare_check(session, (await note_on(session, paper)).id, embedder)

    rest = [chunks[2].id, chunks[3].id]  # not Key ideas, not back
    assert spy.calls and all(c["chunk_ids"] == rest for c in spy.calls)


async def test_a_reconstruction_has_method_chunks_and_the_outline(session, embedder):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper, "First I embed the tokens. Then I attend.", kind="reconstruction")

    got = await checks.prepare_check(session, note.id, embedder)

    assert [s.id for s in got.prepared.sources] == [chunks[2].id]
    assert "Sections of the method, in order:\n- 3 Method (p.3)\n\n" in got.prepared.prompt


async def test_one_short_sentence_still_finds_passages(session, embedder, monkeypatch):
    paper, _ = await long_paper(session)
    spy = Spy(monkeypatch)

    got = await checks.prepare_check(session, (await note_on(session, paper, "Sparse wins.")).id, embedder)

    assert [c["query"] for c in spy.calls] == ["Sparse wins."]
    assert len(got.prepared.sources) > 3


async def test_a_role_override_changes_what_is_read(session, embedder):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper)
    await sections.set_role(session, paper.id, "4 Results", "back")

    got = await checks.prepare_check(session, note.id, embedder)

    assert chunks[3].id not in [s.id for s in got.prepared.sources]


async def test_the_prompt_holds_the_task_the_label_and_the_note_with_its_braces(session, embedder):
    paper, _ = await paper_with_headings(session, HEADINGS)
    body = "The loss is {x} and {0}."
    note = await note_on(session, paper, body)

    prompt = (await checks.prepare_check(session, note.id, embedder)).prepared.prompt

    assert checks.TASKS["summary"] in prompt and "The reader's summary, between the markers:\n<<<\n" in prompt
    assert f"<<<\n{body}\n>>>" in prompt


async def test_a_five_cs_prompt_holds_the_note_as_written_with_its_headings(session, embedder):
    paper, _ = await paper_with_headings(session, HEADINGS)
    body = "Category: a survey\nContext:\nCorrectness: fine\nContributions: one\nClarity: ok"
    note = await note_on(session, paper, body, kind="five_cs")

    prompt = (await checks.prepare_check(session, note.id, embedder)).prepared.prompt

    assert f"<<<\n{body}\n>>>" in prompt
    assert "Category:" in prompt and "\nContext:\n" in prompt


async def test_refusals_come_in_the_documented_order(session):
    paper, _ = await paper_with_headings(session, HEADINGS, has_pdf=False, status="extracting")
    llm = await note_on(session, paper, kind=None, provenance=Provenance.LLM, linked=False)
    plain = await note_on(session, paper, kind=None, linked=False)
    unlinked = await note_on(session, paper, linked=False)
    unready = await note_on(session, paper)
    for note, code in ((llm, "not_your_text"), (plain, "not_checkable"), (unlinked, "note_not_on_one_paper"),
                       (unready, "needs_full_text")):
        with pytest.raises((Conflict, InvalidInput), match=f"^{code}$"):
            await checks.prepare_check(session, note.id)
    await session.execute(Chunk.__table__.update().where(Chunk.paper_id == paper.id).values(page=1))
    await session.execute(type(paper).__table__.update().where(type(paper).id == paper.id).values(file_path="/x.pdf"))
    await session.commit()
    await session.refresh(paper)
    with pytest.raises(Conflict, match="^paper_not_ready$"):
        await checks.prepare_check(session, unready.id)


async def test_the_outline_is_cut_at_a_thousand_characters(session, embedder):
    heads = [f"3.{i} Method step number {i} of the procedure" for i in range(100)]
    paper, _ = await paper_with_headings(session, heads)
    note = await note_on(session, paper, "I rebuilt the method step by step.", kind="reconstruction")

    prompt = (await checks.prepare_check(session, note.id, embedder)).prepared.prompt

    outline = prompt.split("Sections of the method, in order:")[1].split("The reader's")[0]
    assert 900 < len("Sections of the method, in order:" + outline.rstrip()) <= checks.OUTLINE_CHARS


# --- storing a check, staleness, deleting (Task 10) ---

from datetime import datetime, timedelta, timezone  # noqa: E402

from sqlalchemy import select, update  # noqa: E402

from app.core import chat, notes  # noqa: E402
from app.core.chunking import ChunkDraft  # noqa: E402
from app.models import LLMOutput  # noqa: E402

CONTENT = "Missing: the memory cut [C1]\nSupported: it holds on every task [C2]\nUnsupported: the speed claim"


async def prepared_for(session, note):
    return await checks.prepare_check(session, note.id)


async def check_on(session, note, content=CONTENT, minutes_ago=0):
    output_id = await checks.save_check(session, await prepared_for(session, note), content, "fake", "Fake")
    written = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    await session.execute(update(LLMOutput).where(LLMOutput.id == output_id).values(created_at=written))
    await session.commit()
    return output_id


async def test_save_check_writes_every_column_and_cites_kept_lines_only(session):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper)
    prepared = await prepared_for(session, note)

    content = CONTENT + "\nSupported: it scored 97 [C3]"
    output_id = await checks.save_check(session, prepared, content, "qwen3:8b", "Ollama")

    output = await session.get(LLMOutput, output_id)
    ids = [c.id for c in prepared.prepared.sources]
    assert (output.kind, output.paper_id, output.question, output.content) == ("check", paper.id, note.body, content)
    assert output.source_chunks == ids
    assert output.cited_chunks == [ids[0], ids[1]]  # the dropped line's [C3] is not cited
    assert output.source_notes == [note.id]
    assert (output.whole_paper, output.model, output.connection_name, output.prompt_version) == (
        prepared.prepared.whole_paper, "qwen3:8b", "Ollama", checks.CHECK_PROMPT_VERSION
    )


async def test_a_check_leaves_the_note_and_reading_pass_alone(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper)
    before = (note.body, note.provenance, note.updated_at, paper.reading_pass)

    await check_on(session, note)
    await session.refresh(note)
    await session.refresh(paper)

    assert (note.body, note.provenance, note.updated_at, paper.reading_pass) == before


async def test_saving_after_the_note_was_deleted_raises(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper)
    prepared = await prepared_for(session, note)
    await notes.delete_note(session, note.id)

    with pytest.raises(NotFound):
        await checks.save_check(session, prepared, CONTENT, "fake", "Fake")


async def test_list_checks_gives_the_newest_per_note(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    first, second = await note_on(session, paper), await note_on(session, paper, body="Another summary of it all.")
    await check_on(session, first, minutes_ago=5)
    newest = await check_on(session, first)
    other = await check_on(session, second, minutes_ago=2)

    found = await checks.list_checks(session, paper.id)

    assert {v.output.id for v in found} == {newest, other}
    with pytest.raises(NotFound):
        await checks.list_checks(session, uuid.uuid4())


async def test_stale_flips_on_a_body_edit_and_not_on_colour_kind_or_links(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper)
    await check_on(session, note)

    await notes.update_note(session, note.id, color="#ff0000", kind="reconstruction")
    await notes.set_papers(session, note.id, [paper.id])
    [fresh] = await checks.list_checks(session, paper.id)
    await notes.update_note(session, note.id, body=SUMMARY + " More.")
    [old] = await checks.list_checks(session, paper.id)

    assert (fresh.stale, old.stale) == (False, True)
    assert fresh.note_id == note.id


async def test_a_body_edited_during_the_check_is_stale_at_once(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper)
    prepared = await prepared_for(session, note)
    await notes.update_note(session, note.id, body="Rewritten while the model was thinking.")

    await checks.save_check(session, prepared, CONTENT, "fake", "Fake")

    [view] = await checks.list_checks(session, paper.id)
    assert view.stale is True


async def test_a_replaced_chunk_resolves_to_none(session):
    from app.core import papers

    paper, chunks = await paper_with_headings(session, HEADINGS)
    note = await note_on(session, paper)
    await check_on(session, note)
    drafts = [ChunkDraft(c.ordinal, c.page, c.bbox, c.section_title, c.text) for c in chunks]

    await papers.replace_chunks(session, paper.id, drafts)

    [view] = await checks.list_checks(session, paper.id)
    assert view.sources and all(s is None for s in view.sources)


async def test_deleting_a_note_deletes_its_checks(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    note, kept = await note_on(session, paper), await note_on(session, paper, body="Keep my check please.")
    gone, stays = await check_on(session, note), await check_on(session, kept)

    await notes.delete_note(session, note.id)

    left = set(await session.scalars(select(LLMOutput.id).where(LLMOutput.kind == "check")))
    assert gone not in left and stays in left


async def test_chat_history_lists_no_checks(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    await check_on(session, await note_on(session, paper))

    assert await chat.list_answers(session, paper.id) == []


async def test_saving_a_suggestion_from_a_check_is_not_found(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    output_id = await check_on(session, await note_on(session, paper))

    with pytest.raises(NotFound):
        await notes.save_suggestion(session, output_id, 0)


async def test_retrieval_never_searches_the_chunks_already_kept_as_key_ideas(session, embedder, monkeypatch):
    # no abstract, intro, conclusion or discussion: Key ideas falls back to position, and overlaps Critical check
    heads = ["3 Method", "3.1 Setup", "4 Results", "4.1 Ablation", "Limitations", "References"]
    paper, _ = await long_paper(session, heads, size=8_000)
    spy = Spy(monkeypatch)

    await checks.prepare_check(session, (await note_on(session, paper)).id, embedder)

    kept = set((await lenses.lens_chunks(session, paper.id, "key_ideas")).chunk_ids)
    assert kept
    assert all(not kept & set(c["chunk_ids"]) for c in spy.calls)
