"""A paper as a CSL item, the shape every citation format is rendered from, and its BibTeX key."""

import re
import unicodedata

from app.core.search.candidates import arxiv_from_doi
from app.domain.source_types import PREPRINT_SERVERS

CSL_TYPES = {
    "journal_article": "article-journal",
    "proceedings": "paper-conference",
    "book": "book",
    "chapter": "chapter",
    "preprint": "article",
    "magazine": "article-magazine",
    "thesis": "thesis",
    "other": "document",
}
ARXIV_DOI_PREFIX = "10.48550/arxiv."
DOI_LINK = re.compile(r"^https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/\S+)$", re.IGNORECASE)
# A paper of unknown type with a known venue is a journal article unless the venue reads as a meeting. Journal words
# are read first: several journals carry a meeting word ("Proceedings of the National Academy", "History Workshop").
# ponytail: words plus a few big acronyms; a venue table (or OpenAlex's source type) if this misfiles real venues.
JOURNAL = re.compile(
    r"\b(journals?|transactions|letters|reviews?|pvldb)\b|mayo clinic proceedings|proceedings of the (national "
    r"academy|royal society|acm on|vldb endowment)|^proceedings of the ieee$",
    re.IGNORECASE,
)
MEETING = re.compile(
    r"\b(proceedings|conference|symposium|workshop|congress|colloquium|meeting|"
    r"iclr|icml|neurips|nips|aaai|ijcai|acl|emnlp|naacl|cvpr|iccv|eccv|kdd|sigir|cscw|uist)\b|"
    r"neural information processing systems|computer vision and pattern recognition|"
    r"knowledge discovery and data mining|international conference|"
    r"\bCHI\s*'?\d{2,4}\b",  # "CHI '24", "CHI 2024": the conference by its short name and year
    re.IGNORECASE,
)
BOOK = re.compile(r"\b(lecture notes|handbook|encyclopa?edia|book series)\b", re.IGNORECASE)
ISBN_DOI = re.compile(r"/97[89][-.\d]")
ORG_WORDS = {
    "organization", "organisation", "university", "institute", "association", "group", "consortium", "committee",
    "society", "agency", "ministry", "team", "collaboration", "council", "center", "centre", "foundation",
    "laboratory", "department", "commission", "network", "company", "inc", "ltd",
}  # fmt: skip
PARTICLES = {"van", "von", "de", "der", "den", "del", "della", "di", "da", "la", "le", "du", "bin", "al", "ter", "ten"}
SUFFIX = re.compile(r"[,\s]+(Jr\.?|Sr\.?|II|III|IV)$", re.IGNORECASE)
INITIALS = re.compile(r"[A-Z]{1,2}|(?:[A-Z]\.){1,3}")
# The letters NFKD leaves alone, which would otherwise vanish from a citation key (Sınav became "snav").
TRANSLITERATE = str.maketrans({
    "ø": "o", "ß": "ss", "æ": "ae", "œ": "oe", "ł": "l", "đ": "d", "þ": "th", "ı": "i", "ð": "d", "ħ": "h", "ŋ": "n",
    "ŧ": "t", "ſ": "s",
})  # fmt: skip
ARTICLES = ("a ", "an ", "the ")
STOP_WORDS = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "from", "by", "at", "as", "is", "are"}
ACCESS_NOTE = {
    "full_text": "full text in PaperLab",
    "abstract": "abstract only in PaperLab",
    "metadata": "metadata only in PaperLab",
}
CONTROL = re.compile(r"\s*[\x00-\x1f\x7f]+\s*")
PEER_NOTE = {"true": "peer-reviewed", "false": "not peer-reviewed"}


def _person(name: str) -> dict:
    name = " ".join(name.split())
    suffix = None
    if (m := SUFFIX.search(name)) and " " in name[: m.start()].strip():
        name, suffix = name[: m.start()].strip(), m.group(1)
    words = re.findall(r"\w+", name.lower())
    # ponytail: an organisation is a single token or one with an organisation word; the byline has no other marker.
    if " " not in name and "," not in name or ORG_WORDS & set(words):
        return {"literal": name}
    if "," in name:
        family, _, given = name.partition(",")
        person = {"family": family.strip(), "given": given.strip()}
    else:
        tokens = name.split(" ")
        cut = len(tokens) - 1
        if INITIALS.fullmatch(tokens[-1]) and len(tokens) > 1:
            # "Smith J.A.": the trailing initials are the given name
            person = {"family": " ".join(tokens[:cut]), "given": tokens[-1]}
        else:
            while cut > 1 and tokens[cut - 1].lower() in PARTICLES:
                cut -= 1
            person = {"family": " ".join(tokens[cut:]), "given": " ".join(tokens[:cut])}
    return {**person, "suffix": suffix} if suffix else person


def _kind_from_venue(venue: str | None, doi: str | None = None) -> str | None:
    """A paper of unknown type, by its venue; a chapter by its book's words or a DOI that holds the book's ISBN."""
    if venue and MEETING.search(venue) and not JOURNAL.search(venue.strip()):
        return "proceedings"
    if (venue and BOOK.search(venue)) or (doi and ISBN_DOI.search(doi)):
        return "chapter"
    return "journal_article" if venue else None


def _published_venue_and_doi(paper) -> tuple[str | None, str | None] | None:
    """Where a preprint was published, as (venue, DOI), or None for a true preprint. A citation wants the published
    record: an arXiv DOI on a paper with a real venue exported as @misc with the venue in `publisher`."""
    if paper.source_type != "preprint":
        return None
    doi = getattr(paper, "published_doi", None)
    venue = getattr(paper, "published_venue", None) or paper.venue
    if venue and PREPRINT_SERVERS.search(venue):
        venue = None
    return (venue, doi) if venue or doi else None


def _note(paper) -> str | None:
    label = (paper.source_type or "").replace("_", " ")
    preprint = paper.source_type == "preprint"  # the genre is already "Preprint"; don't say it twice
    parts = [
        f"Source: {label}" if label and not preprint else None,
        PEER_NOTE.get(paper.peer_reviewed),
        ACCESS_NOTE.get(paper.evidence_access),
    ]
    note = " · ".join(p for p in parts if p)
    return note[:1].upper() + note[1:] if preprint and note else note or None


def _extra_lines(paper) -> list[str]:
    """Zotero reads `Label: value` lines of a note as its Extra field, so identifiers with no CSL field go there."""
    published, venue = getattr(paper, "published_doi", None), getattr(paper, "published_venue", None)
    version = f"Published version: {venue + ' ' if venue else ''}"
    arxiv = arxiv_from_doi((paper.doi or "").lower())
    pmid, pmcid = getattr(paper, "pmid", None), getattr(paper, "pmcid", None)
    lines = (
        f"arXiv: {arxiv}" if arxiv else None,
        f"PMID: {pmid}" if pmid else None,
        f"PMCID: {pmcid}" if pmcid else None,
        f"{version}https://doi.org/{published}" if published else None,
    )
    return [line for line in lines if line]


def _keywords(paper, extra: list[str]) -> list[str]:
    label = (paper.source_type or "").replace("_", " ")
    words = [*extra, label, "peer-reviewed" if paper.peer_reviewed == "true" else None]
    # a control character (a newline in a tag) would start a new line in RIS, which doesn't escape
    return [clean for w in words if w and (clean := CONTROL.sub(" ", w).strip())]


def csl_item(paper, keywords: list[str] | None = None, notes: list[str] | None = None) -> dict:
    """The CSL-JSON item for a paper-like object (no DB). `keywords` come first (a workspace's tags and screening
    decision); the source type and "peer-reviewed" follow. Optional biblio fields are read when present."""
    published = _published_venue_and_doi(paper)
    kind = paper.source_type or _kind_from_venue(paper.venue, paper.doi)
    if published:
        kind = _kind_from_venue(published[0]) or "journal_article"
    item: dict = {"id": str(paper.id), "type": CSL_TYPES.get(kind, "document"), "title": paper.title}
    if paper.authors:
        item["author"] = [_person(name) for name in paper.authors]
    if editors := getattr(paper, "editors", None):
        item["editor"] = [_person(name) for name in editors]
    if paper.year:
        item["issued"] = {"date-parts": [[paper.year]]}
    if published:
        if published[0]:
            item["container-title"] = published[0]
    elif paper.source_type == "preprint":
        item["genre"] = "Preprint"
        arxiv = (paper.doi or "").lower().startswith(ARXIV_DOI_PREFIX)
        if publisher := paper.venue or ("arXiv" if arxiv else None):
            item["publisher"] = publisher
    elif paper.venue:
        item["container-title"] = paper.venue
    for key, attr in (("volume", "volume"), ("issue", "issue"), ("page", "pages")):
        if value := getattr(paper, attr, None):
            item[key] = str(value)
    for key, attr in (("abstract", "abstract"), ("ISSN", "issn"), ("PMID", "pmid"), ("PMCID", "pmcid")):
        if value := getattr(paper, attr, None):
            item[key] = value
    # A paper saved from a doi.org link can hold its DOI only there: a reference list wants it as the DOI.
    doi = paper.doi or ((m := DOI_LINK.match(paper.oa_url or "")) and m.group(1))
    if published and published[1]:
        item["_arxiv"] = arxiv_from_doi((doi or "").lower())  # the free copy, beside the published DOI
        doi = published[1]
    if doi:
        item["DOI"] = doi
    if paper.oa_url and not (doi and not paper.doi):
        item["URL"] = paper.oa_url
    if note := "\n".join(p for p in (_note(paper), *_extra_lines(paper)) if p):
        item["note"] = note
    if words := _keywords(paper, keywords or []):
        item["keyword"] = ", ".join(words)
        item["_keywords"] = words  # private: RIS writes one KW per entry, a tag may itself contain ", "
    if notes:
        item["_notes"] = notes  # private: PaperLab notes as plain text; BibTeX annote, one RIS N1 each
    return item


def _ascii(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower().translate(TRANSLITERATE)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", folded.lower())


def _base_key(item: dict) -> str:
    first = (item.get("author") or [{}])[0]
    name = first.get("family") or (first.get("literal") or "").split(" ")[0]
    year = item.get("issued", {}).get("date-parts", [[None]])[0][0]
    words = [_ascii(w) for w in item["title"].split()]
    word = next((w for w in words if w and w not in STOP_WORDS), "") or next((w for w in words if w), "")
    # ponytail: a name or title with no Latin letters (CJK, Cyrillic) falls back to "anon" / "untitled".
    return f"{_ascii(name) or 'anon'}{year or 'nd'}{word or 'untitled'}"


def bibtex_keys(items: list[dict], pinned: dict[str, str] | None = None) -> dict[str, str]:
    """item id -> key `firstauthorYEARfirstword`. Collisions in one export get a, b, ... by title, then id, so the
    same library gives the same keys every time. `pinned` (item id -> key) wins for those items; every pinned key is
    reserved, so the other items skip it and carry on from the next free letter."""
    pinned = pinned or {}
    taken = set(pinned.values())
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(_base_key(item), []).append(item)
    keys: dict[str, str] = {i["id"]: pinned[i["id"]] for i in items if i["id"] in pinned}
    for base in sorted(groups):  # sorted, so the keys do not depend on the order the items arrive in
        group = groups[base]
        group.sort(key=lambda i: (i["title"].lower(), i["id"]))
        for n, item in enumerate(i for i in group if i["id"] not in pinned):
            key = base if len(group) == 1 else base + _suffix(n)
            if key in taken:  # the next free letter, counting from "a" for a lone paper
                n = 0 if len(group) == 1 else n + 1
                while (key := base + _suffix(n)) in taken:
                    n += 1
            keys[item["id"]] = key
            taken.add(key)
    return keys


def _suffix(n: int) -> str:
    return (_suffix(n // 26 - 1) if n >= 26 else "") + chr(97 + n % 26)
