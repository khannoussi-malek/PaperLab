"""citations.missing_keys: keys a manuscript cites that match nothing (M27d), as a registered check."""

from app.core.manuscript_checks.base import Check, CheckContext, Finding
from app.core.manuscript_missing_keys import missing_in

NAME = "citations.missing_keys"


def _run(ctx: CheckContext) -> list[Finding]:
    return [
        Finding(NAME, "error", m["file"], m["line"],
                f"Cited key {m['key']} matches no paper in your library or your .bib files, so LaTeX prints [?].",
                "Add the paper to the workspace, pin it, or add the entry to a .bib file; or fix the key.")
        for m in missing_in(sorted(ctx.files.items()), ctx.known_keys)
    ]


CHECKS = (Check(NAME, "cheap", "Cited keys that match no paper or .bib entry", _run),)
