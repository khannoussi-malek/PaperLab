"""What a PDF itself says about its paper (DOI, arXiv id, authors, years), and whether a found record matches it."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.domain.doi import normalize_doi

YEAR_TOLERANCE = 1  # an arXiv preprint and its published version are often dated a year apart

# New-style ("1810.04805") or old-style, pre-2007 ("hep-th/9901001", "math.GT/0309136") IDs, an optional "vN" dropped.
_ARXIV_ID = re.compile(r"arXiv:(\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z-]+)?/\d{7})(?:v\d+)?", re.IGNORECASE)
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


def _split(value: str, separators: re.Pattern) -> list[str]:
    return [part for part in separators.split(value) if part]


def pdf_hints(first_page_text: str, metadata: dict[str, str]) -> PdfHints:
    arxiv = _ARXIV_ID.search(first_page_text)
    created = _PDF_DATE_YEAR.match(metadata.get("creationDate", ""))
    years = {int(created.group(1))} if created else set()
    if arxiv and "/" not in arxiv.group(1):
        years.add(2000 + int(arxiv.group(1)[:2]))  # new-style arXiv IDs start with yymm
    # ponytail: old-style IDs (archive/YYMMNNN) span 1991-2007, so a bare "2000 + yy" would misread them; skip.
    author = metadata.get("author", "")
    return PdfHints(
        doi=normalize_doi(" ".join([metadata.get("subject", ""), metadata.get("keywords", ""), first_page_text])),
        arxiv_id=arxiv.group(1) if arxiv else None,
        years=frozenset(years),
        text=f"{author}\n{first_page_text}",
        authors=_split(author, _AUTHOR_SEPARATORS),
        keywords=_split(metadata.get("keywords", ""), _KEYWORD_SEPARATORS),
    )


_UNICODE_HYPHENS = str.maketrans("‐‑", "--")  # OpenAlex writes "Ming‐Wei" with U+2010


def _fold(text: str) -> str:
    """Casefolded, without accents, ASCII hyphens: "Chabrière‐Smith" and "CHABRIERE-SMITH" compare equal."""
    text = unicodedata.normalize("NFKD", text).translate(_UNICODE_HYPHENS)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _on_page(family: str, hints: PdfHints) -> bool:
    # ponytail: the family name as a whole word on page 1. A name in a non-Latin script never matches: a miss,
    # never a wrong match.
    return bool(family) and re.search(rf"\b{re.escape(_fold(family))}\b", _fold(hints.text)) is not None


def _first_author_matches(work: dict[str, Any], hints: PdfHints) -> bool:
    authorships = work.get("authorships") or []
    names = authorships[0]["author"]["display_name"].split() if authorships else []
    return bool(names) and _on_page(names[-1], hints)


def is_confirmed_match(work: dict[str, Any], hints: PdfHints) -> bool:
    """A title-search hit counts only when its year and its first author agree with the PDF."""
    year = work.get("publication_year")
    if year is None or not any(abs(year - y) <= YEAR_TOLERANCE for y in hints.years):
        return False
    return _first_author_matches(work, hints)
