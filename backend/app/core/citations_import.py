"""Read Zotero exports (M40 Task 6, I1): BibTeX (Zotero and Better BibTeX), RIS and CSL-JSON into `ImportEntry`s.
Parsing only, no database. The file is never trusted: 20 MB, 5,000 entries, and any parse error raises
`CitationsImportError` (plain message) before anything is created. The inverse of `citations_export`."""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field

import bibtexparser
import rispy
from pylatexenc.latex2text import LatexNodes2Text

from app.core.candidates import ARXIV_ID, arxiv_from_doi
from app.core.citations_import_html import html_to_markdown
from app.core.enrichment import normalize_doi

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
# RIS and CSL keys checked under the BibTeX limit of another name; any other key is checked as itself (FIELD_MAX).
RIS_LIMITS = {"notes": "note", "urls": "file", "file_attachments1": "file", "authors": "author name",
              "first_authors": "author name", "secondary_authors": "editor name"}  # fmt: skip
CSL_LIMITS = {"author": "author name", "editor": "editor name", "keyword": "keywords", "URL": "file"}
SUFFIX = re.compile(r"(Jr\.?|Sr\.?|II|III|IV)", re.IGNORECASE)
MIME_TAIL = re.compile(r":(?:application|text|image|audio|video)/[\w.+-]+$")
DRIVE = re.compile(r"[A-Za-z]:[\\/]")
LATEX = LatexNodes2Text(math_mode="verbatim")
BIBTEX_TYPES = {
    "article": "journal_article", "inproceedings": "proceedings", "conference": "proceedings",
    "proceedings": "proceedings", "book": "book", "booklet": "book", "incollection": "chapter",
    "inbook": "chapter", "phdthesis": "thesis", "mastersthesis": "thesis", "thesis": "thesis",
}  # fmt: skip
RIS_TYPES = {
    "JOUR": "journal_article", "JFULL": "journal_article", "MGZN": "magazine", "CONF": "proceedings",
    "CPAPER": "proceedings", "BOOK": "book", "EBOOK": "book", "CHAP": "chapter", "ECHAP": "chapter",
    "THES": "thesis", "PPRINT": "preprint", "UNPB": "preprint",
}  # fmt: skip
CSL_TYPES = {
    "article-journal": "journal_article", "paper-conference": "proceedings", "book": "book", "chapter": "chapter",
    "article": "preprint", "article-magazine": "magazine", "article-newspaper": "magazine", "thesis": "thesis",
}  # fmt: skip


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


def _bibtex_files(raw: str | None) -> list[str]:
    """Zotero `Title:path:mime` items, Better BibTeX `:path:mime` and bare paths, separated by `;`."""
    colon = "\x00"
    paths = []
    for item in _split_top((raw or "").replace("\\:", colon).replace("\\;", "\x01"), r";"):
        item = MIME_TAIL.sub("", item.strip())
        if not DRIVE.match(item):
            item = item.split(":", 1)[-1]  # drop "Title:" (empty in Better BibTeX's ":path:mime")
        path = item.replace(colon, ":").replace("\x01", ";").strip()
        if path:
            paths.append(path)
    return paths


def _bibtex_entry(entry) -> ImportEntry:
    f = {x.key.lower(): x.value for x in entry.fields}
    label = f"the BibTeX entry '{entry.key}'"
    _check_sizes(label, f)
    if not (title := _tex(f.get("title"))):
        raise CitationsImportError(f"The BibTeX entry '{entry.key}' has no title, so nothing was imported.")
    source_type = BIBTEX_TYPES.get(entry.entry_type.lower(), "other")
    extra = _tex(f.get("note"))
    notes = [n for n in (_note(_tex_block(f["annote"])),) if n] if f.get("annote") else []
    arxiv = f.get("eprint") if f.get("archiveprefix", f.get("eprinttype", "arxiv")).lower() == "arxiv" else None
    return _build(
        title, source_type, extra=extra, url=f.get("url"),
        authors=_names(f.get("author")), editors=_names(f.get("editor")), year=_year(f.get("year") or f.get("date")),
        venue=_tex(f.get("journal") or f.get("journaltitle") or f.get("booktitle")) or None,
        publisher=_tex(f.get("publisher")) or None, doi=f.get("doi"), arxiv_id=arxiv,
        pmid=f.get("pmid"), pmcid=f.get("pmcid"), issn=f.get("issn"), abstract=_tex(f.get("abstract")) or None,
        volume=_tex(f.get("volume")) or None, issue=_tex(f.get("number") or f.get("issue")) or None,
        pages=_pages(_tex(f.get("pages"))), tags=_split_words(f.get("keywords") or f.get("keyword")),
        collection="; ".join(_split_words(f.get("collections"))) or None, notes=notes,
        files=_bibtex_files(f.get("file")),
    )  # fmt: skip


def _parse_bibtex(text: str) -> list[ImportEntry]:
    library = bibtexparser.parse_string(text)
    if library.failed_blocks:
        block = library.failed_blocks[0]
        key = getattr(block, "key", None)
        where = f"the entry '{key}' (a repeated key)" if key else f"the entry at line {block.start_line + 1}"
        raise CitationsImportError(f"This BibTeX file has {where} that PaperLab can't read, so nothing was imported.")
    _check_count(library.entries)
    return [_bibtex_entry(e) for e in library.entries]


# ---- RIS ----


def _as_list(value) -> list[str]:
    return [value] if isinstance(value, str) else [str(v) for v in value or []]


def _ris_entry(r: dict, number: int) -> ImportEntry:
    label = f"reference #{number} in this RIS file"
    if not (title := r.get("title") or r.get("primary_title")):
        raise CitationsImportError(f"The {label} has no title, so nothing was imported.")
    for key, value in r.items():
        for item in _as_list(value):
            _check_sizes(label, {RIS_LIMITS.get(key, key.replace("_", " ")): item})
    texts = _as_list(r.get("notes")) + _as_list(r.get("note"))
    page = _pages("-".join(p for p in (r.get("start_page"), r.get("end_page")) if p))
    return _build(
        title, RIS_TYPES.get(r.get("type_of_reference", ""), "other"), extra="\n".join(texts),
        url=" ".join(_as_list(r.get("urls"))),
        authors=[_person(n) for n in _as_list(r.get("authors")) + _as_list(r.get("first_authors"))],
        editors=[_person(n) for n in _as_list(r.get("secondary_authors"))],
        year=_year(r.get("year") or r.get("publication_year") or r.get("date")),
        venue=r.get("secondary_title") or r.get("journal_name") or r.get("alternate_title3"),
        publisher=r.get("publisher"), doi=r.get("doi"), issn=r.get("issn"), abstract=r.get("abstract"),
        volume=r.get("volume"), issue=r.get("number"), pages=page,
        tags=[k.strip() for k in _as_list(r.get("keywords")) if k.strip()],
        notes=[n for t in texts if (n := _note(t))], files=_as_list(r.get("file_attachments1")),
    )  # fmt: skip


def _parse_ris(text: str) -> list[ImportEntry]:
    starts, ends = len(re.findall(r"^TY  - ", text, re.M)), len(re.findall(r"^ER  -", text, re.M))
    if not starts or starts != ends:
        raise CitationsImportError("This RIS file looks cut off or isn't RIS, so nothing was imported.")
    try:
        records = rispy.loads(text, skip_unknown_tags=True)
    except Exception:  # noqa: BLE001 - rispy raises assorted errors on malformed lines; the user gets one plain message
        raise CitationsImportError("PaperLab couldn't read this RIS file, so nothing was imported.") from None
    _check_count(records)
    return [_ris_entry(r, n) for n, r in enumerate(records, 1)]


# ---- CSL-JSON ----


def _s(value) -> str | None:
    """A CSL value as text: the first item of a list (Crossref-shaped CSL), numbers as text, anything else None."""
    while isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    return str(value).strip() or None


def _csl_person(p: dict) -> str:
    if literal := _s(p.get("literal")):
        return literal
    particles = (_s(p.get("non-dropping-particle")), _s(p.get("dropping-particle")), _s(p.get("family")))
    return _join_name(" ".join(x for x in particles if x), _s(p.get("given")) or "", _s(p.get("suffix")) or "")


def _csl_year(item: dict) -> int | None:
    issued = item.get("issued")
    if not isinstance(issued, dict):
        return _year(_s(issued))
    parts = issued.get("date-parts")
    first = parts[0][0] if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0] else None
    return _year(_s(first) or _s(issued.get("raw")) or _s(issued.get("literal")))


def _csl_people(item: dict, key: str) -> list[str]:
    people = item.get(key)
    return [n for p in people if isinstance(p, dict) and (n := _csl_person(p))] if isinstance(people, list) else []


def _csl_keywords(value) -> list[str]:
    return _split_words(", ".join(v for v in (_s(x) for x in value) if v) if isinstance(value, list) else _s(value))


def _check_csl(label: str, item: dict) -> None:
    """Every text in the item, a person's name parts included, under the BibTeX limits."""
    for key, value in item.items():
        for part in value if isinstance(value, list) else [value]:
            for text in part.values() if isinstance(part, dict) else [part]:
                if isinstance(text, str):
                    _check_sizes(label, {CSL_LIMITS.get(key, key): text})


def _csl_entry(item, number: int) -> ImportEntry:
    label = f"reference #{number} in this CSL-JSON file"
    if not isinstance(item, dict) or not (title := _s(item.get("title"))):
        raise CitationsImportError(f"The {label} has no title, so nothing was imported.")
    _check_csl(label, item)
    return _build(
        title, CSL_TYPES.get(_s(item.get("type")) or "", "other"), extra=_s(item.get("note")) or "",
        url=_s(item.get("URL")), authors=_csl_people(item, "author"), editors=_csl_people(item, "editor"),
        year=_csl_year(item), venue=_s(item.get("container-title")), publisher=_s(item.get("publisher")),
        doi=_s(item.get("DOI")), pmid=_s(item.get("PMID")), pmcid=_s(item.get("PMCID")), issn=_s(item.get("ISSN")),
        abstract=_s(item.get("abstract")), volume=_s(item.get("volume")), issue=_s(item.get("issue")),
        pages=_pages(_s(item.get("page"))), tags=_csl_keywords(item.get("keyword")),
    )  # fmt: skip


def _parse_csl(text: str) -> list[ImportEntry]:
    try:
        items = json.loads(text)
    except ValueError:
        raise CitationsImportError("This file isn't valid JSON, so nothing was imported.") from None
    if not isinstance(items, list):
        raise CitationsImportError("This JSON file isn't a CSL-JSON list of references.")
    _check_count(items)
    return [_csl_entry(item, n) for n, item in enumerate(items, 1)]


# ---- entry point ----


def _detect(name: str, text: str) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext in ("bib", "bibtex"):
        return "bibtex"
    if ext in ("ris", "json"):
        return ext
    head = text.lstrip()
    if head[:1] in ("[", "{"):
        return "json"
    if re.match(r"TY  - ", head):
        return "ris"
    if re.match(r"(?:@\w+\s*[{(]|%|@comment)", head):
        return "bibtex"
    raise CitationsImportError("PaperLab reads BibTeX (.bib), RIS (.ris) and CSL-JSON (.json) files from Zotero.")


def parse(name: str, data: bytes) -> list[ImportEntry]:
    """The references in a Zotero export. Raises CitationsImportError (plain message) for anything unreadable."""
    text = _decode(data)
    kind = _detect(name, text)
    try:
        return {"bibtex": _parse_bibtex, "ris": _parse_ris, "json": _parse_csl}[kind](text)
    except (RecursionError, TypeError, AttributeError, ValueError):
        # hostile or oddly shaped input (deep nesting, wrong value types): one plain message, never a trace to the
        # user; the log keeps it, so a real bug shows
        logger.warning("could not parse %s as %s", name, kind, exc_info=True)
        raise CitationsImportError("PaperLab couldn't read this file, so nothing was imported.") from None
