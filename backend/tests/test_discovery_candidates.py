import pytest
from conftest import recorded_discovery

from app.core.candidates import (
    MAX_AUTHORS,
    MAX_PDF_URLS,
    Candidate,
    from_arxiv,
    from_core,
    from_crossref,
    from_s2,
    from_work,
    merge,
    with_s2,
)
from app.core.discovery import classify_query
from app.schemas.discovery import CandidateIn, CandidateOut


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("10.18653/v1/N19-1423", ("doi", "10.18653/v1/n19-1423")),
        ("https://doi.org/10.18653/v1/N19-1423", ("doi", "10.18653/v1/n19-1423")),
        ("doi: 10.1038/s41586-021-03819-2.", ("doi", "10.1038/s41586-021-03819-2")),
        ("10.48550/arXiv.1810.04805", ("arxiv", "1810.04805")),
        ("1810.04805", ("arxiv", "1810.04805")),
        ("arXiv:1810.04805v2", ("arxiv", "1810.04805")),
        ("https://arxiv.org/abs/2411.18021v1", ("arxiv", "2411.18021")),
        ("https://arxiv.org/pdf/2411.18021.pdf", ("arxiv", "2411.18021")),
        ("hep-th/9901001", ("arxiv", "hep-th/9901001")),
        ("math.GT/0309136", ("arxiv", "math.gt/0309136")),
        ("W2963341956", ("openalex", "W2963341956")),
        ("https://openalex.org/w2963341956", ("openalex", "W2963341956")),
        ("  BERT:   pre-training\n of transformers ", ("title", "BERT: pre-training of transformers")),
    ],
    ids=[
        "doi", "doi-url", "doi-with-label-and-period", "arxiv-doi", "arxiv", "arxiv-prefixed-versioned",
        "arxiv-abs-url", "arxiv-pdf-url", "old-arxiv", "old-arxiv-subject-class", "openalex", "openalex-url", "title",
    ],
)  # fmt: skip
def test_classify_query(query, expected):
    assert classify_query(query) == expected


def test_a_published_paper_without_a_free_copy_in_openalex_has_no_pdf_urls():
    bert = recorded_discovery("openalex_search_bert")["results"][0]

    candidate = from_work(bert)

    assert candidate.title.startswith("BERT")
    assert candidate.doi == "10.18653/v1/n19-1423"
    assert candidate.openalex_id == "W2963341956"
    assert candidate.arxiv_id is None
    assert candidate.pdf_urls == []  # its OA landing page is not a PDF link (D68)
    assert candidate.authors[0] == "Jacob Devlin"
    assert candidate.year == 2019


def test_an_arxiv_preprint_takes_its_id_from_its_doi_and_lists_its_pdf_once():
    candidate = from_work(recorded_discovery("openalex_work_arxiv_preprint"))

    assert candidate.arxiv_id == "2411.18021"
    assert candidate.pdf_urls == ["https://arxiv.org/pdf/2411.18021"]


def test_an_arxiv_location_gives_a_published_paper_its_arxiv_pdf_first():
    work = {
        "id": "https://openalex.org/W1",
        "title": "A paper",
        "doi": "https://doi.org/10.1000/pub",
        "best_oa_location": {
            "pdf_url": "https://publisher.example/pub.pdf",
            "landing_page_url": "https://publisher.example/pub",
        },
        "locations": [
            {"pdf_url": "https://publisher.example/pub.pdf", "landing_page_url": "https://publisher.example/pub"},
            {"pdf_url": None, "landing_page_url": "http://arxiv.org/abs/2003.07000v2"},
            {"pdf_url": "https://repository.example/copy.pdf", "landing_page_url": None},
            {"pdf_url": "ftp://old.example/copy.pdf", "landing_page_url": None},
        ],
        "open_access": {"oa_url": "https://publisher.example/pub"},
    }

    candidate = from_work(work)

    assert candidate.arxiv_id == "2003.07000"
    assert candidate.pdf_urls == [
        "https://arxiv.org/pdf/2003.07000",
        "https://publisher.example/pub.pdf",
        "https://repository.example/copy.pdf",
    ]


def test_a_work_missing_optional_fields_still_maps():
    candidate = from_work({"title": None, "primary_location": {"source": None}})

    assert candidate == Candidate(title="Untitled", sources=("openalex",))


def test_semantic_scholar_papers_build_the_arxiv_pdf_even_when_their_pdf_link_is_empty():
    papers = recorded_discovery("s2_recommend_bert")["recommendedPapers"]
    arxiv_only = next(p for p in papers if p["externalIds"].get("ArXiv") and not p["openAccessPdf"]["url"])

    candidate = from_s2(arxiv_only)

    assert candidate.arxiv_id == arxiv_only["externalIds"]["ArXiv"]
    assert candidate.pdf_urls == [f"https://arxiv.org/pdf/{candidate.arxiv_id}"]
    assert candidate.s2_id == arxiv_only["paperId"]
    assert candidate.authors == [a["name"] for a in arxiv_only["authors"]]


def test_semantic_scholar_dois_are_lowercased():
    candidate = from_s2({"paperId": "a" * 40, "title": "T", "externalIds": {"DOI": "10.1109/ASIANCON.2024.1"}})

    assert candidate.doi == "10.1109/asiancon.2024.1"
    assert candidate.pdf_urls == []


def test_semantic_scholar_adds_the_arxiv_copy_openalex_lacks():
    bert = from_work(recorded_discovery("openalex_search_bert")["results"][0])
    [s2_bert, _] = recorded_discovery("s2_batch_bert")

    candidate = with_s2(bert, s2_bert)

    assert candidate.arxiv_id == "1810.04805"
    assert candidate.pdf_urls[0] == "https://arxiv.org/pdf/1810.04805"
    assert candidate.s2_id == s2_bert["paperId"]
    assert (candidate.title, candidate.doi, candidate.openalex_id) == (bert.title, bert.doi, bert.openalex_id)


def test_no_semantic_scholar_record_leaves_the_candidate_as_it_is():
    bert = from_work(recorded_discovery("openalex_search_bert")["results"][0])

    assert with_s2(bert, None) is bert


# --- MAX_PDF_URLS / MAX_AUTHORS caps (the API's Add rejects a candidate over either) ---


def test_more_than_ten_pdf_locations_cap_at_ten_in_d68_order():
    work = {
        "id": "https://openalex.org/W1",
        "title": "A widely deposited paper",
        "locations": [{"pdf_url": f"https://repo.example/{i}.pdf"} for i in range(15)],
    }

    candidate = from_work(work)

    assert candidate.pdf_urls == [f"https://repo.example/{i}.pdf" for i in range(MAX_PDF_URLS)]


def test_more_than_500_authors_from_openalex_cap_at_500():
    work = {
        "id": "https://openalex.org/W1",
        "title": "A large collaboration",
        "authorships": [{"author": {"display_name": f"Author {i}"}} for i in range(600)],
    }

    candidate = from_work(work)

    assert len(candidate.authors) == MAX_AUTHORS
    assert candidate.authors[0] == "Author 0"
    assert candidate.authors[-1] == f"Author {MAX_AUTHORS - 1}"


def test_more_than_500_authors_from_semantic_scholar_cap_at_500():
    paper = {"paperId": "a" * 40, "title": "T", "authors": [{"name": f"Author {i}"} for i in range(600)]}

    candidate = from_s2(paper)

    assert len(candidate.authors) == MAX_AUTHORS


def _recorded_openalex_works():
    yield from recorded_discovery("openalex_search_bert")["results"]
    yield recorded_discovery("openalex_work_arxiv_preprint")


def _recorded_s2_papers():
    yield from (paper for paper in recorded_discovery("s2_batch_bert") if paper)
    yield recorded_discovery("s2_paper_arxiv_bert")
    yield from recorded_discovery("s2_recommend_bert")["recommendedPapers"]


@pytest.mark.parametrize(
    "candidate",
    [from_work(work) for work in _recorded_openalex_works()] + [from_s2(paper) for paper in _recorded_s2_papers()],
)
def test_every_recorded_candidate_round_trips_through_the_api_schemas(candidate):
    dumped = CandidateOut.model_validate(candidate, from_attributes=True).model_dump(mode="json")

    CandidateIn.model_validate(dumped)


def test_openalex_abstract_is_reconstructed_from_the_inverted_index():
    # OpenAlex never gives plain abstract text, only a word -> positions map (abstract_text, app/core/enrichment.py,
    # already used for library-paper enrichment; reused here for search candidates).
    work = {
        "title": "A paper",
        "primary_location": {"source": None},
        "abstract_inverted_index": {"BERT": [0], "is": [1], "a": [2], "model.": [3]},
    }
    assert from_work(work).abstract == "BERT is a model."


def test_openalex_abstract_is_none_when_the_index_is_absent():
    assert from_work({"title": "A paper", "primary_location": {"source": None}}).abstract is None


def test_semantic_scholar_abstract_maps_straight_through():
    paper = {"title": "A paper", "abstract": "A study of something interesting."}
    assert from_s2(paper).abstract == "A study of something interesting."


def test_core_abstract_maps_straight_through():
    work = {"id": 1, "title": "A paper", "abstract": "A study of something else."}
    assert from_core(work).abstract == "A study of something else."


def test_crossref_never_surfaces_an_abstract():
    """Crossref's own `abstract` field (when present) is raw JATS XML markup, not plain text — deliberately
    never read, so a candidate from this source never shows tags to the reader."""
    item = {"type": "journal-article", "title": ["A paper"], "abstract": "<jats:p>Some markup.</jats:p>"}
    assert from_crossref(item).abstract is None


def test_merge_keeps_the_abstract_from_the_most_trusted_source_that_has_one():
    """merge()'s trust order follows paper_sources.SOURCES (D73): openalex, crossref, semantic_scholar, arxiv,
    core. An OpenAlex record with no abstract should still pick up S2's, not lose it because OpenAlex ran first."""
    openalex_candidate = Candidate(title="Shared Paper", doi="10.1/shared", sources=("openalex",), abstract=None)
    s2_candidate = Candidate(title="Shared Paper", doi="10.1/shared", sources=("semantic_scholar",), abstract="The real abstract.")

    [merged] = merge({"openalex": [openalex_candidate], "semantic_scholar": [s2_candidate]}, limit=10)

    assert merged.abstract == "The real abstract."
