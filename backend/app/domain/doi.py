"""Reading a DOI out of any text or link, in its one stored form."""

import re

_DOI = re.compile(r"10\.\d{4,9}/\S+")


def normalize_doi(value: str) -> str | None:
    """The first DOI in `value`, lowercased (DOIs are case-insensitive), or None."""
    match = _DOI.search(value)
    if match is None:
        return None
    doi = re.sub(r"^(10\.\d{4,9})/+", r"\1/", match.group().lower())  # OpenAlex's legacy APA "10.1037//…"
    while True:
        trimmed = doi.rstrip(".,;").removesuffix(".pdf")  # a publisher's PDF URL ends in the file's extension
        # A DOI may contain balanced brackets ("s0140-6736(20)30367-6"); only an unbalanced closing one is prose.
        for open_ch, close_ch in ("()", "[]"):
            if trimmed.endswith(close_ch) and trimmed.count(close_ch) > trimmed.count(open_ch):
                trimmed = trimmed[:-1]
        if trimmed == doi:
            return trimmed
        doi = trimmed
