from app.core.enrichment import PdfHints, normalize_doi, pdf_hints
from app.providers.extraction import extract

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


def test_normalize_doi_strips_unbalanced_trailing_brackets():
    # Fix round 1, finding 1: a citation-list "[3] ... doi:X]" left a trailing "]" on the DOI.
    assert normalize_doi("[3] Some Ref, doi:10.1000/abc]") == "10.1000/abc"
    assert normalize_doi("(see doi:10.1000/abc).") == "10.1000/abc"
    assert normalize_doi("[3] 10.1000/abc],") == "10.1000/abc"


def test_pdf_hints_finds_old_style_arxiv_ids():
    # Fix round 1, finding 2: pre-2007 arXiv IDs ("archive/YYMMNNN") weren't matched at all.
    hints = pdf_hints("See arXiv:hep-th/9901001v2 for details", {})
    assert hints.arxiv_id == "hep-th/9901001"


def test_pdf_hints_from_a_real_extraction_finds_the_printed_doi(doi_pdf):
    # Fix round 1, finding 4: the extraction -> hints seam, using a real extracted PDF instead of hand-written text.
    doc = extract(doi_pdf)
    assert pdf_hints(doc.first_page_text, doc.metadata).doi == "10.18653/v1/n19-1423"


def test_pdf_hints_from_a_real_extraction_finds_the_arxiv_id(arxiv_pdf):
    doc = extract(arxiv_pdf)
    assert pdf_hints(doc.first_page_text, doc.metadata).arxiv_id == "1810.04805"


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
