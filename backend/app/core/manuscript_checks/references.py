"""P01: reference hygiene over the user's own .bib files and the cites in the .tex files (S2P B2). Offline."""

import re
from collections.abc import Iterator

from app.core.manuscript_checks.base import Check, CheckContext, Finding
from app.core.manuscript_checks.bibparse import BibEntry, parse_bib
from app.core.manuscript_paths import RESERVED
from app.core.manuscript_sentences import _blank_comments, cite_spans

VENUE_FIELDS = {"journal", "booktitle", "publisher", "howpublished", "school", "institution", "organization", "series"}
VENUE_KINDS = {"article", "inproceedings", "conference", "incollection", "inbook", "book", "phdthesis",
               "mastersthesis", "techreport"}
IDENTIFIER_FIELDS = {"doi", "url", "eprint", "isbn"}
IDENTIFIER_KINDS = {"article", "inproceedings", "conference", "misc", "online", "unpublished"}
URL_IN = re.compile(r"\\url|https?://", re.I)
IDENTIFIER_FROM_YEAR = 2000  # older articles have no DOI
WEB_KINDS = {"misc", "online", "electronic", "www", "software", "dataset"}  # no person author or year to give
AUTHOR_FIELDS = {"author", "editor", "organization", "institution", "key"}


def bib_entries(ctx: CheckContext) -> Iterator[tuple[str, BibEntry]]:
    """The user's own .bib entries in path order; the generated paperlab.bib is PaperLab's output and is skipped."""
    for path in sorted(ctx.files):
        if path.endswith(".bib") and path.rsplit("/", 1)[-1].lower() != RESERVED:
            for entry in parse_bib(ctx.files[path]):
                yield path, entry


def _duplicates(ctx: CheckContext) -> list[Finding]:
    first: dict[str, tuple[str, int]] = {}
    found = []
    for path, e in bib_entries(ctx):
        seen = first.setdefault(e.key.lower(), (path, e.line))
        if seen != (path, e.line):
            found.append(Finding(
                "references.duplicate_key", "warning", path, e.line,
                f"Key {e.key} is defined twice (first at {seen[0]}:{seen[1]}); BibTeX uses the first.",
                "Delete or rename one of the entries. If both are the same paper, keep one key and fix the cites."))
    return found


def _has_url(e: BibEntry) -> bool:
    return bool(e.fields.get("url")) or any(URL_IN.search(e.fields.get(k, "")) for k in ("howpublished", "note"))


def _missing(e: BibEntry) -> list[str]:
    has = {k for k, v in e.fields.items() if v}
    if e.kind in WEB_KINDS and _has_url(e):  # a website or software page: the title and the URL are enough
        return [] if "title" in has else ["title"]
    missing = [n for n, ok in (("title", "title" in has), ("author", bool(AUTHOR_FIELDS & has)),
                               ("year", bool({"year", "date"} & has))) if not ok]
    if e.kind in VENUE_KINDS and not VENUE_FIELDS & has:
        missing.append("venue")
    return missing


def _lacks_identifier(e: BibEntry) -> bool:
    if e.kind not in IDENTIFIER_KINDS or any(e.fields.get(k) for k in IDENTIFIER_FIELDS):
        return False
    if any(URL_IN.search(e.fields.get(k, "")) for k in ("howpublished", "note")):
        return False
    year = re.search(r"\d{4}", e.fields.get("year") or e.fields.get("date") or "")
    return not (year and int(year.group()) < IDENTIFIER_FROM_YEAR)


def _stubs(ctx: CheckContext) -> list[Finding]:
    found = []
    for path, e in bib_entries(ctx):
        if m := _missing(e):  # a real stub: warning
            found.append(Finding("references.stub_entry", "warning", path, e.line,
                                 f"Entry {e.key} is missing: {', '.join(m)}.",
                                 "Fill the missing fields, or replace the entry with one added from your library "
                                 "(it has full metadata)."))
        if _lacks_identifier(e):  # common in real .bib files, so info only (never in the badge)
            found.append(Finding("references.stub_entry", "info", path, e.line, f"Entry {e.key} has no DOI or URL.",
                                 "Add the DOI or URL so readers (and Check DOIs online) can find it."))
    return found


def cited_keys(ctx: CheckContext) -> set[str]:
    return {k.lower() for p in ctx.files if p.endswith(".tex") for k, _ in cite_spans(ctx.files[p])}


def _unused(ctx: CheckContext) -> list[Finding]:
    cited = cited_keys(ctx)
    if "*" in cited:  # \nocite{*} cites every entry
        return []
    return [
        Finding("references.unused_entry", "info", path, e.line, f"Entry {e.key} is never cited.",
                "Delete it, or cite it if it belongs in the paper.")
        for path, e in bib_entries(ctx)
        if e.key.lower() not in cited
    ]


INCLUDED = r"\\(?:input|include|subfile|import|subimport)\b"  # a body placed by another file is not missing its cites
CITING_SECTIONS = {"introduction", "related work", "related works", "background", "literature review"}
MIN_SECTION_WORDS = 40  # a fresh heading with a line or two does not nag while drafting
HEADING = re.compile(r"\\section\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")


def _zero_cite(ctx: CheckContext) -> list[Finding]:
    found = []
    for path in sorted(p for p in ctx.files if p.endswith(".tex")):
        text = _blank_comments(ctx.files[path])
        heads = list(HEADING.finditer(text))
        for i, h in enumerate(heads):
            title = h.group(1).strip()
            if " ".join(title.lower().split()) not in CITING_SECTIONS:
                continue
            body = text[h.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            words = len(re.findall(r"[A-Za-z]{2,}", re.sub(r"\\[A-Za-z]+\*?", " ", body)))
            if words < MIN_SECTION_WORDS or re.search(INCLUDED, body) or cite_spans(body):
                continue
            found.append(Finding(
                "references.zero_cite_section", "warning", path, text.count("\n", 0, h.start()) + 1,
                f'Section "{title}" cites nothing.',
                "Related work and introductions normally cite the work they build on; "
                "add citations or confirm this is intended."))
    return found


CHECKS = (
    Check("references.duplicate_key", "cheap", "Bib keys defined more than once", _duplicates),
    Check("references.stub_entry", "cheap",
          "Bib entries missing title, author, year or venue (and a DOI or URL, as info)", _stubs),
    Check("references.unused_entry", "cheap", "Bib entries that no .tex file cites", _unused),
    Check("references.zero_cite_section", "cheap",
          "Introduction and related-work sections that cite nothing", _zero_cite),
)
