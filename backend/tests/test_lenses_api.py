"""GET /api/papers/{id}/sections and PUT /api/papers/{id}/section-roles (M16 spec §4.3)."""

import uuid

import pytest
from test_sections import paper_with_headings

from app.main import create_app

pytestmark = pytest.mark.anyio

HEADINGS = [None, "Abstract", "1 Introduction", "2 Method", "3 Results", "References"]


def lens_in(body, lens_id):
    return next(lens for lens in body["lenses"] if lens["id"] == lens_id)


async def test_sections_list_each_section_and_every_lens(client, session):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    ids = [str(c.id) for c in chunks]

    response = await client.get(f"/api/papers/{paper.id}/sections")

    assert response.status_code == 200
    body = response.json()
    assert body["sections"][2] == {
        "title": "1 Introduction",
        "role": "intro",
        "source": "keyword",
        "chunk_ids": [ids[2]],
        "first_chunk_id": ids[2],
        "page": 3,
        "preview": "Text of chunk 2.",
    }
    assert [(s["title"], s["role"]) for s in body["sections"]] == [
        (None, "other"),
        ("Abstract", "abstract"),
        ("1 Introduction", "intro"),
        ("2 Method", "method"),
        ("3 Results", "results"),
        ("References", "back"),
    ]
    assert [lens["id"] for lens in body["lenses"]] == ["full", "key_ideas", "critical", "method", "related"]
    assert lens_in(body, "key_ideas") == {
        "id": "key_ideas",
        "label": "Key ideas",
        "chunk_ids": [ids[1], ids[2]],
        "positional_fallback": False,
        "missing_roles": ["conclusion"],
    }
    assert (lens_in(body, "critical")["chunk_ids"], lens_in(body, "critical")["missing_roles"]) == (
        [ids[3], ids[4]],
        ["limitations"],
    )
    assert (lens_in(body, "related")["chunk_ids"], lens_in(body, "full")["chunk_ids"]) == ([], ids)


async def test_sections_of_an_unknown_paper_is_404(client):
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/sections")).status_code == 404


async def test_a_role_fix_comes_back_at_once_and_automatic_undoes_it(client, session):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    path = f"/api/papers/{paper.id}/section-roles"

    fixed = await client.put(path, json={"section_title": "2 Method", "role": "conclusion"})
    undone = await client.put(path, json={"section_title": "2 Method", "role": None})

    assert fixed.status_code == 200
    assert (fixed.json()["sections"][3]["role"], fixed.json()["sections"][3]["source"]) == ("conclusion", "user")
    assert lens_in(fixed.json(), "key_ideas")["chunk_ids"] == [str(chunks[i].id) for i in (1, 2, 3)]
    assert undone.status_code == 200
    assert (undone.json()["sections"][3]["role"], undone.json()["sections"][3]["source"]) == ("method", "keyword")


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"section_title": "2 Method", "role": "bogus"}, None),
        ({"section_title": "9 Appendix", "role": "back"}, "unknown_section"),
        ({"section_title": "", "role": "back"}, None),
        ({"section_title": "x" * 501, "role": "back"}, None),
        ({"section_title": "2 Method"}, None),  # role is required, even when it is null
    ],
)
async def test_a_role_fix_is_refused_with_422(client, session, body, detail):
    paper, _ = await paper_with_headings(session, HEADINGS)

    response = await client.put(f"/api/papers/{paper.id}/section-roles", json=body)

    assert response.status_code == 422
    if detail is not None:
        assert response.json() == {"detail": detail}


async def test_a_role_fix_on_an_unknown_paper_is_404(client):
    body = {"section_title": "2 Method", "role": "results"}

    assert (await client.put(f"/api/papers/{uuid.uuid4()}/section-roles", json=body)).status_code == 404


def test_the_lens_schemas_are_in_openapi():
    schemas = create_app().openapi()["components"]["schemas"]

    for name in ["SectionsOut", "SectionOut", "LensOut", "SectionRoleIn"]:
        assert name in schemas
