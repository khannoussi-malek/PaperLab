"""citations.missing_keys: keys a manuscript cites that match nothing (M27d), as a registered check."""

import difflib
import string
from collections.abc import Iterable

from app.core.manuscript_checks.base import Check, CheckContext, Finding
from app.core.manuscript_missing_keys import missing_in

NAME = "citations.missing_keys"
_HINT = "Add the paper to the workspace, pin it, or add the entry to a .bib file; or fix the key."
_MAX_SUGGESTIONS = 3


def suggest(key: str, known: Iterable[str]) -> list[str]:
    """Known keys a missing key may have meant: same key ignoring case, the key plus an a/b-style suffix, then
    close spellings. At most three, sorted."""
    keys = sorted(set(known))
    same_ignoring_case = [k for k in keys if k.lower() == key.lower()]
    suffixed = [k for k in keys if len(k) == len(key) + 1 and k[:-1] == key and k[-1] in string.ascii_lowercase]
    close = difflib.get_close_matches(key, keys, n=_MAX_SUGGESTIONS, cutoff=0.85)
    picked = list(dict.fromkeys(same_ignoring_case + suffixed + close))[:_MAX_SUGGESTIONS]
    return sorted(picked)


def _did_you_mean(near: list[str]) -> str:
    if len(near) == 1:
        return f"Did you mean {near[0]}?"
    return f"Did you mean {', '.join(near[:-1])} or {near[-1]}?"


def _hint(key: str, known: Iterable[str]) -> str:
    near = suggest(key, known)
    return f"{_did_you_mean(near)} {_HINT}" if near else _HINT


def _run(ctx: CheckContext) -> list[Finding]:
    known = sorted(ctx.known_keys)
    hints: dict[str, str] = {}  # one lookup per distinct key: a key cited 40 times is matched once
    found = []
    for m in missing_in(sorted(ctx.files.items()), ctx.known_keys):
        if m["key"] not in hints:
            hints[m["key"]] = _hint(m["key"], known)
        found.append(Finding(NAME, "error", m["file"], m["line"],
                             f"Cited key {m['key']} matches no paper in your library or your .bib files, "
                             "so LaTeX prints [?].", hints[m["key"]]))
    return found


CHECKS = (Check(NAME, "cheap", "Cited keys that match no paper or .bib entry", _run),)
