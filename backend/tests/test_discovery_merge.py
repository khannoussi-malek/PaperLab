import pytest

from app.core.candidates import Candidate, from_arxiv, from_core, from_crossref, merge, surname

ARXIV_ENTRY = {
    "arxiv_id": "1706.03762", "title": "Attention Is All You Need", "year": 2017, "doi": None,
    "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"],
}  # fmt: skip
CROSSREF_ITEM = {
    "DOI": "10.18653/V1/N19-1423", "type": "proceedings-article", "is-referenced-by-count": 8811,
    "title": ["BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"],
    "author": [{"given": "Jacob", "family": "Devlin"}, {"name": "Google AI Language"}, {"given": "Ming-Wei"}],
    "issued": {"date-parts": [[2019]]}, "container-title": ["Proceedings of NAACL-HLT"],
}  # fmt: skip
CORE_WORK = {
    "id": 42873602, "title": "Attention Is All\n  You Need", "yearPublished": 2023, "doi": None, "arxivId": None,
    "authors": [{"name": "Uszkoreit, Jakob"}, {"name": "Parmar, Niki"}], "citationCount": 0,
    "downloadUrl": "https://core.ac.uk/download/83868954.pdf", "sourceFulltextUrls": ["https://example.org/landing"],
}  # fmt: skip


def test_an_arxiv_entry_is_a_candidate_with_its_pdf():
    candidate = from_arxiv(ARXIV_ENTRY)

    assert (candidate.arxiv_id, candidate.year, candidate.sources) == ("1706.03762", 2017, ("arxiv",))
    assert candidate.pdf_urls == ["https://arxiv.org/pdf/1706.03762"]


def test_a_crossref_item_is_a_candidate_without_pdf_urls():
    candidate = from_crossref(CROSSREF_ITEM)

    assert candidate.doi == "10.18653/v1/n19-1423"
    assert candidate.authors == ["Jacob Devlin", "Google AI Language", "Ming-Wei"]
    assert (candidate.year, candidate.venue, candidate.cited_by_count) == (2019, "Proceedings of NAACL-HLT", 8811)
    assert (candidate.pdf_urls, candidate.sources) == ([], ("crossref",))


@pytest.mark.parametrize("kind", ["other", "dataset", "peer-review", None])
def test_a_crossref_record_that_is_not_a_paper_is_dropped(kind):
    assert from_crossref({**CROSSREF_ITEM, "type": kind}) is None


def test_a_crossref_item_without_optional_fields_still_maps():
    candidate = from_crossref({"type": "journal-article", "issued": {"date-parts": [[None]]}})

    assert (candidate.title, candidate.year, candidate.doi, candidate.authors) == ("Untitled", None, None, [])


def test_a_core_work_lists_only_its_download_url_and_not_its_citation_count():
    candidate = from_core(CORE_WORK)

    assert (candidate.title, candidate.core_id, candidate.sources) == (
        "Attention Is All You Need",
        "42873602",
        ("core",),
    )
    assert candidate.pdf_urls == ["https://core.ac.uk/download/83868954.pdf"]  # never its landing pages (D68)
    assert candidate.cited_by_count is None  # CORE counts 0 for the 2017 paper


def test_a_core_work_with_an_arxiv_id_drops_its_version():
    candidate = from_core({**CORE_WORK, "arxivId": "1706.03762v5", "downloadUrl": ""})

    assert candidate.pdf_urls == ["https://arxiv.org/pdf/1706.03762"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Uszkoreit, Jakob", "uszkoreit"), ("Jakob Uszkoreit", "uszkoreit"), ("Krönke, Christoph", "kronke"), ("", "")],
)
def test_surname(name, expected):
    assert surname(name) == expected


def found(source: str, **fields) -> Candidate:
    return Candidate(**{"title": "A Paper", "sources": (source,), **fields})


def test_results_sharing_a_doi_arxiv_id_or_source_id_merge_whatever_their_titles():
    merged = merge(
        {
            "openalex": [found("openalex", title="BERT", doi="10.5555/bert", openalex_id="W1")],
            "crossref": [found("crossref", title="BERT: Pre-training", doi="10.5555/BERT")],
            "arxiv": [found("arxiv", title="Other title", arxiv_id="1810.04805", doi="10.48550/arxiv.1810.04805")],
            "core": [found("core", title="Yet another", arxiv_id="1810.04805", core_id="7")],
        },
        limit=20,
    )

    assert [m.sources for m in merged] == [("openalex", "crossref"), ("arxiv", "core")]


def test_the_same_title_merges_only_with_a_shared_surname():
    vaswani = found("arxiv", title="Attention Is All You Need", authors=["Ashish Vaswani", "Jakob Uszkoreit"])
    core_copy = from_core(CORE_WORK)
    core_duplicate = from_core({**CORE_WORK, "id": 391275825})
    kronke = from_core({**CORE_WORK, "id": 144975462, "authors": [{"name": "Krönke, Christoph"}], "downloadUrl": ""})

    merged = merge({"arxiv": [vaswani], "core": [core_copy, kronke, core_duplicate]}, limit=20)

    assert [(m.sources, m.authors[0]) for m in merged] == [
        (("arxiv", "core"), "Ashish Vaswani"),
        (("core",), "Krönke, Christoph"),
    ]


def test_without_authors_the_same_title_needs_the_same_known_year():
    merged = merge(
        {
            "openalex": [found("openalex", title="Deep Learning", year=2015)],
            "crossref": [
                found("crossref", title="deep  learning", year=2015),
                found("crossref", title="Deep Learning"),
            ],
        },
        limit=20,
    )

    assert [m.sources for m in merged] == [("openalex", "crossref"), ("crossref",)]


def test_fields_come_from_the_most_trusted_source_that_has_them():
    [merged] = merge(
        {
            "openalex": [found("openalex", title="BERT", doi="10.5555/bert", venue=None, cited_by_count=10)],
            "crossref": [found("crossref", title="BERT!", doi="10.5555/bert", venue="NAACL", cited_by_count=8811)],
            "arxiv": [
                found("arxiv", doi="10.5555/bert", arxiv_id="1810.04805", pdf_urls=["https://arxiv.org/pdf/1810.04805"])
            ],
            "core": [found("core", doi="10.5555/bert", core_id="9", pdf_urls=["https://core.ac.uk/download/9.pdf"])],
        },
        limit=20,
    )

    assert (merged.title, merged.venue, merged.cited_by_count, merged.core_id) == ("BERT", "NAACL", 8811, "9")
    assert merged.pdf_urls == ["https://arxiv.org/pdf/1810.04805", "https://core.ac.uk/download/9.pdf"]


def test_papers_more_sources_found_come_first_then_the_best_position():
    merged = merge(
        {
            "openalex": [found("openalex", title="Only OpenAlex"), found("openalex", title="Both", doi="10.5555/b")],
            "crossref": [found("crossref", title="Only Crossref"), found("crossref", title="Both", doi="10.5555/b")],
        },
        limit=2,
    )

    assert [m.title for m in merged] == ["Both", "Only OpenAlex"]
