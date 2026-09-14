"""Paper metadata from three sources, in rising precedence: the PDF, OpenAlex, the user.

- Never fatal: a paper with no OpenAlex match, or with OpenAlex unreachable, stays fully usable.
- A stored OpenAlex ID, a DOI or an arXiv ID is trusted. A title-search hit is accepted only when its year (±1) and
  its first author agree with the PDF.
- Authors are keyed on OpenAlex IDs, never on names. Author details are refetched only after 30 days.
- A field the user corrected (papers.manual_fields) is never overwritten by the PDF or by OpenAlex.
"""

import re
from dataclasses import dataclass

_DOI = re.compile(r"10\.\d{4,9}/\S+")
_ARXIV_ID = re.compile(r"arXiv:(\d{4}\.\d{4,5})", re.IGNORECASE)
_PDF_DATE_YEAR = re.compile(r"D:(\d{4})")
# ponytail: splits "A; B and C" and "A, B". A "Family, Given" author field becomes two names; the user can correct it.
_AUTHOR_SEPARATORS = re.compile(r"\s*(?:;|,|\band\b)\s*")
_KEYWORD_SEPARATORS = re.compile(r"\s*[;,]\s*")


@dataclass(frozen=True)
class PdfHints:
    doi: str | None
    arxiv_id: str | None
    years: frozenset[int]  # years the PDF suggests: its arXiv ID's year and its creation date's year
    text: str  # the embedded author field and page 1's text, where a match's first author must appear
    authors: list[str]  # the embedded author field, split into names
    keywords: list[str]  # the embedded keywords: the author's own topic labels


def normalize_doi(value: str) -> str | None:
    """The first DOI in `value`, lowercased (DOIs are case-insensitive), or None."""
    match = _DOI.search(value)
    if match is None:
        return None
    doi = match.group().rstrip(".,;").lower()
    # A DOI may contain parentheses ("s0140-6736(20)30367-6"); only an unbalanced closing one is prose.
    return doi[:-1] if doi.endswith(")") and doi.count(")") > doi.count("(") else doi


def _split(value: str, separators: re.Pattern) -> list[str]:
    return [part for part in separators.split(value) if part]


def pdf_hints(first_page_text: str, metadata: dict[str, str]) -> PdfHints:
    arxiv = _ARXIV_ID.search(first_page_text)
    created = _PDF_DATE_YEAR.match(metadata.get("creationDate", ""))
    years = {int(created.group(1))} if created else set()
    if arxiv:
        years.add(2000 + int(arxiv.group(1)[:2]))  # new-style arXiv IDs start with yymm
    author = metadata.get("author", "")
    return PdfHints(
        doi=normalize_doi(" ".join([metadata.get("subject", ""), metadata.get("keywords", ""), first_page_text])),
        arxiv_id=arxiv.group(1) if arxiv else None,
        years=frozenset(years),
        text=f"{author}\n{first_page_text}",
        authors=_split(author, _AUTHOR_SEPARATORS),
        keywords=_split(metadata.get("keywords", ""), _KEYWORD_SEPARATORS),
    )
