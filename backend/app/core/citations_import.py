"""Read Zotero exports (M40 Task 6, I1): BibTeX (Zotero and Better BibTeX), RIS and CSL-JSON into `ImportEntry`s.
Parsing only, no database. The file is never trusted: 20 MB, 5,000 entries, and any parse error raises
`CitationsImportError` (plain message) before anything is created. The inverse of `citations_export`."""

import json
import re
import unicodedata
from dataclasses import dataclass, field

import bibtexparser
import rispy
from pylatexenc.latex2text import LatexNodes2Text

from app.core.candidates import ARXIV_ID, arxiv_from_doi
from app.core.citations_import_html import html_to_markdown
from app.core.enrichment import normalize_doi

MAX_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 5000
YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d|21\d\d)\b")
ARXIV_LINE = re.compile(rf"^\s*arxiv:\s*({ARXIV_ID})(?:v\d+)?", re.IGNORECASE | re.MULTILINE)
ARXIV_URL = re.compile(rf"arxiv\.org/(?:abs|pdf)/({ARXIV_ID})(?:v\d+)?", re.IGNORECASE)
PMID_LINE = re.compile(r"^\s*pmid:\s*(\d+)", re.IGNORECASE | re.MULTILINE)
PMCID_LINE = re.compile(r"^\s*pmcid:\s*(PMC\d+)", re.IGNORECASE | re.MULTILINE)
# What PaperLab's own export writes into a note; reading it back as a note would duplicate the metadata.
OWN_NOTE = re.compile(
    r"^\s*(preprint\.\s*)?(source:|(not )?peer-reviewed|(full text|abstract only|metadata only) in paperlab"
    r"|arxiv:|pmid:|pmcid:|published version:)",
    re.IGNORECASE,
)
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
    return match.group(1).lower() if match else None


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
    return None if not lines or all(OWN_NOTE.match(ln) for ln in lines) else markdown


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
    if not (title := _tex(f.get("title"))):
        raise CitationsImportError(f"The BibTeX entry '{entry.key}' has no title, so nothing was imported.")
    source_type = BIBTEX_TYPES.get(entry.entry_type.lower(), "other")
    extra = _tex(f.get("note"))
    notes = [n for n in (_note(_tex(f["annote"])),) if n] if f.get("annote") else []
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
        raise CitationsImportError(
            "This BibTeX file has an entry PaperLab can't read (a missing brace or a repeated key), "
            "so nothing was imported."
        )
    _check_count(library.entries)
    return [_bibtex_entry(e) for e in library.entries]


# ---- RIS ----


def _as_list(value) -> list[str]:
    return [value] if isinstance(value, str) else [str(v) for v in value or []]


def _ris_entry(r: dict) -> ImportEntry:
    if not (title := r.get("title") or r.get("primary_title")):
        raise CitationsImportError("A reference in this RIS file has no title, so nothing was imported.")
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
    return [_ris_entry(r) for r in records]


# ---- CSL-JSON ----


def _csl_person(p: dict) -> str:
    if p.get("literal"):
        return p["literal"].strip()
    family = " ".join(x for x in (p.get("non-dropping-particle"), p.get("dropping-particle"), p.get("family")) if x)
    return _join_name(family.strip(), (p.get("given") or "").strip(), p.get("suffix") or "")


def _csl_year(item: dict) -> int | None:
    issued = item.get("issued") or {}
    parts = issued.get("date-parts") or [[]]
    return _year(parts[0][0] if parts and parts[0] else issued.get("raw") or issued.get("literal"))


def _csl_entry(item) -> ImportEntry:
    if not isinstance(item, dict) or not (title := str(item.get("title") or "").strip()):
        raise CitationsImportError("A reference in this CSL-JSON file has no title, so nothing was imported.")
    people = lambda key: [n for p in item.get(key) or [] if isinstance(p, dict) and (n := _csl_person(p))]  # noqa: E731
    return _build(
        title, CSL_TYPES.get(item.get("type"), "other"), extra=str(item.get("note") or ""), url=item.get("URL"),
        authors=people("author"), editors=people("editor"), year=_csl_year(item), venue=item.get("container-title"),
        publisher=item.get("publisher"), doi=item.get("DOI"), pmid=item.get("PMID"), pmcid=item.get("PMCID"),
        issn=item.get("ISSN"), abstract=item.get("abstract"), volume=_str(item.get("volume")),
        issue=_str(item.get("issue")), pages=_pages(_str(item.get("page"))),
        tags=_split_words(item.get("keyword")),
    )  # fmt: skip


def _str(value) -> str | None:
    return str(value) if value not in (None, "") else None


def _parse_csl(text: str) -> list[ImportEntry]:
    try:
        items = json.loads(text)
    except ValueError:
        raise CitationsImportError("This file isn't valid JSON, so nothing was imported.") from None
    if not isinstance(items, list):
        raise CitationsImportError("This JSON file isn't a CSL-JSON list of references.")
    _check_count(items)
    return [_csl_entry(i) for i in items]


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
    return {"bibtex": _parse_bibtex, "ris": _parse_ris, "json": _parse_csl}[kind](text)
