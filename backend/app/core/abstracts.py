"""Whether a stored abstract is an abstract. Some records hold the paper's citation instead (D44 saw this in OpenAlex),
and a model judging "Yining Lu, Dixuan Wang… Proceedings of the 2025 Conference… 2025." rates the paper off-topic."""

import re

_MAX_CITATION_CHARS = 400
_VENUE = re.compile(
    r"\b(proceedings|conference|symposium|workshop|transactions|journal|vol\.|volume|pp\.|pages|press|publisher|issn|isbn)\b",
    re.IGNORECASE,
)
_ENDS_IN_YEAR = re.compile(r"\b(?:19|20)\d\d[a-z]?\s*[.)]?\s*$")
_AUTHOR_LIST = re.compile(r"^(?:[A-Z][\w.'-]+(?: [A-Z][\w.'-]+){1,3}, ){1,}[A-Z][\w.'-]+(?: [A-Z][\w.'-]+){1,3}\. ")
_PROSE = re.compile(
    r"\b(we|this paper|this study|this article|our|results?|proposed?|proposes|presents?|shows?|is|are|was|were)\b",
    re.IGNORECASE,
)


def is_citation_only(text: str | None) -> bool:
    """Authors and venue with no sentence about the work. Tried on 4,379 short abstracts in a real library: 89 matched,
    and a sample of them were all citations or publisher boilerplate.

    ponytail: English markers; a citation in another language still counts as an abstract."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > _MAX_CITATION_CHARS or not _VENUE.search(stripped) or _PROSE.search(stripped):
        return False
    return bool(_AUTHOR_LIST.search(stripped) or _ENDS_IN_YEAR.search(stripped))


def usable_abstract(text: str | None) -> str | None:
    """The abstract, or None when there is none to judge a paper by."""
    stripped = (text or "").strip()
    return None if not stripped or is_citation_only(stripped) else stripped
