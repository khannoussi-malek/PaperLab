"""M40 Task 6: read Zotero exports (BibTeX, Better BibTeX, RIS, CSL-JSON). Parsing only, no database."""

import json
from pathlib import Path

import pytest

from app.core.citations_import import MAX_BYTES, MAX_ENTRIES, CitationsImportError, parse
from app.core.citations_import_html import html_to_markdown

FIX = Path(__file__).parent / "fixtures" / "zotero"


def load(name: str):
    return parse(name, (FIX / name).read_bytes())


def test_zotero7_bibtex():
    journal, preprint, conf = load("zotero7.bib")
    assert journal.title == "The DNA of Café Culture"  # Review Focus 1
    assert journal.authors == ["Jane A. Smith", "Hans Müller", "World Health Organization"]
    assert (journal.year, journal.venue, journal.volume, journal.issue) == (2020, "Journal of Things", "12", "3")
    assert (journal.pages, journal.issn, journal.doi) == ("45-67", "1234-5678", "10.1234/abc.2020.1")
    assert journal.abstract == "We study DNA & coffee."
    assert journal.source_type == "journal_article" and journal.tags == ["coffee", "genetics"]
    assert journal.files == [
        "files/101/Smith et al. - 2020 - The DNA of Café Culture.pdf",
        "files/102/snap.html",
    ]
    assert journal.notes == ["A **key** idea."]
    assert preprint.arxiv_id == "2406.07735" and preprint.source_type == "preprint"
    assert preprint.authors == ["Anna van der Berg", "John Doe"] and preprint.venue == "arXiv"
    assert conf.source_type == "proceedings" and conf.venue == "Proceedings of the Big Conference"
    assert conf.authors == ["Kim Lee", "Min Park Jr."] and conf.editors == ["Richard Roe"]
    assert conf.pages == "1-9"


def test_better_bibtex():
    article, book = load("better-bibtex.bib")
    assert article.title == "The DNA of Café Culture" and article.authors[1] == "Hans Müller"
    assert (article.year, article.venue, article.arxiv_id) == (2020, "Journal of Things", "2406.07735")
    assert article.files == ["/Users/me/Zotero/storage/ABCD1234/Smith 2020.pdf"]
    assert article.collection == "Reading list" and article.tags == ["coffee"]
    assert book.source_type == "book"
    assert book.files == ["C:/Users/me/Doe.pdf", "/Users/me/doe-notes.pdf"]


def test_ris():
    journal, chapter = load("zotero.ris")
    assert journal.authors == ["Jane A. Smith", "Hans Müller"] and journal.year == 2020
    assert (journal.venue, journal.volume, journal.issue, journal.pages) == ("Journal of Things", "12", "3", "45-67")
    assert journal.doi == "10.1234/abc.2020.1" and journal.issn == "1234-5678"
    assert journal.tags == ["coffee", "genetics"] and journal.files == ["files/101/Smith.pdf"]
    assert journal.notes == ["A **key** idea."]  # the PMID line is an identifier, not a note
    assert journal.pmid == "123456"
    assert chapter.source_type == "chapter" and chapter.editors == ["Richard Roe"]


def test_csl_json():
    journal, preprint = load("zotero.json")
    assert journal.authors == ["Jane A. Smith", "Anna van der Berg", "World Health Organization"]
    assert (journal.year, journal.pages, journal.doi) == (2020, "45-67", "10.1234/abc.2020.1")
    assert (journal.pmid, journal.pmcid, journal.editors) == ("123456", "PMC789", ["Richard Roe"])
    assert preprint.source_type == "preprint" and preprint.arxiv_id == "2406.07735"
    assert preprint.doi == "10.48550/arxiv.2406.07735"


def test_extra_arxiv_line():
    data = json.dumps([{"type": "article", "title": "T", "note": "arXiv: 2406.07735\nSource: preprint"}]).encode()
    assert parse("x.json", data)[0].arxiv_id == "2406.07735"


def test_format_is_sniffed_without_an_extension():
    assert parse("export", (FIX / "zotero.ris").read_bytes())[0].volume == "12"
    assert parse("export.txt", (FIX / "zotero7.bib").read_bytes())[0].volume == "12"
    assert parse("export", (FIX / "zotero.json").read_bytes())[0].volume == "12"


def test_html_to_markdown():
    html = (
        "<div><h2>Notes</h2><p>one<br>two <em>x</em> <i>y</i> <a href='https://a.org/p'>link</a> "
        "<a href='javascript:alert(1)'>bad</a><script>alert(1)</script></p>"
        "<ul><li>a</li><li>b</li></ul><ol><li>c</li></ol><blockquote>quoted</blockquote><span>t</span></div>"
    )
    assert html_to_markdown(html) == (
        "## Notes\n\none\ntwo *x* *y* [link](https://a.org/p) bad\n\n- a\n- b\n\n1. c\n\n> quoted\n\nt"
    )


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("a.bib", b"@article{k, title={x}\n"),
        ("a.bib", b"@article{k, title={x}}\n@article{k, title={y}}\n"),
        ("a.json", b"[{not json"),
        ("a.json", b'{"a": 1}'),
        ("a.json", b'[{"type": "book"}]'),
        ("a.ris", b"hello"),
        ("a.ris", b"TY  - JOUR\nTI  - no end\n"),
        ("a.txt", b"just words"),
        ("a.bib", b""),
        ("a.bib", b"\xff\xfe\x00bad"),
    ],
)
def test_broken_files_give_a_plain_error(name, data):
    with pytest.raises(CitationsImportError) as err:
        parse(name, data)
    assert "Traceback" not in str(err.value) and str(err.value)


def test_limits():
    with pytest.raises(CitationsImportError, match="20 MB"):
        parse("a.bib", b" " * (MAX_BYTES + 1))
    many = json.dumps([{"type": "book", "title": f"t{i}"} for i in range(MAX_ENTRIES + 1)]).encode()
    with pytest.raises(CitationsImportError, match="5,000"):
        parse("a.json", many)
    ok = json.dumps([{"type": "book", "title": f"t{i}"} for i in range(MAX_ENTRIES)]).encode()
    assert len(parse("a.json", ok)) == MAX_ENTRIES


def test_files_in_every_form():
    bib = (
        b"@book{a, title={T}, file={Full Text PDF:files/1/a b.pdf:application/pdf;"
        b":/abs/x.pdf:application/pdf;C\\:/Win/y.pdf:application/pdf;Snap:C:\\Win\\z.pdf;plain.pdf}}"
    )
    assert parse("a.bib", bib)[0].files == [
        "files/1/a b.pdf", "/abs/x.pdf", "C:/Win/y.pdf", "C:\\Win\\z.pdf", "plain.pdf",
    ]  # fmt: skip


def test_papers_own_export_notes_are_not_read_back_as_notes():
    ris = b"TY  - JOUR\nTI  - T\nN1  - Source: journal article\nN1  - arXiv: 2406.07735\nN1  - mine\nER  - \n"
    entry = parse("a.ris", ris)[0]
    assert entry.notes == ["mine"] and entry.arxiv_id == "2406.07735"
