"""Fake PubMed, PMC, Europe PMC, Zenodo, HAL, DOAJ and OpenAIRE answers for the test stack."""

import httpx

from app.providers.discovery_fake_data import PAGE_PAPERS, PAPERS, _page_slice


def _pubmed_article(pmid: str, title: str, doi: str) -> str:
    return (
        f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article>"
        f"<Journal><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal>"
        f"<ArticleTitle>{title}</ArticleTitle>"
        f'<ELocationID EIdType="doi">{doi}</ELocationID>'
        f"<AuthorList><Author><LastName>Fixture</LastName><ForeName>Ada</ForeName></Author></AuthorList>"
        f"</Article></MedlineCitation></PubmedArticle>"
    )


def _pubmed_esearch_response(ids: list[str], count: int) -> httpx.Response:
    return httpx.Response(200, json={"esearchresult": {"count": str(count), "idlist": ids}})


def _pubmed_efetch_response(entries: list[tuple[str, str, str]]) -> httpx.Response:
    articles = "".join(_pubmed_article(pmid, title, doi) for pmid, title, doi in entries)
    return httpx.Response(
        200, text=f"<PubmedArticleSet>{articles}</PubmedArticleSet>", headers={"content-type": "application/xml"}
    )


# PMIDs are fabricated positionally, in two disjoint ranges so a request's own `id` list says which fixture
# set (PAPERS, for the one-shot ask flow, or PAGE_PAPERS, for a search_page pagination test) it belongs to —
# offset well clear of the other fixtures' own ids (core_id 900000s, s2 paperId hex 1-3, arxiv 10000s above).
_PMID_BASE = 800_000       # PAPERS[0..2] -> 800000..800002
_PAGE_PMID_BASE = 810_000  # PAGE_PAPERS[0..2] -> 810000..810002
FREE_PUBMED_ID = str(_PMID_BASE)  # PAPERS[0]'s own pmid — mirrors FREE_ARXIV_ID above


def _pubmed_handle(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/esearch.fcgi"):
        retmax = int(request.url.params["retmax"])
        # Unlike arxiv.py's plain search() (which sends no `start` at all, letting _arxiv_handle tell the two
        # cases apart by presence alone), pubmed.search() and search_page() both always send retstart/retmax
        # — so this tells them apart by size instead: the one-shot ask flow always asks PER_SOURCE=10 (> the
        # 3-item PAPERS fixture), while every pagination test in this file deliberately uses page_size=2 (this
        # file's own documented convention). Never call pubmed.search()/search_page() with a limit/page_size
        # that straddles len(PAPERS)==3 in a new test, or this stops being able to tell them apart.
        if retmax < len(PAPERS):  # a direct search_page() pagination test in this file (page_size=2)
            offset = int(request.url.params["retstart"])
            items = _page_slice(offset, retmax)
            ids = [str(_PAGE_PMID_BASE + offset + i) for i in range(len(items))]
            return _pubmed_esearch_response(ids, len(PAGE_PAPERS))
        ids = [str(_PMID_BASE + i) for i in range(len(PAPERS))]
        return _pubmed_esearch_response(ids, len(PAPERS))
    ids = request.url.params["id"].split(",")
    if int(ids[0]) >= _PAGE_PMID_BASE:
        offset = int(ids[0]) - _PAGE_PMID_BASE
        items = _page_slice(offset, len(ids))
        return _pubmed_efetch_response([(pmid, title, doi) for pmid, (title, doi) in zip(ids, items)])
    return _pubmed_efetch_response([(str(_PMID_BASE + i), title, doi) for i, (title, doi, _) in enumerate(PAPERS)])


# PMC shares PubMed's exact esearch/efetch request shape (just db=pmc) and so mirrors _pubmed_handle almost
# line for line below -- own id bases, offset past PubMed's 800000/810000, so fixture ids never collide.
_PMC_PMID_BASE = 820_000       # PAPERS[0..2] -> 820000..820002
_PAGE_PMC_PMID_BASE = 830_000  # PAGE_PAPERS[0..2] -> 830000..830002
FREE_PMC_ID = str(_PMC_PMID_BASE)


def _pmc_article(pmcid: str, title: str, doi: str) -> str:
    return (
        f'<article><front><article-meta>'
        f'<article-id pub-id-type="pmcid">PMC{pmcid}</article-id>'
        f'<article-id pub-id-type="doi">{doi}</article-id>'
        f"<title-group><article-title>{title}</article-title></title-group>"
        f"<pub-date><year>2026</year></pub-date>"
        f'<contrib-group><contrib contrib-type="author">'
        f"<name><surname>Fixture</surname><given-names>Ada</given-names></name></contrib></contrib-group>"
        f"</article-meta></front></article>"
    )


def _pmc_efetch_response(entries: list[tuple[str, str, str]]) -> httpx.Response:
    articles = "".join(_pmc_article(pmcid, title, doi) for pmcid, title, doi in entries)
    return httpx.Response(
        200, text=f"<pmc-articleset>{articles}</pmc-articleset>", headers={"content-type": "application/xml"}
    )


def _pmc_handle(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/esearch.fcgi"):
        retmax = int(request.url.params["retmax"])
        if retmax < len(PAPERS):  # a direct search_page() pagination test (page_size=2), same convention as PubMed
            offset = int(request.url.params["retstart"])
            items = _page_slice(offset, retmax)
            ids = [str(_PAGE_PMC_PMID_BASE + offset + i) for i in range(len(items))]
            return _pubmed_esearch_response(ids, len(PAGE_PAPERS))
        ids = [str(_PMC_PMID_BASE + i) for i in range(len(PAPERS))]
        return _pubmed_esearch_response(ids, len(PAPERS))
    ids = request.url.params["id"].split(",")
    if int(ids[0]) >= _PAGE_PMC_PMID_BASE:
        offset = int(ids[0]) - _PAGE_PMC_PMID_BASE
        items = _page_slice(offset, len(ids))
        return _pmc_efetch_response([(pmcid, title, doi) for pmcid, (title, doi) in zip(ids, items)])
    return _pmc_efetch_response([(str(_PMC_PMID_BASE + i), title, doi) for i, (title, doi, _) in enumerate(PAPERS)])


# Europe PMC is structurally simpler: one request per page, no esearch/efetch split, and its cursorMark is an
# opaque string token (not an offset) -- this fake mints its own cursorMark values (just the next offset as a
# string) since it's the only side that ever has to read them back.
_EUROPE_PMC_ID_BASE = 840_000       # PAPERS[0..2] -> 840000..840002
_PAGE_EUROPE_PMC_ID_BASE = 850_000  # PAGE_PAPERS[0..2] -> 850000..850002
FREE_EUROPE_PMC_ID = str(_EUROPE_PMC_ID_BASE)


def _europe_pmc_result(ext_id: int, title: str, doi: str) -> dict:
    return {
        "pmid": str(ext_id),
        "title": title,
        "authorList": {"author": [{"fullName": "Ada Fixture"}]},
        "pubYear": "2026",
        "doi": doi,
        "citedByCount": 3,
    }


def _europe_pmc_handle(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    page_size = int(params["pageSize"])
    cursor_mark = params["cursorMark"]
    if page_size < len(PAPERS):  # a direct search_page() pagination test (page_size=2), same convention as PubMed
        offset = 0 if cursor_mark == "*" else int(cursor_mark)
        items = _page_slice(offset, page_size)
        results = [
            _europe_pmc_result(_PAGE_EUROPE_PMC_ID_BASE + offset + i, title, doi)
            for i, (title, doi) in enumerate(items)
        ]
        body: dict = {"hitCount": len(PAGE_PAPERS), "resultList": {"result": results}}
        next_offset = offset + page_size
        if next_offset < len(PAGE_PAPERS):
            body["nextCursorMark"] = str(next_offset)
        return httpx.Response(200, json=body)
    results = [_europe_pmc_result(_EUROPE_PMC_ID_BASE + i, title, doi) for i, (title, doi, _) in enumerate(PAPERS)]
    return httpx.Response(200, json={"hitCount": len(PAPERS), "resultList": {"result": results}})


# Zenodo is one-step like Europe PMC, but paginates with a 1-based `page` number (not an offset) and signals
# "is there more" via links.next's presence, same as zenodo.py's own search_page() -- own id bases, offset past
# Europe PMC's 840000/850000, so fixture ids never collide with any other source's.
_ZENODO_ID_BASE = 860_000       # PAPERS[0..2] -> 860000..860002
_PAGE_ZENODO_ID_BASE = 870_000  # PAGE_PAPERS[0..2] -> 870000..870002
FREE_ZENODO_ID = str(_ZENODO_ID_BASE)


def _zenodo_hit(record_id: int, title: str, doi: str, pdf_url: str | None) -> dict:
    files = [{"key": "paper.pdf", "links": {"self": pdf_url}}] if pdf_url else []
    return {
        "id": record_id,
        "doi": doi,
        "metadata": {
            "title": title,
            "creators": [{"name": "Ada Fixture"}],
            "publication_date": "2026-01-05",
            "description": "An overview of fixtures.",
        },
        "files": files,
    }


def _zenodo_handle(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    size = int(params["size"])
    if size < len(PAPERS):  # a direct search_page() pagination test (page_size=2), same convention as PubMed
        page = int(params["page"])
        offset = (page - 1) * size
        items = _page_slice(offset, size)
        hits = [
            _zenodo_hit(_PAGE_ZENODO_ID_BASE + offset + i, title, doi, None) for i, (title, doi) in enumerate(items)
        ]
        body: dict = {"hits": {"hits": hits}}
        if offset + size < len(PAGE_PAPERS):
            body["links"] = {"next": "https://zenodo.org/api/records?page=2"}
        return httpx.Response(200, json=body)
    hits = [_zenodo_hit(_ZENODO_ID_BASE + i, title, doi, pdf_url) for i, (title, doi, pdf_url) in enumerate(PAPERS)]
    return httpx.Response(200, json={"hits": {"hits": hits}})


# HAL shares PubMed/PMC's exact offset shape (0-based start/rows), just with Solr field-list values instead of
# XML -- own id bases, offset past Zenodo's 860000/870000, so fixture ids never collide with any other source's.
_HAL_ID_BASE = 880_000       # PAPERS[0..2] -> 880000..880002
_PAGE_HAL_ID_BASE = 890_000  # PAGE_PAPERS[0..2] -> 890000..890002
FREE_HAL_ID = str(_HAL_ID_BASE)


def _hal_doc(docid: int, title: str, doi: str, pdf_url: str | None) -> dict:
    return {
        "docid": str(docid),
        "title_s": [title],
        "abstract_s": ["An overview of fixtures."],
        "authFullName_s": ["Ada Fixture"],
        "doiId_s": doi,
        "producedDate_s": "2026-01-05",
        "files_s": [pdf_url] if pdf_url else [],
    }


def _hal_handle(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    rows = int(params["rows"])
    start = int(params["start"])
    if rows < len(PAPERS):  # a direct search_page() pagination test (page_size=2), same convention as PubMed
        items = _page_slice(start, rows)
        docs = [_hal_doc(_PAGE_HAL_ID_BASE + start + i, title, doi, None) for i, (title, doi) in enumerate(items)]
        return httpx.Response(200, json={"response": {"numFound": len(PAGE_PAPERS), "docs": docs}})
    docs = [_hal_doc(_HAL_ID_BASE + i, title, doi, pdf_url) for i, (title, doi, pdf_url) in enumerate(PAPERS)]
    return httpx.Response(200, json={"response": {"numFound": len(PAPERS), "docs": docs}})


# DOAJ is one-step like Zenodo, with a 1-based page cursor and a "next" key presence signal, same as
# doaj.py's own search_page() -- own id bases, offset past HAL's 880000/890000.
_DOAJ_ID_BASE = 900_000       # PAPERS[0..2] -> 900000..900002, zero-padded to doaj's own 32-hex id shape
_PAGE_DOAJ_ID_BASE = 910_000  # PAGE_PAPERS[0..2] -> 910000..910002
FREE_DOAJ_ID = f"{_DOAJ_ID_BASE:032d}"


def _doaj_article(article_id: int, title: str, doi: str, pdf_url: str | None) -> dict:
    links = [{"content_type": "pdf", "type": "fulltext", "url": pdf_url}] if pdf_url else []
    return {
        "id": f"{article_id:032d}",
        "bibjson": {
            "title": title, "year": "2026", "author": [{"name": "Ada Fixture"}],
            "identifier": [{"id": doi, "type": "doi"}], "link": links,
        },
    }


def _doaj_handle(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    page_size = int(params["pageSize"])
    page = int(params["page"])
    if page_size < len(PAPERS):  # a direct search_page() pagination test, same convention as PubMed
        offset = (page - 1) * page_size
        items = _page_slice(offset, page_size)
        results = [
            _doaj_article(_PAGE_DOAJ_ID_BASE + offset + i, title, doi, None) for i, (title, doi) in enumerate(items)
        ]
        body: dict = {"total": len(PAGE_PAPERS), "page": page, "results": results}
        if offset + page_size < len(PAGE_PAPERS):
            body["next"] = f"https://doaj.org/api/v4/search/articles/x?page={page + 1}"
        return httpx.Response(200, json=body)
    results = [_doaj_article(_DOAJ_ID_BASE + i, title, doi, pdf_url) for i, (title, doi, pdf_url) in enumerate(PAPERS)]
    return httpx.Response(200, json={"total": len(PAPERS), "page": 1, "results": results})


# OpenAIRE is one-step with a 1-based page cursor and a numFound-based "more" signal, same as
# openaire.py's own search_page() -- own id bases, offset past DOAJ's 900000/910000.
_OPENAIRE_ID_BASE = 920_000       # PAPERS[0..2] -> 920000..920002
_PAGE_OPENAIRE_ID_BASE = 930_000  # PAGE_PAPERS[0..2] -> 930000..930002
FREE_OPENAIRE_ID = f"openaire____::{_OPENAIRE_ID_BASE:032d}"


def _openaire_record(record_id: str, title: str, doi: str) -> dict:
    return {
        "id": record_id, "type": "publication", "mainTitle": title,
        "descriptions": ["An overview of fixtures."], "pids": [{"scheme": "doi", "value": doi}],
        "authors": [{"fullName": "Ada Fixture"}], "publicationDate": "2026-01-05",
        "instances": [{"urls": [f"https://doi.org/{doi}"]}],
    }


def _openaire_handle(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    page_size = int(params["pageSize"])
    page = int(params["page"])
    if page_size < len(PAPERS):  # a direct search_page() pagination test, same convention as PubMed
        offset = (page - 1) * page_size
        items = _page_slice(offset, page_size)
        results = [
            _openaire_record(f"openaire____::{_PAGE_OPENAIRE_ID_BASE + offset + i:032d}", title, doi)
            for i, (title, doi) in enumerate(items)
        ]
        body = {"header": {"numFound": len(PAGE_PAPERS), "page": page, "pageSize": page_size}, "results": results}
        return httpx.Response(200, json=body)
    results = [
        _openaire_record(f"openaire____::{_OPENAIRE_ID_BASE + i:032d}", title, doi)
        for i, (title, doi, _) in enumerate(PAPERS)
    ]
    body = {"header": {"numFound": len(PAPERS), "page": 1, "pageSize": 20}, "results": results}
    return httpx.Response(200, json=body)
