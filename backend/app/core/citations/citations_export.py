"""Citation export (M39 F7, D253-D255): one CSL-JSON item per paper is the hub; every format is rendered from it."""

import html
import json
import re
import unicodedata
import uuid
import warnings
from pathlib import Path

import bibtexparser
import rispy
from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter
from citeproc.source.json import CiteProcJSON
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.citations.citations_keywords import workspace_keywords
from app.core.citations.csl_items import ARTICLES, TRANSLITERATE, _suffix, bibtex_keys, csl_item
from app.core.search.candidates import arxiv_from_doi
from app.core.workspaces import workspaces
from app.domain.errors import InvalidInput, NotFound
from app.models import Paper

# ---- renderers ----

APA_STYLE = Path(__file__).resolve().parents[2] / "styles" / "apa.csl"
FORMATS = {
    "bibtex": ("application/x-bibtex", "bib"),
    "ris": ("application/x-research-info-systems", "ris"),
    "csljson": ("application/vnd.citationstyles.csl+json", "json"),
    "apa": ("text/plain", "txt"),
    "apa-html": ("text/html", "html"),
}
BIBTEX_TYPES = {
    "article-journal": "article",
    "article-magazine": "article",
    "paper-conference": "inproceedings",
    "book": "book",
    "chapter": "incollection",
    "thesis": "phdthesis",
}
RIS_TYPES = {
    "article-journal": "JOUR",
    "article-magazine": "MGZN",
    "paper-conference": "CONF",
    "book": "BOOK",
    "chapter": "CHAP",
    "thesis": "THES",
}
BIBTEX_SPECIALS = str.maketrans(
    {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
     "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
)  # fmt: skip


def render(items: list[dict], fmt: str) -> str:
    """The items as one of FORMATS, in the order given (APA sorts itself). ValueError("unknown_format") otherwise."""
    if fmt not in FORMATS:
        raise ValueError("unknown_format")
    if fmt == "csljson":
        public = [{k: v for k, v in item.items() if not k.startswith("_")} for item in items]
        return json.dumps(public, ensure_ascii=False, indent=2)
    if fmt == "bibtex":
        return _bibtex(items)
    if fmt == "ris":
        return _ris(items)
    return _apa(items, html=fmt == "apa-html")


def _tex(text: str | None) -> str | None:
    return text.translate(BIBTEX_SPECIALS) if text else text


def _bibtex_names(people: list[dict]) -> str:
    return " and ".join(
        "{" + _tex(p["literal"]) + "}" if "literal" in p else _tex(f"{p['family']}, {p['given']}".rstrip(", "))
        for p in people
    )


def _note_lines(item: dict) -> list[str]:
    """The genre joined to the first note line, then one line per Extra line (`arXiv: …`, `PMID: …`)."""
    first, *rest = (item.get("note") or "").split("\n")
    return [line for line in (". ".join(p for p in (item.get("genre"), first) if p), *rest) if line]


# What a published paper's reference list may print: PaperLab's own notes (source, peer review, how much of it the
# library holds), keywords, abstracts and annotes stay in the library's exports only.
LIBRARY_ONLY = ("abstract", "issn", "pmid", "pmcid", "keywords", "annote", "file")


def _bibtex_fields(item: dict, publish: bool = False) -> dict[str, str]:
    kind = item["type"]
    container = item.get("container-title")
    fields = {
        "author": _bibtex_names(item.get("author", [])),
        "editor": _bibtex_names(item.get("editor", [])),
        "title": item["title"],
        "journal": container if kind in ("article-journal", "article-magazine") else None,
        "booktitle": container if kind in ("paper-conference", "chapter") else None,
        "publisher": item.get("publisher"),
        "year": str(item.get("issued", {}).get("date-parts", [[""]])[0][0]),
        "volume": item.get("volume"),
        "number": item.get("issue"),
        "pages": re.sub(r"^(\d+)\s*[-–]+\s*(\d+)$", r"\1--\2", item.get("page") or "") or None,
        "note": "\n".join(_note_lines(item)),
        "abstract": item.get("abstract"),
        "issn": item.get("ISSN"),
        "pmid": item.get("PMID"),
        "pmcid": item.get("PMCID"),
        "keywords": item.get("keyword"),
        "annote": "\n\n".join(item.get("_notes", [])),
        "file": item.get("_file"),  # set by citations_bundle: the PDF's path inside the zip
    }
    if publish:
        fields = {k: v for k, v in fields.items() if k not in LIBRARY_ONLY} | {"note": item.get("genre")}
    escaped = {k: v if k in ("author", "editor") else _tex(v) for k, v in fields.items()}
    # DOIs, URLs and the arXiv id are verbatim in BibTeX; escaping their underscores or percents would break the link.
    arxiv = arxiv_from_doi((item.get("DOI") or "").lower()) or item.get("_arxiv")
    extra = {"eprint": arxiv, "archivePrefix": "arXiv" if arxiv else None}
    url = None if publish and item.get("DOI") else item.get("URL")  # a reference list links the DOI, not a PDF copy
    return {**escaped, "doi": item.get("DOI"), "url": url, **extra}


def _publish_field(field: bibtexparser.model.Field) -> bibtexparser.model.Field | None:
    key = field.key.lower()
    if key in LIBRARY_ONLY:
        return None
    if key == "note":  # every stored note is PaperLab's; a publishing note is the genre only ("Preprint")
        return bibtexparser.model.Field("note", "Preprint") if str(field.value).startswith("Preprint") else None
    return field


def publishable(bibtex: str) -> str:
    """Stored BibTeX entries (a manuscript's pin) with only publishing fields, as `_bibtex(..., publish=True)` writes
    them: an entry stored before the manuscript bib dropped PaperLab's notes is cleaned when it is printed again."""
    library = bibtexparser.Library()
    for entry in bibtexparser.parse_string(bibtex).entries:
        doi = any(f.key.lower() == "doi" for f in entry.fields)
        fields = [f for f in map(_publish_field, entry.fields) if f and not (doi and f.key.lower() == "url")]
        library.add(bibtexparser.model.Entry(entry.entry_type, entry.key, fields))
    return bibtexparser.write_string(library) if library.entries else ""


def _bibtex(items: list[dict], pinned: dict[str, str] | None = None, publish: bool = False) -> str:
    """BibTeX entries. `publish`: for a manuscript's reference list (publishing fields only, see LIBRARY_ONLY)."""
    keys = bibtex_keys(items, pinned)
    library = bibtexparser.Library()
    for item in items:
        fields = [bibtexparser.model.Field(k, v) for k, v in _bibtex_fields(item, publish).items() if v]
        entry_type = BIBTEX_TYPES.get(item["type"], "misc")
        library.add(bibtexparser.model.Entry(entry_type, keys[item["id"]], fields))
    return bibtexparser.write_string(library)


def _ris_names(people: list[dict]) -> list[str]:
    return [p["literal"] if "literal" in p else f"{p['family']}, {p['given']}".rstrip(", ") for p in people]


def _ris_entry(item: dict) -> dict:
    m = re.fullmatch(r"(\d+)\s*[-–]+\s*(\d+)", item.get("page") or "")
    first, last = m.groups() if m else (item.get("page"), None)
    entry = {
        "type_of_reference": RIS_TYPES.get(item["type"], "GEN"),
        "title": item["title"],
        "authors": _ris_names(item.get("author", [])),
        "secondary_authors": _ris_names(item.get("editor", [])),
        "secondary_title": item.get("container-title"),
        "publisher": item.get("publisher"),
        "year": str(item.get("issued", {}).get("date-parts", [[""]])[0][0]),
        "volume": item.get("volume"),
        "number": item.get("issue"),
        "start_page": first or None,
        "end_page": last,
        "doi": item.get("DOI"),
        "urls": [item["URL"]] if item.get("URL") else None,
        "notes": [*_note_lines(item), *(" ".join(n.split()) for n in item.get("_notes", []))],  # RIS has no newlines
        "file_attachments1": item.get("_file"),
        "abstract": item.get("abstract"),
        "issn": item.get("ISSN"),
        "keywords": item.get("_keywords"),
    }
    return {k: v for k, v in entry.items() if v}


def _ris(items: list[dict]) -> str:
    return rispy.dumps([_ris_entry(item) for item in items])


def _initials(given: str) -> str:
    return "".join(w[0] for w in re.findall(r"\w+", given.lower()))


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(TRANSLITERATE))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _title_key(title: str) -> str:
    lowered = _fold(re.sub(r"^[\W_]+", "", title.strip()))
    return next((lowered[len(a) :] for a in ARTICLES if lowered.startswith(a)), lowered)


def _apa_names(item: dict) -> tuple:
    people = item.get("author") or [{"literal": _title_key(item["title"])}]
    return tuple((_fold(p.get("family") or p.get("literal") or ""), _initials(p.get("given", ""))) for p in people)


def _apa_order(item: dict) -> tuple:
    # citeproc-py's own bibliography.sort() leaves the order unchanged with this style, so order by authors (a shorter
    # list first), year, title.
    year = item.get("issued", {}).get("date-parts", [[0]])[0][0]
    return (_apa_names(item), year, _title_key(item["title"]), item["id"])


def _escaped(value):
    if isinstance(value, str):
        return html.escape(value, quote=False)
    if isinstance(value, list):
        return [_escaped(v) for v in value]
    if isinstance(value, dict):
        return {k: v if k in ("id", "type") else _escaped(v) for k, v in value.items()}
    return value


def _with_year_suffixes(ordered: list[dict]) -> list[dict]:
    """citeproc-py doesn't compute year suffixes: same authors and year get a, b, ... in the final order."""
    groups: dict[tuple, list[dict]] = {}
    for item in ordered:
        if item.get("issued"):
            groups.setdefault((_apa_names(item), _apa_order(item)[1]), []).append(item)
    suffixes = {i["id"]: _suffix(n) for g in groups.values() if len(g) > 1 for n, i in enumerate(g)}
    return [{**i, "year-suffix": suffixes[i["id"]]} if i["id"] in suffixes else i for i in ordered]


def _title_as_author(item: dict, *, html: bool) -> dict:
    """APA 7: with no author the title takes the author slot and is not repeated (citeproc-py repeats it). A standalone
    work keeps its italics; an article's title stays plain."""
    if item.get("author"):
        return item
    standalone = html and not item.get("container-title")
    title = f"<i>{item['title']}</i>" if standalone else item["title"]
    return {**item, "author": [{"literal": title}], "title": ""}


def _apa(items: list[dict], *, html: bool) -> str:
    ordered = _with_year_suffixes(sorted(items, key=_apa_order))
    if html:
        ordered = [_escaped(i) for i in ordered]  # citeproc's html formatter leaves field values raw
    ordered = [_title_as_author(i, html=html) for i in ordered]
    # ponytail: the style is parsed on every call (~0.3 s); cache it if exports get hot.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # citeproc-py warns about CSL fields it doesn't know
        style = CitationStylesStyle(str(APA_STYLE), validate=False)
        bibliography = CitationStylesBibliography(
            style, CiteProcJSON(ordered), formatter.html if html else formatter.plain
        )
        for item in ordered:
            bibliography.register(Citation([CitationItem(item["id"])]))
        return "\n".join(str(entry) for entry in bibliography.bibliography()) + "\n"


MAX_SELECTION = 1000


async def load_items(
    session: AsyncSession, *, workspace_id: uuid.UUID | None = None, paper_ids: list[uuid.UUID] | None = None,
    notes: bool = False,
) -> tuple[list, list[dict]]:  # fmt: skip
    """(papers, CSL items) of the workspace (its own order) or the selected papers (the order given, repeats dropped).
    With a workspace, keywords add its tags and screening decision; ids plus a workspace select within it (any paper).
    `notes` adds each paper's PaperLab notes. Raises InvalidInput no_papers / too_many_papers, NotFound."""
    if workspace_id is not None and paper_ids is None:
        papers = await workspaces.papers(session, workspace_id)
    else:
        if workspace_id is not None:
            await workspaces.get(session, workspace_id)
        if len(paper_ids or []) > MAX_SELECTION:
            raise InvalidInput("too_many_papers", max=MAX_SELECTION)
        ids = list(dict.fromkeys(paper_ids or []))
        found = {p.id: p for p in await session.scalars(select(Paper).where(Paper.id.in_(ids)))}
        if missing := [i for i in ids if i not in found]:
            raise NotFound(f"paper {missing[0]} not found")
        papers = [found[i] for i in ids]
    if not papers:
        raise InvalidInput("no_papers")
    words = await workspace_keywords(session, workspace_id) if workspace_id is not None else {}
    texts = await _note_texts(session, papers) if notes else {}
    return papers, [csl_item(p, words.get(p.id), texts.get(p.id)) for p in papers]


async def _note_texts(session: AsyncSession, papers: list) -> dict[uuid.UUID, list[str]]:
    from app.core.notes import notes_markdown  # imported here: notes_markdown imports this module

    by_paper = await notes_markdown._notes_by_paper(session, [p.id for p in papers])
    return {pid: [notes_markdown.plain_note(pid, n) for n in items] for pid, items in by_paper.items()}


async def export_papers(
    session: AsyncSession, *, workspace_id: uuid.UUID | None = None, paper_ids: list[uuid.UUID] | None = None,
    fmt: str, notes: bool = False,
) -> tuple[str, int]:  # fmt: skip
    """`load_items` rendered as `fmt`. Raises InvalidInput unknown_format too."""
    if fmt not in FORMATS:
        raise InvalidInput("unknown_format")
    papers, items = await load_items(session, workspace_id=workspace_id, paper_ids=paper_ids, notes=notes)
    return render(items, fmt), len(papers)


def filename_slug(name: str) -> str:
    """A download-safe name: lowercase ASCII words joined by hyphens."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-") or "citations"
