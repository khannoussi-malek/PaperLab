from app.core.enrichment import PdfHints, normalize_doi, pdf_hints

ARXIV_PAGE = "BERT: Pre-training of Deep\nJacob Devlin Ming-Wei Chang\narXiv:1810.04805v2 [cs.CL] 24 May 2019\n"


def test_normalize_doi_accepts_urls_and_prefixes_and_lowercases():
    assert normalize_doi("https://doi.org/10.18653/v1/N19-1423") == "10.18653/v1/n19-1423"
    assert normalize_doi("doi:10.1016/S0140-6736(20)30367-6") == "10.1016/s0140-6736(20)30367-6"
    assert normalize_doi("  10.1000/xyz123  ") == "10.1000/xyz123"


def test_normalize_doi_strips_sentence_punctuation_but_keeps_balanced_parentheses():
    assert normalize_doi("see 10.1000/abc.") == "10.1000/abc"
    assert normalize_doi("(published as 10.1000/abc)") == "10.1000/abc"
    assert normalize_doi("10.1016/s0140-6736(20)30367-6;") == "10.1016/s0140-6736(20)30367-6"


def test_normalize_doi_rejects_text_without_one():
    assert normalize_doi("not a doi") is None
    assert normalize_doi("10.12/too-short-prefix") is None


def test_an_arxiv_first_page_gives_the_arxiv_id_and_its_year():
    hints = pdf_hints(ARXIV_PAGE, {"creationDate": "", "author": "", "keywords": ""})

    assert hints == PdfHints(
        doi=None, arxiv_id="1810.04805", years=frozenset({2018}), text="\n" + ARXIV_PAGE, authors=[], keywords=[]
    )


def test_metadata_gives_doi_year_authors_and_keywords():
    metadata = {
        "subject": "Proc. NAACL, doi:10.18653/v1/N19-1423",
        "author": "Jacob Devlin; Ming-Wei Chang and Kenton Lee",
        "keywords": "language models; pre-training, transformers",
        "creationDate": "D:20190528000751Z",
    }

    hints = pdf_hints("no identifiers on this page", metadata)

    assert hints.doi == "10.18653/v1/n19-1423"
    assert hints.years == {2019}
    assert hints.authors == ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee"]
    assert hints.keywords == ["language models", "pre-training", "transformers"]
    assert "Jacob Devlin" in hints.text


def test_missing_metadata_gives_empty_hints():
    assert pdf_hints("", {}) == PdfHints(doi=None, arxiv_id=None, years=frozenset(), text="\n", authors=[], keywords=[])
