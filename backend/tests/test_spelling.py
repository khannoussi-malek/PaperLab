"""UK and US spellings meet in the keyword index (migration 0081): `haemodialysis` in a label, `hemodialysis` in a
question. The english stemmer alone keeps them apart (RAG report 2026-11-22, apixaban q05)."""

import uuid
from collections import Counter

import pytest
from conftest import unit_vector
from sqlalchemy import text
from test_retrieval import add_texts, hybrid

from app.core.chat.retrieval import retrieve

pytestmark = pytest.mark.anyio

PAIRS = [
    ("haemodialysis", "hemodialysis"), ("anaemia", "anemia"), ("hyperglycaemia", "hyperglycemia"),
    ("paediatric", "pediatric"), ("orthopaedic", "orthopedic"), ("oedema", "edema"), ("oesophageal", "esophageal"),
    ("oestrogen", "estrogen"), ("foetal", "fetal"), ("diarrhoea", "diarrhea"), ("coeliac", "celiac"),
    ("randomised", "randomized"), ("organisation", "organization"), ("optimising", "optimizing"),
    ("analysed", "analyzed"), ("dialyse", "dialyze"), ("behaviour", "behavior"), ("tumours", "tumors"),
    ("favourite", "favorite"), ("centre", "center"), ("fibres", "fibers"), ("millilitre", "milliliter"),
    ("catalogue", "catalog"), ("dialogues", "dialogs"), ("defence", "defense"), ("licence", "license"),
    ("programme", "program"),
]
# Short words the rules must leave alone: each would land on another word, or on a stopword and vanish.
UNTOUCHED = ["four", "your", "hour", "rise", "wise", "vogue", "genre", "entre", "does", "toe", "shoes"]


async def lexemes(session, word: str) -> str:
    return await session.scalar(text("SELECT to_tsvector('english', spelling_us(:w))::text"), {"w": word})


@pytest.mark.parametrize(("uk", "us"), PAIRS)
async def test_a_uk_spelling_indexes_like_the_us_one(session, uk, us):
    assert await lexemes(session, uk) == await lexemes(session, us)
    assert await lexemes(session, uk.capitalize()) == await lexemes(session, us)


@pytest.mark.parametrize("word", UNTOUCHED)
async def test_short_lookalikes_are_left_alone(session, word):
    assert await session.scalar(text("SELECT spelling_us(:w)"), {"w": word}) == word


async def test_the_stored_column_uses_the_us_spelling(session, embedder):
    query = unit_vector(uuid.uuid4().hex)
    [chunk] = await add_texts(session, query, "UK label", [("Dose in haemodialysis and paediatric patients", 0.1)])

    stored = await session.scalar(text("SELECT tsv::text FROM chunks WHERE id = :id"), {"id": chunk.id})

    assert "'hemodialysi'" in stored and "'pediatr'" in stored


@pytest.mark.parametrize(("asked", "written"), [("hemo", "haemo"), ("haemo", "hemo")])
async def test_either_spelling_finds_the_other_by_its_words(session, embedder, monkeypatch, asked, written):
    hybrid(monkeypatch, True)
    # One unique word, so no other test's chunk matches it; digits, so its prefix holds no spelling rule's letters.
    question = f"x{uuid.uuid4().int % 10**12}{asked}dialysis dose"
    word = question.split()[0]
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {question}"] = query
    near = await add_texts(session, query, "Near", [(f"Unrelated chunk {i}", 0.1 + 0.05 * i) for i in range(3)])
    far = await add_texts(session, query, "Far", [(f"{word.replace(asked, written)} is in this one", 1.5)])

    found = await retrieve(session, question, paper_ids=[near[0].paper_id, far[0].paper_id], k=4, embedder=embedder)

    assert found[0].id == far[0].id
    assert Counter(r.paper_id for r in found)[near[0].paper_id] == 3
