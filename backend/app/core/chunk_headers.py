"""Document-aware chunk headers (M8): a chunk is embedded and keyword-indexed as "<title> · <section>" above its text,
so a passage deep in a long document is found by the document it belongs to. The chunk's text stays the PDF's own:
citations, highlight boxes and quote checks read it. Measured 2026-11-23 on chat's path: apixaban 15 -> 16, semaglutide
18 -> 19, no question lost; title + venue/year and a detected EU/US label kind scored no better than this.
ponytail: the title as it was when the chunk was embedded; a later edit or enrichment shows after the next re-index."""

SEPARATOR = " · "


def header(title: str | None, section: str | None) -> str:
    """The paper's title and the chunk's section, whichever it has; "" for neither."""
    return SEPARATOR.join(part.strip() for part in (title, section) if part and part.strip())


def embed_text(header_line: str, text: str) -> str:
    """What the search model reads for a chunk: its header on a line of its own, then its text."""
    return f"{header_line}\n{text}" if header_line else text
