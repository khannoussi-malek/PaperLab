"""Reading an OpenAlex work: the paper's fields, bibliographic details, published version and topics."""

from typing import Any

from app.domain.doi import normalize_doi
from app.domain.source_types import ARXIV_DOI_PREFIX, PREPRINT_SERVERS, source_type_of


def short_id(url: str | None) -> str | None:
    """ "https://openalex.org/W2963341956" -> "W2963341956"; also strips "https://orcid.org/"."""
    return url.rsplit("/", 1)[-1] if url else None


def abstract_text(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    return " ".join(word for _, word in sorted((i, word) for word, places in inverted_index.items() for i in places))


def work_fields(work: dict[str, Any]) -> dict[str, Any]:
    """The papers columns an OpenAlex work fills."""
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    best_oa = work.get("best_oa_location") or {}
    fields = {
        "openalex_id": short_id(work["id"]),
        "doi": normalize_doi(work.get("doi") or ""),
        "title": work.get("title"),
        "abstract": abstract_text(work.get("abstract_inverted_index")),
        "authors": [a["author"]["display_name"] for a in work.get("authorships") or []],
        "year": work.get("publication_year"),
        "venue": source.get("display_name") or location.get("raw_source_name"),
        "issn": source.get("issn_l"),
        "type": work.get("type"),
        "is_retracted": bool(work.get("is_retracted")),
        "oa_status": (work.get("open_access") or {}).get("oa_status"),
        "oa_url": best_oa.get("pdf_url") or best_oa.get("landing_page_url"),
        "cited_by_count": work.get("cited_by_count"),
        "referenced_works_count": work.get("referenced_works_count"),
    }
    return fields


def openalex_biblio(work: dict[str, Any]) -> dict[str, str | None]:
    """volume, issue, pages, pmid and pmcid (bare ids) of an OpenAlex work. Not in `work_fields`: these six columns are
    fill-only (see `fill_biblio`)."""
    biblio = work.get("biblio") or {}
    ids = work.get("ids") or {}
    pages = "-".join(dict.fromkeys(p for p in (biblio.get("first_page"), biblio.get("last_page")) if p))
    return {
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "pages": pages or None,
        "pmid": short_id((ids.get("pmid") or "").rstrip("/")),
        "pmcid": short_id((ids.get("pmcid") or "").rstrip("/")),
    }


BIBLIO_FIELDS = ("volume", "issue", "pages", "editors", "pmid", "pmcid")
PUBLISHED_TYPES = frozenset({"article", "conference-paper", "proceedings-article", "book-chapter"})


def openalex_published(work: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(published_doi, published_venue, source_type) when the work is a published version: a non-arXiv DOI, a
    published type (or a publishedVersion location) and a primary source that is no preprint server."""
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    venue = source.get("display_name") or location.get("raw_source_name")
    doi = normalize_doi(work.get("doi") or "")
    published = location.get("version") == "publishedVersion" or (work.get("type") or "").lower() in PUBLISHED_TYPES
    if not doi or doi.startswith(ARXIV_DOI_PREFIX) or not published:
        return None, None, None
    if source.get("type") == "repository" or (venue and PREPRINT_SERVERS.search(venue)):
        return None, None, None
    return doi, venue, source_type_of(work.get("type"), doi)


def work_topics(work: dict[str, Any]) -> dict[str, float]:
    """OpenAlex topics, keywords and concepts by label. A label in more than one list keeps its best score."""
    scores: dict[str, float] = {}
    for item in [*(work.get("topics") or []), *(work.get("keywords") or []), *(work.get("concepts") or [])]:
        scores[item["display_name"]] = max(scores.get(item["display_name"], 0.0), item["score"])
    return scores
