"""M40 Task 5: the with-files zip and notes in the citation export."""

import io
import re
import uuid
import zipfile

import pytest
from sqlalchemy import insert

from app.models import Chunk, Note, Paper, note_anchors, note_papers

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

RUN = uuid.uuid4().hex[:8]
PDF = b"%PDF-1.4 fake body"


async def seed(client, session, tmp_path):
    ws = (await client.post("/api/workspaces", json={"name": f"Bundle {RUN}"})).json()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(PDF)
    with_pdf = Paper(title=f"Zeta {RUN}", file_path=str(pdf), page_count=3, year=2020, authors=["Jane Smith"])
    no_pdf = Paper(title=f"Omega {RUN}", file_path=str(tmp_path / "gone.pdf"), page_count=3, year=2021,
                   authors=["Jane Smith"])  # fmt: skip
    session.add_all([with_pdf, no_pdf])
    await session.commit()
    for p in (with_pdf, no_pdf):
        await client.put(f"/api/workspaces/{ws['id']}/papers/{p.id}")
    chunk_row = Chunk(
        paper_id=with_pdf.id, ordinal=0, page=7, bbox=[[1, 2, 3, 4]], text="t", embed_model="m", strategy_ver=1
    )
    session.add(chunk_row)
    await session.flush()
    chunk = chunk_row.id
    quoted = Note(body="Key claim\nsecond line", provenance="llm")
    plain = Note(body="Just a thought", provenance="human")
    session.add_all([quoted, plain])
    await session.flush()
    await session.execute(
        insert(note_papers).values([{"note_id": n.id, "paper_id": with_pdf.id} for n in (quoted, plain)])
    )
    await session.execute(
        insert(note_anchors).values(
            note_id=quoted.id,
            paper_id=with_pdf.id,
            page=7,
            bbox=[[1, 2, 3, 4]],
            quoted_text="verbatim quote",
            chunk_id=chunk,
        )  # fmt: skip
    )
    await session.commit()
    return ws, with_pdf, no_pdf, chunk


def open_zip(response):
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(response.content))


@pytest.mark.parametrize("fmt, ext", [("bibtex", "bib"), ("ris", "ris")])
async def test_zip_layout_and_refs_point_at_files_in_the_zip(client, session, tmp_path, fmt, ext):
    ws, with_pdf, _, _ = await seed(client, session, tmp_path)
    response = await client.get(f"/api/workspaces/{ws['id']}/citations.zip", params={"format": fmt})
    zf = open_zip(response)
    assert f'filename="bundle-{RUN}.zip"' in response.headers["content-disposition"]
    assert sorted(zf.namelist()) == sorted([f"PaperLab export.{ext}", "files/smith2020zeta.pdf"])
    assert zf.read("files/smith2020zeta.pdf") == PDF
    refs = zf.read(f"PaperLab export.{ext}").decode()
    pointers = re.findall(r"files/\S+?\.pdf", refs)
    assert pointers == ["files/smith2020zeta.pdf"]  # the paper without a PDF gets no pointer
    assert all(p in zf.namelist() for p in pointers)
    assert ("file = {files/smith2020zeta.pdf}" if fmt == "bibtex" else "L1  - files/smith2020zeta.pdf") in refs
    assert f"Omega {RUN}" in refs and "annote" not in refs and "N1  - Just" not in refs  # notes are opt-in
    await client.delete(f"/api/workspaces/{ws['id']}")


async def test_notes_in_ris_one_n1_per_note_with_quote_page_label_and_link(client, session, tmp_path):
    ws, p, _, chunk = await seed(client, session, tmp_path)
    ris = (
        open_zip(
            await client.get(f"/api/workspaces/{ws['id']}/citations.zip", params={"format": "ris", "notes": "true"})
        )
        .read("PaperLab export.ris")
        .decode()
    )
    n1 = [line for line in ris.splitlines() if line.startswith("N1  - ")]
    quoted = next(line for line in n1 if "Key claim" in line)
    assert "AI" in quoted and "p. 7" in quoted and "verbatim quote" in quoted
    assert f"paperlab://papers/{p.id}?page=7&chunk={chunk}" in quoted and "\n" not in quoted
    plain = next(line for line in n1 if "Just a thought" in line)
    assert "You" in plain and f"paperlab://papers/{p.id}" in plain
    await client.delete(f"/api/workspaces/{ws['id']}")


async def test_notes_in_bibtex_annote_joined_by_a_blank_line(client, session, tmp_path):
    ws, p, _, chunk = await seed(client, session, tmp_path)
    response = await client.get(f"/api/workspaces/{ws['id']}/citations", params={"format": "bibtex", "notes": "true"})
    assert response.status_code == 200
    annote = response.text.split("annote = {")[1].split("\n    }")[0] if "annote = {" in response.text else ""
    assert annote, response.text
    assert "AI" in annote and "p. 7" in annote and "verbatim quote" in annote and "Just a thought" in annote
    assert "\n\n" in annote and f"paperlab://papers/{p.id}?page=7\\&chunk={chunk}" in annote
    plain = await client.get(f"/api/workspaces/{ws['id']}/citations", params={"format": "bibtex"})
    assert "annote" not in plain.text and "Just a thought" not in plain.text
    ris = await client.get(f"/api/workspaces/{ws['id']}/citations", params={"format": "ris", "notes": "true"})
    assert "N1  - " in ris.text and "Just a thought" in ris.text
    await client.delete(f"/api/workspaces/{ws['id']}")


async def test_zip_errors(client, session, tmp_path):
    assert (await client.get(f"/api/workspaces/{uuid.uuid4()}/citations.zip?format=ris")).status_code == 404
    ws, *_ = await seed(client, session, tmp_path)
    for fmt in ("apa", "csljson", "nonsense"):
        bad = await client.get(f"/api/workspaces/{ws['id']}/citations.zip", params={"format": fmt})
        assert bad.status_code == 422, fmt
    await client.delete(f"/api/workspaces/{ws['id']}")


async def test_a_pdf_that_vanishes_mid_build_gets_no_attachment(client, session, tmp_path, monkeypatch):
    ws, *_ = await seed(client, session, tmp_path)

    def gone(self, filename, *args, **kwargs):
        raise FileNotFoundError(filename)

    monkeypatch.setattr(zipfile.ZipFile, "write", gone)
    zf = open_zip(await client.get(f"/api/workspaces/{ws['id']}/citations.zip", params={"format": "bibtex"}))
    assert zf.namelist() == ["PaperLab export.bib"] and "file = {" not in zf.read("PaperLab export.bib").decode()
    await client.delete(f"/api/workspaces/{ws['id']}")
