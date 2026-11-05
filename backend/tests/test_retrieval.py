import uuid
from collections import Counter

import numpy as np
import pytest
from conftest import unit_vector
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, insert, select, text

from app.core import retrieval
from app.core.errors import Conflict
from app.core.retrieval import retrieve
from app.models import Chunk, Paper, Workspace, workspace_papers
from app.providers import embedding

pytestmark = pytest.mark.anyio

QUERY = "how does attention work?"


def near(query: list[float], spread: float, seed: str) -> list[float]:
    """A unit vector at a small, spread-dependent distance from the query.

    Real chunks already in the dev database sit at distance ~1 from a random query, so they never
    reach the top k of these.
    """
    vector = np.array(query) + spread * np.array(unit_vector(seed))
    return (vector / np.linalg.norm(vector)).tolist()


async def seed_papers(session, embedder):
    """Papers A and B, six embedded chunks each at interleaved distances, plus one unembedded chunk in A."""
    query = unit_vector(uuid.uuid4().hex)  # a fixed one piles up dead HNSW entries: see fresh_query
    embedder.vectors[f"search_query: {QUERY}"] = query
    papers = [Paper(title=name, file_path=f"/{name}.pdf", status="ready") for name in ("A", "B")]
    session.add_all(papers)
    await session.flush()
    chunks = [
        Chunk(
            paper_id=paper.id,
            ordinal=i,
            page=i + 1,
            bbox=[[10, 20, 30, 40]],
            section_title="Method" if i % 2 else None,
            text=f"{paper.title} chunk {i}",
            embedding=near(query, 0.1 * (2 * i + offset + 1), f"{paper.title}{i}"),
            embed_model="test",
            strategy_ver=1,
        )
        for offset, paper in enumerate(papers)
        for i in range(6)
    ]
    unembedded = Chunk(
        paper_id=papers[0].id, ordinal=6, page=7, bbox=[[1, 2, 3, 4]], text="no vector yet", embed_model="test",
        strategy_ver=1,
    )
    session.add_all([*chunks, unembedded])
    await session.commit()
    distance = {c.id: 1 - float(np.dot(query, c.embedding)) for c in chunks}
    return papers, chunks, unembedded, distance


async def test_returns_the_true_nearest_k_in_order(session, embedder, monkeypatch):
    # The whole library on the shared database: real chunks about attention would join a keyword ranking.
    monkeypatch.setattr(retrieval.settings, "hybrid_search", False)
    _, chunks, _, distance = await seed_papers(session, embedder)

    found = await retrieve(session, QUERY, k=5, embedder=embedder)

    expected = sorted(chunks, key=lambda c: distance[c.id])[:5]
    assert [r.id for r in found] == [c.id for c in expected]
    assert [r.distance for r in found] == pytest.approx([distance[c.id] for c in expected], abs=1e-5)
    assert embedder.calls[0][0] == [f"search_query: {QUERY}"]
    first = found[0]
    assert (first.page, first.bbox, first.text) == (expected[0].page, [(10.0, 20.0, 30.0, 40.0)], expected[0].text)


async def test_paper_scope_is_respected(session, embedder):
    (paper_a, _), chunks, _, distance = await seed_papers(session, embedder)

    found = await retrieve(session, QUERY, paper_ids=[paper_a.id], k=4, embedder=embedder)

    in_a = sorted((c for c in chunks if c.paper_id == paper_a.id), key=lambda c: distance[c.id])
    assert [r.id for r in found] == [c.id for c in in_a[:4]]
    assert {r.paper_id for r in found} == {paper_a.id}


async def test_chunks_without_an_embedding_are_skipped(session, embedder):
    (paper_a, _), _, unembedded, _ = await seed_papers(session, embedder)

    found = await retrieve(session, QUERY, paper_ids=[paper_a.id], k=100, embedder=embedder)

    assert len(found) == 6
    assert unembedded.id not in {r.id for r in found}


async def test_uses_the_process_model_when_no_embedder_is_given(session, embedder, monkeypatch):
    (paper_a, _), _, _, _ = await seed_papers(session, embedder)
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)

    found = await retrieve(session, QUERY, paper_ids=[paper_a.id], k=1)
    assert len(found) == 1 and embedder.calls


async def test_with_no_search_model_retrieval_says_search_is_not_set_up(session, monkeypatch):
    monkeypatch.setattr(embedding, "get_model", lambda: None)  # nothing downloaded

    with pytest.raises(Conflict, match="^search_not_set_up$") as refused:
        await retrieve(session, QUERY, k=3)

    assert refused.value.details == {
        "detail": "Search isn't set up. Download the search model in Settings to search long papers and workspaces."
    }


def fresh_query(embedder) -> list[float]:
    """A query vector no earlier test run used.

    Rolled-back inserts leave dead HNSW entries until autovacuum. Seeded from a fixed string, thousands of
    identical dead vectors pile up around the query, and an HNSW scan gives up before reaching live rows.
    """
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {QUERY}"] = query
    return query


def at_spread(query: list[float], spread: float) -> list[float]:
    """A unit vector whose cosine distance from the query is exactly 1 - 1/sqrt(1 + spread²).

    near() adds random noise that isn't orthogonal to the query, which moves distances by ~0.007 per sigma: enough
    to swap two papers whose spreads differ by 0.05.
    """
    q = np.array(query)
    noise = np.array(unit_vector(uuid.uuid4().hex))
    noise -= noise.dot(q) * q
    vector = q + spread * noise / np.linalg.norm(noise)
    return (vector / np.linalg.norm(vector)).tolist()


async def add_paper(session, query: list[float], title: str, spreads: list[float]) -> Paper:
    """A ready paper whose chunk i sits at spreads[i] from the query, in that order of distance."""
    paper = Paper(title=title, file_path=f"/{title}.pdf", status="ready")
    session.add(paper)
    await session.flush()
    session.add_all(
        Chunk(
            paper_id=paper.id, ordinal=i, page=1, bbox=[[1, 2, 3, 4]], text=f"{title} chunk {i}",
            embedding=at_spread(query, spread), embed_model="test", strategy_ver=1,
        )
        for i, spread in enumerate(spreads)
    )
    await session.commit()
    return paper


async def make_workspace(session, papers: list[Paper]) -> Workspace:
    workspace = Workspace(name=f"Retrieval {uuid.uuid4()}")  # unique: the owner's workspaces share the database
    session.add(workspace)
    await session.flush()
    if papers:  # an executemany with an empty list of rows is invalid
        rows = [{"workspace_id": workspace.id, "paper_id": p.id} for p in papers]
        await session.execute(insert(workspace_papers), rows)
    await session.commit()
    return workspace


async def test_workspace_and_multi_paper_scopes_return_only_in_scope_chunks(session, embedder):
    query = fresh_query(embedder)
    paper_a = await add_paper(session, query, "A", [0.1, 0.3, 0.5, 0.7])
    paper_b = await add_paper(session, query, "B", [0.2, 0.4, 0.6, 0.8])
    outside = await add_paper(session, query, "Outside", [0.05, 0.06])  # nearer than anything in scope
    workspace = await make_workspace(session, [paper_a, paper_b])
    await make_workspace(session, [outside])

    by_workspace = await retrieve(session, QUERY, workspace_id=workspace.id, k=6, embedder=embedder)
    by_ids = await retrieve(session, QUERY, paper_ids=[paper_a.id, paper_b.id], k=6, embedder=embedder)

    expected = ["A chunk 0", "B chunk 0", "A chunk 1", "B chunk 1", "A chunk 2", "B chunk 2"]  # 3 per paper
    assert [r.text for r in by_workspace] == expected
    assert [r.text for r in by_ids] == expected


async def test_both_scopes_at_once_is_a_value_error(session, embedder):
    with pytest.raises(ValueError, match="paper_ids or workspace_id, not both"):
        await retrieve(session, QUERY, paper_ids=[], workspace_id=uuid.uuid4(), embedder=embedder)


async def test_an_empty_paper_list_returns_nothing_without_embedding_the_query(session, embedder):
    assert await retrieve(session, QUERY, paper_ids=[], embedder=embedder) == []
    assert embedder.calls == []


async def test_k_defaults_to_8(session, embedder):
    paper = await add_paper(session, fresh_query(embedder), "Ten chunks", [0.1 * (i + 1) for i in range(10)])

    assert len(await retrieve(session, QUERY, paper_ids=[paper.id], embedder=embedder)) == 8


async def test_a_dominant_paper_gets_at_most_3_of_k(session, embedder):
    query = fresh_query(embedder)
    dominant = await add_paper(session, query, "Dominant", [0.05 + 0.01 * i for i in range(10)])
    second = await add_paper(session, query, "Second", [0.5, 0.6, 0.7, 0.8])
    third = await add_paper(session, query, "Third", [0.55, 0.65, 0.75, 0.85])
    workspace = await make_workspace(session, [dominant, second, third])
    ids = [dominant.id, second.id, third.id]

    capped = Counter(r.paper_id for r in await retrieve(session, QUERY, workspace_id=workspace.id, embedder=embedder))
    by_ids = Counter(r.paper_id for r in await retrieve(session, QUERY, paper_ids=ids, embedder=embedder))
    single = await retrieve(session, QUERY, paper_ids=[dominant.id], embedder=embedder)
    uncapped = await retrieve(session, QUERY, workspace_id=workspace.id, per_paper=8, embedder=embedder)

    assert retrieval.MAX_PER_PAPER == 3
    assert capped == by_ids == {dominant.id: 3, second.id: 3, third.id: 2}
    assert len(single) == 8  # one paper: no cap
    assert {r.paper_id for r in uncapped} == {dominant.id}


async def test_a_forced_hnsw_plan_still_returns_k_rows(session, embedder):
    """A filtered HNSW scan post-filters inside ef_search (40) candidates: 60 nearer chunks outside the scope used to
    leave 0 rows."""
    query = fresh_query(embedder)
    await add_paper(session, query, "Crowd", [0.1] * 60)
    paper_a = await add_paper(session, query, "A", [1.0] * 4)
    paper_b = await add_paper(session, query, "B", [1.0] * 4)
    workspace = await make_workspace(session, [paper_a, paper_b])
    # enable_seqscan alone still picks the (paper_id, page) btree and a sort; without sorts, HNSW is the only way.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL enable_sort = off"))
    plan = await session.execute(
        text("EXPLAIN SELECT id FROM chunks WHERE paper_id = ANY(:ids) ORDER BY embedding <=> :q LIMIT 6").bindparams(
            bindparam("q", type_=Vector(768))
        ),
        {"ids": [paper_a.id, paper_b.id], "q": query},
    )
    assert "chunks_embedding_idx" in "\n".join(row[0] for row in plan)

    by_ids = await retrieve(session, QUERY, paper_ids=[paper_a.id, paper_b.id], k=6, embedder=embedder)
    assert len(by_ids) == 6
    assert [r.distance for r in by_ids] == sorted(r.distance for r in by_ids)
    assert len(await retrieve(session, QUERY, workspace_id=workspace.id, k=6, embedder=embedder)) == 6


async def test_a_single_paper_workspace_is_not_capped(session, embedder):
    paper = await add_paper(session, fresh_query(embedder), "Solo", [0.1 * (i + 1) for i in range(10)])
    workspace = await make_workspace(session, [paper])

    found = await retrieve(session, QUERY, workspace_id=workspace.id, embedder=embedder)

    assert len(found) == 8  # k defaults to 8; a lone paper is uncapped, same as passing its id directly
    assert {r.paper_id for r in found} == {paper.id}


async def test_an_empty_workspace_returns_nothing_without_embedding_the_query(session, embedder):
    workspace = await make_workspace(session, [])

    assert await retrieve(session, QUERY, workspace_id=workspace.id, embedder=embedder) == []
    assert embedder.calls == []


async def test_the_search_widens_hnsw_ef_search_to_the_setting(session, embedder, monkeypatch):
    # M8 step 2: at pgvector's default 40 a workspace search missed ~4% of its true top 8; 100 brought @8 to ≥ 0.99.
    monkeypatch.setattr(retrieval.settings, "hnsw_ef_search", 123)
    await retrieve(session, "anything", k=4, embedder=embedder)

    assert await session.scalar(text("SHOW hnsw.ef_search")) == "123"


def test_hnsw_ef_search_defaults_to_100_and_rejects_nonsense():
    from pydantic import ValidationError  # noqa: PLC0415

    from app.config import Settings  # noqa: PLC0415

    assert Settings().hnsw_ef_search == 100
    for bad in (0, 1001):
        with pytest.raises(ValidationError):
            Settings(hnsw_ef_search=bad)


async def test_chunk_ids_limit_retrieval_to_those_chunks(session, embedder):
    _, chunks, unembedded, distance = await seed_papers(session, embedder)
    wanted = [chunks[1], chunks[4], chunks[8]]

    found = await retrieve(session, QUERY, chunk_ids=[c.id for c in [*wanted, unembedded]], k=5, embedder=embedder)

    # An unembedded chunk is still skipped; the rest come back nearest first.
    assert [r.id for r in found] == [c.id for c in sorted(wanted, key=lambda c: distance[c.id])]


async def test_an_empty_chunk_list_returns_nothing_without_embedding_the_query(session, embedder):
    await seed_papers(session, embedder)

    assert await retrieve(session, QUERY, chunk_ids=[], embedder=embedder) == []
    assert embedder.calls == []


async def test_chunk_ids_combine_with_paper_ids_and_the_per_paper_cap(session, embedder):
    (paper_a, paper_b), chunks, _, _ = await seed_papers(session, embedder)
    listed = [c.id for c in chunks[:6]] + [c.id for c in chunks[6:8]]  # all of A, two of B

    found = await retrieve(session, QUERY, paper_ids=[paper_a.id, paper_b.id], chunk_ids=listed, k=8, embedder=embedder)

    assert Counter(r.paper_id for r in found) == {paper_a.id: 3, paper_b.id: 2}
    assert {r.id for r in found} <= set(listed)


RARE = "zorblaxine"  # a made-up drug name: no real chunk in the shared database holds it


async def add_texts(session, query: list[float], title: str, texts_and_spreads: list[tuple[str, float]]) -> list[Chunk]:
    """A ready paper with one chunk per (text, spread from the query)."""
    paper = Paper(title=title, file_path=f"/{title}.pdf", status="ready")
    session.add(paper)
    await session.flush()
    chunks = [
        Chunk(
            paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[1, 2, 3, 4]], text=text,
            embedding=at_spread(query, spread), embed_model="test", strategy_ver=1,
        )
        for i, (text, spread) in enumerate(texts_and_spreads)
    ]
    session.add_all(chunks)
    await session.commit()
    return chunks


def hybrid(monkeypatch, on: bool) -> None:
    monkeypatch.setattr(retrieval.settings, "hybrid_search", on)


# Inside one paper, retrieval stays vector only (see retrieval.py), so these tests scope hybrid search to their chunks.


async def test_hybrid_search_finds_an_exact_rare_term_the_vectors_rank_last(session, embedder, monkeypatch):
    # The MI test's miss: "itraconazole" was in both labels, and no chunk of the top 8 held it.
    question = f"Which dose with {RARE}?"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    near_ones = [(f"Background chunk {i}", 0.1 * (i + 1)) for i in range(6)]  # none shares a word with the question
    chunks = await add_texts(session, query, "Label", [*near_ones, (f"Avoid strong inhibitors such as {RARE}.", 3.0)])
    scope = [c.id for c in chunks]

    hybrid(monkeypatch, False)
    vector_only = await retrieve(session, question, chunk_ids=scope, k=3, embedder=embedder)
    hybrid(monkeypatch, True)
    fused = await retrieve(session, question, chunk_ids=scope, k=3, embedder=embedder)
    one_paper = await retrieve(session, question, paper_ids=[chunks[0].paper_id], k=3, embedder=embedder)

    assert chunks[-1].id not in {r.id for r in vector_only}
    rare = next(r for r in fused if r.id == chunks[-1].id)  # lexical rank 1 + vector rank 7
    # Inside one paper its own topic words are everywhere: the retrieval eval lost recall there, so it stays vectors.
    assert [r.id for r in one_paper] == [r.id for r in vector_only]
    assert rare.distance == pytest.approx(1 - 1 / np.sqrt(1 + 3.0**2), abs=1e-5)  # still its cosine distance


async def test_hybrid_search_weights_a_rare_term_above_a_common_one(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    question = f"dose of {RARE}"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    common = [(f"The dose in group {i}", 0.1 * (i + 1)) for i in range(6)]
    chunks = await add_texts(
        session, query, "Weights", [*common, ("Another dose table", 3.0), (f"Nothing on {RARE} here", 3.1)]
    )

    found = await retrieve(session, question, chunk_ids=[c.id for c in chunks], k=8, embedder=embedder)
    order = [r.id for r in found]

    # Both far chunks match one word each; "dose" is in 7 of 8 chunks, the drug name in one.
    assert order.index(chunks[-1].id) < order.index(chunks[-2].id)


async def test_hybrid_search_without_a_matching_word_keeps_the_vector_order(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    query = fresh_query(embedder)
    paper = await add_paper(session, query, "Plain", [0.1 * (i + 1) for i in range(6)])
    scope = list(await session.scalars(select(Chunk.id).where(Chunk.paper_id == paper.id)))

    found = await retrieve(session, QUERY, chunk_ids=scope, k=6, embedder=embedder)

    assert [r.text for r in found] == [f"Plain chunk {i}" for i in range(6)]


async def test_hybrid_search_keeps_the_per_paper_cap(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    question = f"{RARE} interactions"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    dominant = await add_texts(session, query, "Dominant", [(f"{RARE} note {i}", 0.05 + 0.01 * i) for i in range(8)])
    other = await add_texts(session, query, "Other", [(f"Other chunk {i}", 0.5 + 0.1 * i) for i in range(6)])

    found = await retrieve(
        session, question, paper_ids=[dominant[0].paper_id, other[0].paper_id], k=6, embedder=embedder
    )

    assert Counter(r.paper_id for r in found) == {dominant[0].paper_id: 3, other[0].paper_id: 3}


async def test_hybrid_search_stays_inside_the_chunk_scope(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    question = f"{RARE} interactions"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    chunks = await add_texts(session, query, "Scoped", [("Listed chunk", 0.1), (f"Unlisted {RARE} chunk", 3.0)])

    found = await retrieve(session, question, chunk_ids=[chunks[0].id], k=5, embedder=embedder)

    assert [r.id for r in found] == [chunks[0].id]


def test_hybrid_search_is_off_by_default_and_can_be_switched_on(monkeypatch):
    from app.config import Settings  # noqa: PLC0415

    monkeypatch.delenv("HYBRID_SEARCH", raising=False)

    assert Settings().hybrid_search is False
    assert Settings(hybrid_search=True).hybrid_search is True


async def test_the_stored_switch_changes_what_a_search_across_papers_finds(session, embedder, monkeypatch):
    from app.core import embedding_sources  # noqa: PLC0415

    hybrid(monkeypatch, False)  # the env var off: only the stored switch decides
    question = f"Which dose with {RARE}?"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    near_ones = [(f"Background chunk {i}", 0.1 * (i + 1)) for i in range(6)]
    chunks = await add_texts(session, query, "Label", [*near_ones, (f"Avoid strong inhibitors such as {RARE}.", 3.0)])
    scope = [c.id for c in chunks]

    before = await retrieve(session, question, chunk_ids=scope, k=3, embedder=embedder)
    await embedding_sources.set_hybrid(session, True)
    after = await retrieve(session, question, chunk_ids=scope, k=3, embedder=embedder)

    assert chunks[-1].id not in {r.id for r in before} and chunks[-1].id in {r.id for r in after}


async def test_the_settings_switch_turns_hybrid_search_on_and_the_env_var_still_forces_it(session, monkeypatch):
    from app.core import embedding_sources  # noqa: PLC0415

    monkeypatch.setattr(retrieval.settings, "hybrid_search", False)
    assert await retrieval.hybrid_on(session) is False
    await embedding_sources.set_hybrid(session, True)
    assert await retrieval.hybrid_on(session) is True
    await embedding_sources.set_hybrid(session, False)
    assert await retrieval.hybrid_on(session) is False
    monkeypatch.setattr(retrieval.settings, "hybrid_search", True)  # HYBRID_SEARCH: the evals compare both modes
    assert await retrieval.hybrid_on(session) is True


async def test_hybrid_search_keeps_the_vector_order_among_tied_keyword_matches(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    question = f"{RARE} interactions"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    texts = [f"Chunk {i} mentions {RARE}" if i in (1, 2, 4) else f"Chunk {i} is plain" for i in range(6)]
    chunks = await add_texts(session, query, "Ties", [(t, 0.1 * (i + 1)) for i, t in enumerate(texts)])

    found = await retrieve(session, question, chunk_ids=[c.id for c in chunks], k=6, embedder=embedder)

    # The three matches tie on the keyword score: they rise together, nearest first, ahead of the plain ones.
    assert [r.text for r in found] == [texts[i] for i in (1, 2, 4, 0, 3, 5)]


async def test_hybrid_search_keeps_the_nearest_of_more_tied_matches_than_it_takes(session, embedder, monkeypatch):
    # 50 chunks tie on the keyword score and only 40 keyword candidates are taken: the nearest 40 must be the ones.
    hybrid(monkeypatch, True)
    question = f"{RARE} interactions"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    paper = Paper(title="Many ties", file_path="/many.pdf", status="ready")
    session.add(paper)
    await session.flush()
    # Ids sort the other way round from distance, so a tie cut by id would keep the 40 farthest.
    ids = sorted((uuid.uuid4() for _ in range(60)), reverse=True)
    texts = [(f"Tied {RARE} chunk {i}", 0.1 + 0.01 * i) for i in range(50)] + [("Plain", 5.0)] * 10
    session.add_all(
        Chunk(
            id=ids[i], paper_id=paper.id, ordinal=i, page=1, bbox=[[1, 2, 3, 4]], text=text,
            embedding=at_spread(query, spread), embed_model="test", strategy_ver=1,
        )
        for i, (text, spread) in enumerate(texts)
    )
    await session.commit()

    found = await retrieve(session, question, chunk_ids=ids, k=8, embedder=embedder)

    assert [r.text for r in found] == [f"Tied {RARE} chunk {i}" for i in range(8)]


async def two_paper_scope(session, embedder, question, rare_text):
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question.replace(chr(0), '')}"] = query
    embedder.vectors[f"search_query: {question}"] = query
    near = await add_texts(session, query, "Near", [(f"Background chunk {i}", 0.1 * (i + 1)) for i in range(6)])
    far = await add_texts(session, query, "Far", [(rare_text, 3.0)])
    return near, far


async def test_hybrid_search_covers_a_paper_list_and_a_workspace(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    question = f"Which dose with {RARE}?"
    near, far = await two_paper_scope(session, embedder, question, f"Avoid {RARE}.")
    papers = [near[0].paper_id, far[0].paper_id]
    workspace = Workspace(name=f"W {uuid.uuid4().hex[:6]}")
    session.add(workspace)
    await session.flush()
    await session.execute(insert(workspace_papers), [{"workspace_id": workspace.id, "paper_id": p} for p in papers])
    await session.commit()

    listed = await retrieve(session, question, paper_ids=papers, k=3, embedder=embedder)
    in_workspace = await retrieve(session, question, workspace_id=workspace.id, k=3, embedder=embedder)

    assert far[0].id in {r.id for r in listed} and far[0].id in {r.id for r in in_workspace}


@pytest.mark.parametrize(
    "question",
    [
        f"see https://example.org/{RARE}?a=1&b='2' : (x) | !y",  # URL, quotes and tsquery operators
        "the of and",  # stop words only: no lexeme at all
        "???",
        f"a NUL\x00 byte and {RARE}",  # Postgres refuses 0x00 in text
    ],
)
async def test_hybrid_search_takes_any_question_without_an_error(session, embedder, monkeypatch, question):
    hybrid(monkeypatch, True)
    near, far = await two_paper_scope(session, embedder, question, f"Avoid {RARE}.")
    found = await retrieve(session, question, paper_ids=[near[0].paper_id, far[0].paper_id], k=3, embedder=embedder)
    assert found


async def test_a_long_text_is_searched_by_vectors_alone(session, embedder, monkeypatch):
    # The paper deck sends a whole section: a keyword ranking of 20 000 characters is slow and means nothing.
    hybrid(monkeypatch, True)
    question = f"{RARE} " + "word " * 400
    assert len(question) > retrieval.MAX_HYBRID_CHARS
    near, far = await two_paper_scope(session, embedder, question, f"Avoid {RARE}.")
    found = await retrieve(session, question, paper_ids=[near[0].paper_id, far[0].paper_id], k=3, embedder=embedder)
    assert far[0].id not in {r.id for r in found}


async def test_only_the_rarest_words_of_a_question_are_scored(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    common = [f"common{i}x" for i in range(10)]
    question = " ".join([RARE, *common])
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    shared = " ".join(common)
    near = await add_texts(session, query, "Near", [(f"{shared} chunk {i}", 0.1 * (i + 1)) for i in range(6)])
    far = await add_texts(session, query, "Far", [(f"Avoid {RARE}.", 3.0)])
    papers = [near[0].paper_id, far[0].paper_id]

    monkeypatch.setattr(retrieval, "MAX_TERMS", 50)  # all eleven words: ten shared ones outweigh the rare one
    every_word = await retrieve(session, question, paper_ids=papers, k=3, embedder=embedder)
    monkeypatch.setattr(retrieval, "MAX_TERMS", 1)  # only the rarest
    rarest = await retrieve(session, question, paper_ids=papers, k=3, embedder=embedder)

    assert far[0].id not in {r.id for r in every_word} and rarest[0].id == far[0].id


@pytest.mark.parametrize("hybrid_on", [False, True])
@pytest.mark.parametrize("scope", ["both papers", "whole library"])
async def test_a_wider_search_skips_a_paper_still_embedding(session, embedder, monkeypatch, scope, hybrid_on):
    """A long paper embeds across many jobs, so its first slices sit in the table for hours: they mustn't answer."""
    hybrid(monkeypatch, hybrid_on)
    (a, b), *_ = await seed_papers(session, embedder)
    paper_ids = {"both papers": [a.id, b.id], "whole library": None}[scope]
    a.status = "embedding"
    await session.commit()

    while_embedding = await retrieve(session, QUERY, paper_ids=paper_ids, embedder=embedder)

    assert a.id not in {c.paper_id for c in while_embedding}
    assert b.id in {c.paper_id for c in while_embedding}

    a.status = "ready"
    await session.commit()
    assert a.id in {c.paper_id for c in await retrieve(session, QUERY, paper_ids=paper_ids, embedder=embedder)}


async def test_a_paper_still_embedding_answers_alone_from_keywords_and_its_vectors_so_far(session, embedder):
    """Keywords need no vector, so asked by itself it answers minutes after upload instead of hours."""
    (a, b), chunks, *_ = await seed_papers(session, embedder)
    a.status = "embedding"
    waiting = Chunk(
        paper_id=a.id, ordinal=7, page=8, bbox=[[1, 2, 3, 4]], text="attention works through queries and keys",
        embed_model="test", strategy_ver=1,
    )
    other = Chunk(
        paper_id=b.id, ordinal=7, page=8, bbox=[[1, 2, 3, 4]], text="attention in another paper",
        embed_model="test", strategy_ver=1,
    )
    session.add_all([waiting, other])
    await session.commit()

    found = await retrieve(session, QUERY, paper_ids=[a.id], embedder=embedder)

    assert {c.paper_id for c in found} == {a.id}
    assert waiting.id in {c.id for c in found}  # no vector, found by its words
    assert {c.id for c in chunks if c.paper_id == a.id} & {c.id for c in found}  # the vectors so far count too
    assert all(c.distance is not None for c in found)  # what the MCP tool rounds


async def test_a_ready_paper_with_a_chunk_lacking_a_vector_stays_vector_only(session, embedder):
    (a, _), _, unembedded, _ = await seed_papers(session, embedder)

    found = await retrieve(session, QUERY, paper_ids=[a.id], embedder=embedder)

    assert unembedded.id not in {c.id for c in found}


@pytest.mark.parametrize(("threshold", "found"), [(3, True), (1000, False)])
async def test_a_long_paper_alone_also_searches_its_words(session, embedder, monkeypatch, threshold, found):
    """Inside a long file hybrid answered 28 of 33 fixed questions to vectors' 26; inside a short one it lost recall."""
    monkeypatch.setattr(retrieval, "LONG_PAPER_CHUNKS", threshold)
    hybrid(monkeypatch, False)
    (a, _), *_ = await seed_papers(session, embedder)
    question = "itraconazole dose"
    embedder.vectors[f"search_query: {question}"] = embedder.vectors[f"search_query: {QUERY}"]
    rare = Chunk(
        paper_id=a.id, ordinal=8, page=9, bbox=[[1, 2, 3, 4]], text="itraconazole raises exposure",
        embedding=unit_vector("far from the question"), embed_model="test", strategy_ver=1,
    )
    session.add(rare)
    await session.commit()

    top = await retrieve(session, question, paper_ids=[a.id], k=2, embedder=embedder)

    assert (rare.id in {c.id for c in top}) is found


async def test_a_long_question_on_a_paper_still_embedding_searches_its_first_words(session, embedder):
    """The API allows 2,000 characters; past the hybrid limit it must not end up hiding the paper it's about."""
    (a, _), *_ = await seed_papers(session, embedder)
    a.status = "embedding"
    waiting = Chunk(
        paper_id=a.id, ordinal=7, page=8, bbox=[[1, 2, 3, 4]], text="itraconazole raises exposure",
        embed_model="test", strategy_ver=1,
    )
    session.add(waiting)
    await session.commit()
    question = "itraconazole " + "and more words besides " * 80
    embedder.vectors[f"search_query: {question}"] = embedder.vectors[f"search_query: {QUERY}"]

    found = await retrieve(session, question, paper_ids=[a.id], embedder=embedder)

    assert waiting.id in {c.id for c in found}


NEARER = [(f"Background passage number {i}", 0.1 * (i + 1)) for i in range(4)]  # share no word with the question


async def test_hybrid_ranks_a_word_said_often_above_a_word_said_once(session, embedder, monkeypatch):
    """BM25: on the fixed questions it beat summing each word's weight once, 46 to 45 of 60 unseen ones."""
    hybrid(monkeypatch, True)
    question = f"What about {RARE}?"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    once = f"{RARE} is mentioned here in passing, among many other unrelated drug interactions and warnings."
    often = f"{RARE} raises exposure, so {RARE} needs care, and {RARE} should be avoided in this group of patients."
    # Nearer by vector: `once`. Keyword ties would leave it first.
    chunks = await add_texts(session, query, "Label", [*NEARER, (once, 3.0), (often, 3.1)])

    found = await retrieve(session, question, chunk_ids=[c.id for c in chunks], k=2, embedder=embedder)

    assert [c.text for c in found] == [often, once]


async def test_hybrid_prefers_a_short_chunk_when_both_say_the_word_as_often(session, embedder, monkeypatch):
    hybrid(monkeypatch, True)
    question = f"What about {RARE}?"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    filler = " ".join(f"unrelated{i} words{i}" for i in range(120))
    short, long = f"{RARE} raises exposure.", f"{RARE} raises exposure. {filler}"
    chunks = await add_texts(session, query, "Label", [*NEARER, (long, 3.0), (short, 3.1)])

    found = await retrieve(session, question, chunk_ids=[c.id for c in chunks], k=2, embedder=embedder)

    assert [c.text for c in found] == [short, long]


async def test_words_overrides_the_switch_either_way(session, embedder, monkeypatch):
    question = f"Which dose with {RARE}?"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    near_ones = [(f"Background chunk {i}", 0.1 * (i + 1)) for i in range(6)]
    chunks = await add_texts(session, query, "Label", [*near_ones, (f"Avoid strong inhibitors such as {RARE}.", 3.0)])
    scope = [c.id for c in chunks]

    hybrid(monkeypatch, False)
    forced = await retrieve(session, question, chunk_ids=scope, k=3, embedder=embedder, words=True)
    hybrid(monkeypatch, True)
    held = await retrieve(session, question, chunk_ids=scope, k=3, embedder=embedder, words=False)

    assert chunks[-1].id in {c.id for c in forced}
    assert chunks[-1].id not in {c.id for c in held}


async def test_likely_papers_are_the_ones_with_the_nearest_chunks(session, embedder, monkeypatch):
    monkeypatch.setattr(retrieval, "LIKELY_PAPERS", 2)
    question = "Which paper says it?"
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    papers = [
        (await add_texts(session, query, f"P{i}", [(f"Paper {i} passage {j}", i + 0.1 * (j + 1)) for j in range(3)]))[0]
        for i in range(4)
    ]
    ids = [c.paper_id for c in papers]

    likely = await retrieval.likely_papers(session, question, list(reversed(ids)), embedder=embedder)
    few = await retrieval.likely_papers(session, question, ids[2:], embedder=embedder)

    assert likely == ids[:2]
    assert few == ids[2:]  # no more than LIKELY_PAPERS: all of them, unsearched
