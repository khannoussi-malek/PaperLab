"""Read Zotero exports (M40 Task 6, I1): BibTeX (Zotero and Better BibTeX), RIS and CSL-JSON into `ImportEntry`s.
Parsing only, no database. The file is never trusted: 20 MB, 5,000 entries, and any parse error raises
`CitationsImportError` (plain message) before anything is created. The inverse of `citations_export`."""

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from pylatexenc.latex2text import LatexNodes2Text

from app.core.citations.citations_import_html import html_to_markdown
from app.core.search.candidates import ARXIV_ID, arxiv_from_doi
from app.domain.doi import normalize_doi

logger = logging.getLogger(__name__)

MAX_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 5000
YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d|21\d\d)\b")
ARXIV_LINE = re.compile(rf"^\s*arxiv:\s*({ARXIV_ID})(?:v\d+)?", re.IGNORECASE | re.MULTILINE)
ARXIV_URL = re.compile(rf"arxiv\.org/(?:abs|pdf)/({ARXIV_ID})(?:v\d+)?", re.IGNORECASE)
PMID_LINE = re.compile(r"^\s*pmid:\s*(\d+)", re.IGNORECASE | re.MULTILINE)
PMCID_LINE = re.compile(r"^\s*pmcid:\s*(PMC\d+)", re.IGNORECASE | re.MULTILINE)
# What PaperLab's own export writes into a note; reading it back as a note would duplicate the metadata.
_OWN_PART = (
    r"(?:source: (?:journal article|proceedings|book|chapter|preprint|magazine|thesis|other)"
    r"|(?:not )?peer-reviewed|(?:full text|abstract only|metadata only) in paperlab)"
)
OWN_NOTE = re.compile(
    rf"(?:preprint\. )?{_OWN_PART}(?: \u00b7 {_OWN_PART})*|arxiv: \S+|pmid: \d+|pmcid: PMC\d+"
    r"|published version: .*https://doi\.org/\S+",
    re.IGNORECASE,
)
# Longest text a field may have before LaTeX decoding (pylatexenc is superlinear); the file limit is 20 MB.
BIG_FIELDS = {"abstract": 100_000, "annote": 100_000}
LONG_FIELDS = {"author": 50_000, "editor": 50_000, "file": 50_000, "keywords": 50_000, "keyword": 50_000,
               "note": 50_000, "collections": 50_000}  # fmt: skip
FIELD_MAX = 2_000
SUFFIX = re.compile(r"(Jr\.?|Sr\.?|II|III|IV)", re.IGNORECASE)
LATEX = LatexNodes2Text(math_mode="verbatim")


class CitationsImportError(Exception):
    """A file that can't be imported; the message is plain and meant for the user."""


@dataclass(frozen=True)
class ImportEntry:
    title: str
    authors: list[str] = field(default_factory=list)  # "Given Family"; an organisation stays whole
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    issn: str | None = None
    abstract: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    editors: list[str] = field(default_factory=list)
    source_type: str = "other"
    tags: list[str] = field(default_factory=list)
    collection: str | None = None
    notes: list[str] = field(default_factory=list)  # markdown
    files: list[str] = field(default_factory=list)  # paths as written in the file


# ---- shared helpers ----


def _tex(text: str | None) -> str:
    """LaTeX to Unicode with the protective braces gone."""
    if not text:
        return ""
    text = re.sub(r"\\textless\b\s*(\{\})?", "<", text)
    text = re.sub(r"\\textgreater\b\s*(\{\})?", ">", text)
    return unicodedata.normalize("NFC", " ".join(LATEX.latex_to_text(text).replace("\xa0", " ").split()))


def _tex_block(text: str) -> str:
    """Like _tex, per line, so a plain-text note keeps its line breaks."""
    return "\n".join(_tex(line) for line in text.split("\n")).strip()


def _check_sizes(label: str, values: dict[str, str | None]) -> None:
    for key, value in values.items():
        limit = BIG_FIELDS.get(key) or LONG_FIELDS.get(key) or FIELD_MAX
        if value and len(value) > limit:
            raise CitationsImportError(f"The {key} of {label} is too long to import, so nothing was imported.")


def _split_top(text: str, pattern: str) -> list[str]:
    """Split on `pattern` outside braces."""
    depth, masked = 0, []
    for ch in text:
        depth += (ch == "{") - (ch == "}" and depth > 0)
        masked.append("_" if depth > 0 or ch == "}" else ch)
    parts, start = [], 0
    for m in re.finditer(pattern, "".join(masked), re.IGNORECASE):
        parts.append(text[start : m.start()])
        start = m.end()
    return [*parts, text[start:]]


def _join_name(family: str, given: str, suffix: str = "") -> str:
    return " ".join(p for p in (given, family, suffix) if p)


def _person(raw: str) -> str:
    """A BibTeX/RIS name -> "Given Family". `{World Health Organization}` and a one-word name stay whole."""
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}") and len(_split_top(raw, r"\s")) == 1:
        return _tex(raw)
    parts = [_tex(p) for p in _split_top(raw, ",")]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return _join_name(parts[0], parts[1])
    family, middle, last = parts[0], parts[1], ", ".join(parts[2:])
    if SUFFIX.fullmatch(middle):  # "Family, Jr., Given"
        return _join_name(family, last, middle)
    if SUFFIX.fullmatch(last):  # "Family, Given, Jr."
        return _join_name(family, middle, last)
    return _join_name(family, f"{middle} {last}")


def _names(value: str | None) -> list[str]:
    names = (_person(n) for n in _split_top(value or "", r"\s+and\s+") if n.strip() and n.strip() != "others")
    return [n for n in names if n]


def _year(value) -> int | None:
    match = YEAR.search(str(value or ""))
    return int(match.group(1)) if match else None


def _pages(value: str | None) -> str | None:
    return re.sub(r"\s*(?:--|[-–—])+\s*", "-", value).strip() or None if value else None


def _doi(value: str | None) -> str | None:
    return normalize_doi(re.sub(r"\\([_%&#$])", r"\1", value)) if value else None


def _arxiv(raw: str | None) -> str | None:
    match = re.fullmatch(rf"(?:arxiv:)?\s*({ARXIV_ID})(?:v\d+)?", (raw or "").strip(), re.IGNORECASE)
    return match.group(1) if match else None


def _first(pattern: re.Pattern, *texts: str | None) -> str | None:
    for text in texts:
        if match := pattern.search(text or ""):
            return match.group(1)
    return None


def _split_words(value: str | None) -> list[str]:
    return [w.strip() for w in re.split(r"[,;]", _tex(value)) if w.strip()]


def _note(text: str) -> str | None:
    """A child note as markdown, or None when it is only the metadata PaperLab's own export writes."""
    markdown = html_to_markdown(text)
    lines = [ln for ln in markdown.split("\n") if ln.strip()]
    return None if not lines or all(OWN_NOTE.fullmatch(ln.strip()) for ln in lines) else markdown


def _build(title: str, source_type: str, extra: str = "", url: str | None = None, **values) -> ImportEntry:
    """One entry: the shared identifier rules (DOI, arXiv id from eprint, a URL, Extra or an arXiv DOI)."""
    doi = _doi(values.pop("doi", None)) or _doi(url if "doi.org/" in (url or "") else None)
    arxiv = _arxiv(values.pop("arxiv_id", None)) or _first(ARXIV_LINE, extra) or _first(ARXIV_URL, url)
    arxiv = arxiv or arxiv_from_doi(doi)
    if source_type == "other" and arxiv:
        source_type = "preprint"
    publisher = values.pop("publisher", None)
    venue = values.pop("venue", None) or (publisher if source_type == "preprint" else None)
    return ImportEntry(
        title=title, source_type=source_type, doi=doi, arxiv_id=arxiv, venue=venue or None,
        pmid=values.pop("pmid", None) or _first(PMID_LINE, extra),
        pmcid=values.pop("pmcid", None) or _first(PMCID_LINE, extra), **values,
    )  # fmt: skip


def _decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise CitationsImportError("This file is larger than 20 MB, which is more than PaperLab imports at once.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CitationsImportError("This file isn't UTF-8 text. Export it from Zotero again as UTF-8.") from None


def _check_count(entries: list) -> None:
    if not entries:
        raise CitationsImportError("No references were found in this file.")
    if len(entries) > MAX_ENTRIES:
        raise CitationsImportError(
            "This file has more than 5,000 references, which is more than PaperLab imports at once."
        )


# ---- BibTeX ----


# ---- RIS ----


# ---- CSL-JSON ----


# ---- entry point ----


