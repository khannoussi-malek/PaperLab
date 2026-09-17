import pytest
from conftest import recorded_discovery

from app.core.candidates import MAX_AUTHORS, MAX_PDF_URLS, Candidate, from_s2, from_work, with_s2
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
