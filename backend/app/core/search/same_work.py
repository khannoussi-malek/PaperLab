"""Whether two records are the same work: matching authors' surnames and titles, and a renamed preprint."""

import re

from app.core.search.candidates import arxiv_from_doi, normal_title, surname
from app.domain.candidates import Candidate

_PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "di", "da", "dos", "du", "la", "le", "ter", "bin"}


def _surname_forms(name: str) -> set[str]:
    """The ways a surname may be written: its last token ("berg") and with its particles ("van der berg")."""
    last = surname(name)
    if "," in name:
        return {last.split()[-1], last} if last else set()
    tokens = [surname(token) for token in name.split()]
    start = len(tokens) - 1
    while start > 0 and tokens[start - 1] in _PARTICLES:
        start -= 1
    return {tokens[-1], " ".join(tokens[start:])} if tokens else set()


def same_work(candidate: Candidate, entry: dict) -> bool:
    """An arXiv entry is the candidate's preprint: the same title word for word; the same first author or at least
    two shared surnames (with no authors on either side, a year within one); and not posted more than a year after
    the paper. A wrong match would ingest another paper, so this is strict."""
    if normal_title(entry["title"]) != normal_title(candidate.title):
        return False
    if None not in (candidate.year, entry["year"]) and entry["year"] > candidate.year + 1:
        return False
    ours, theirs = candidate.authors, entry["authors"]
    if not ours and not theirs:
        return None not in (candidate.year, entry["year"]) and abs(candidate.year - entry["year"]) <= 1
    if not ours or not theirs:
        return False
    their_forms = [_surname_forms(name) for name in theirs]
    if _surname_forms(ours[0]) & their_forms[0]:
        return True
    return sum(any(_surname_forms(name) & forms for forms in their_forms) for name in ours) >= 2


def _title_prefix(title: str) -> str | None:
    """The normalised text before a title's first colon ("real sampling"), when there is one of two words or more."""
    head, colon, _ = title.partition(":")
    # Words split on spaces, so "GPT-4" or "Self-RAG" stays one name, too short to identify a paper.
    return normal_title(head) if colon and len(head.split()) >= 2 else None


_SERIES_PART = re.compile(r"\b(?:part|vol(?:ume)?)\s+(?:[ivx]+|\d+)\b", re.IGNORECASE)


def _initial(name: str) -> str:
    """The first given-name initial, ASCII-folded ("Chang, Haw-Shiuan" and "Haw-Shiuan Chang" give "h"), or ""."""
    given = name.split(",", 1)[1] if "," in name else " ".join(name.split()[:-1])
    return surname(next(iter(given.split()), ""))[:1]


def _same_author(ours: str, theirs: str) -> bool:
    initials = {_initial(ours), _initial(theirs)}
    return bool(_surname_forms(ours) & _surname_forms(theirs)) and ("" in initials or len(initials) == 1)


def _renamed_work(candidate: Candidate, entry: dict) -> bool:
    """An arXiv entry is the preprint of a paper renamed on publication: the same text before the colon (two words or
    more), the same three or more authors in the same order (surname and first initial), the paper published 0 to 2
    years after the preprint, and neither title a part of a series ("Part II"), whose parts share a prefix and authors.
    The title test is looser than same_work's, so the author and year tests are stricter."""
    ours, theirs = candidate.authors, entry["authors"]
    return (
        (prefix := _title_prefix(candidate.title)) is not None
        and prefix == _title_prefix(entry["title"])
        and not any(_SERIES_PART.search(t) for t in (candidate.title, entry["title"]))
        and len(ours) >= 3
        and len(ours) == len(theirs)
        and all(_same_author(a, b) for a, b in zip(ours, theirs))
        and None not in (candidate.year, entry["year"])
        and entry["year"] <= candidate.year <= entry["year"] + 2
    )


def _has_arxiv_id(candidate: Candidate) -> bool:
    return bool(
        candidate.external_ids.get("arxiv")
        or arxiv_from_doi(candidate.doi)
        or any("arxiv.org/" in url for url in candidate.pdf_urls)
    )
