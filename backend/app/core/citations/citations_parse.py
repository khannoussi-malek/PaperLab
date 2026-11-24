"""Parsing a citations file: telling BibTeX, RIS and CSL-JSON apart, and reading each into import entries."""

import json
import logging
import re

import bibtexparser
import rispy

from app.core.citations.citations_import import (
    CitationsImportError,
    ImportEntry,
    _build,
    _check_count,
    _check_sizes,
    _decode,
    _join_name,
    _names,
    _note,
    _pages,
    _person,
    _split_top,
    _split_words,
    _tex,
    _tex_block,
    _year,
)

logger = logging.getLogger(__name__)

# RIS and CSL keys checked under the BibTeX limit of another name; any other key is checked as itself (FIELD_MAX).
RIS_LIMITS = {"notes": "note", "urls": "file", "file_attachments1": "file", "authors": "author name",
              "first_authors": "author name", "secondary_authors": "editor name"}  # fmt: skip
CSL_LIMITS = {"author": "author name", "editor": "editor name", "keyword": "keywords", "URL": "file"}


MIME_TAIL = re.compile(r":(?:application|text|image|audio|video)/[\w.+-]+$")
DRIVE = re.compile(r"[A-Za-z]:[\\/]")


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
