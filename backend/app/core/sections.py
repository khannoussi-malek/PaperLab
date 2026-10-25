"""Section roles (M16, D48): which part of a paper each heading starts, computed on request from the headings alone.

`assign_roles` is pure. The service half reads a paper's headings from its chunks and stores only the reader's own
fixes, in `section_role_overrides`. No AI.
"""

import re
from collections.abc import Mapping
from typing import Literal, NamedTuple, get_args

Role = Literal[
    "abstract", "intro", "related", "method", "results", "discussion", "limitations", "conclusion", "back", "other"
]
Source = Literal["user", "keyword", "inherited", "position", "none"]
ROLES: tuple[Role, ...] = get_args(Role)


class RoleResult(NamedTuple):
    role: Role
    source: Source


class _Heading(NamedTuple):
    number: str | None  # "3", "3.2.1", "A.1", "IV"; None when unnumbered
    text: str  # lowercased, without the number


OTHER = RoleResult("other", "none")
# Rule 1. A bare capital letter is text ("A Study of…"); "A.1" and "IV." are numbers.
# ponytail: IEEE lettered subsections ("A." under "III. Results") don't parse as numbered, so they fall to position;
# upgrade: accept `[A-Z]\.` when it follows a roman-numbered parent.
_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)*\.?|[A-Z](?:\.\d+)+\.?|[IVX]+\.)\s+")
_REFERENCES = re.compile(r"^(?:references|bibliography)\b")  # the section itself, not a heading that mentions it
# Rule 3. "acknowledg" is a prefix: acknowledgments, acknowledgements.
_BACK = re.compile(r"\b(?:references|bibliography|appendix|supplementary|data availability)\b|\backnowledg")
# Rule 4, first match wins. A trailing "s" is optional, so "3 METHODS" and "6 LIMITATIONS" match.
_KEYWORDS: tuple[tuple[Role, re.Pattern[str]], ...] = tuple(
    (role, re.compile(rf"\b(?:{'|'.join(words)})s?\b"))
    for role, words in (
        ("abstract", ["abstract"]),
        ("limitations", ["limitation", "threats to validity", "validity threats"]),
        ("intro", ["introduction", "motivation"]),
        ("related", ["related work", "background", "prior work", "literature review"]),
        ("conclusion", ["conclusion", "concluding", "future work"]),
        ("discussion", ["discussion", "implications"]),
        ("results", ["results", "findings", "evaluation", "experiments", "ablation", r"rq\d+"]),
        (
            "method",
            [
                "method",
                "methodology",
                "approach",
                "study design",
                "research design",
                "procedure",
                "participants",
                "materials",
                "data collection",
                "architecture",
                "training",
                "experimental setup",
                "implementation",
            ],
        ),
    )
)
_KEEP_OWN = ("limitations", "back")  # rule 5's exceptions


def _parse(title: str) -> _Heading:
    match = _NUMBER.match(title)
    if match is None:
        return _Heading(None, title.strip().lower())
    return _Heading(match.group(1).rstrip("."), title[match.end() :].strip().lower())


def _direct(title: str | None, heading: _Heading | None, overrides: Mapping[str, Role], after_refs: bool):
    """Rules 2-4: the reader's fix, back matter, then keywords. None: not resolved yet."""
    if title is None:
        return OTHER  # the text before the first heading (spec §3.1)
    if title in overrides:
        return RoleResult(overrides[title], "user")
    if after_refs or _BACK.search(heading.text):
        return RoleResult("back", "keyword")
    role = next((role for role, pattern in _KEYWORDS if pattern.search(heading.text)), None)
    return None if role is None else RoleResult(role, "keyword")


def _inherit(headings, known):
    """Rule 5: a numbered subsection takes its top-level parent's role (when rules 2-4 know it), unless it has its own
    fix, or its own limitations or back match."""
    parents = {h.number: r for h, r in zip(headings, known) if h and h.number and "." not in h.number and r}

    def one(heading, own):
        if heading is None or heading.number is None or "." not in heading.number:
            return own
        parent = parents.get(heading.number.split(".")[0])
        if parent is None or (own is not None and (own.source == "user" or own.role in _KEEP_OWN)):
            return own
        return RoleResult(parent.role, "inherited")

    return [one(heading, own) for heading, own in zip(headings, known)]


def _front_matter(known):
    """Rule 6: unresolved sections before the first abstract or introduction are front matter."""
    first = next((i for i, result in enumerate(known) if result and result.role in ("abstract", "intro")), None)
    if first is None:
        return known
    return [OTHER if result is None and i < first else result for i, result in enumerate(known)]


def _nearest(results, indices):
    """The first resolved role that isn't other, looking through `indices` in order; None if there is none."""
    return next((results[i].role for i in indices if results[i] is not None and results[i].role != "other"), None)


def _position_role(prev, nxt, results_before: bool):
    """Rule 7a-e; None is 7f. `nxt` None means nothing resolved comes after."""
    if prev is not None and prev == nxt:
        return prev
    if prev == "intro" and nxt == "method":
        return "related"
    if prev in ("intro", "related", "method") and nxt == "results":
        return "method"
    if prev == "method" and nxt in ("discussion", "limitations", "conclusion", "back", None):
        return "results"
    if results_before and nxt in ("limitations", "conclusion", "back", None):
        return "discussion"
    return None


def _by_position(headings, known):
    """Rule 7: unresolved sections grouped by parent key (an unnumbered one alone), resolved left to right, each
    resolved group counting as known for the next."""
    groups: dict[str, list[int]] = {}
    for i, (heading, result) in enumerate(zip(headings, known)):
        if result is None:
            groups.setdefault(heading.number.split(".")[0] if heading.number else f"#{i}", []).append(i)
    results = list(known)
    for members in groups.values():
        prev = _nearest(results, range(members[0] - 1, -1, -1))
        nxt = _nearest(results, range(members[-1] + 1, len(results)))
        results_before = any(r is not None and r.role == "results" for r in results[: members[0]])
        role = _position_role(prev, nxt, results_before)
        found = OTHER if role is None else RoleResult(role, "position")
        results = [found if i in members else result for i, result in enumerate(results)]
    return results


def assign_roles(titles: list[str | None], overrides: Mapping[str, Role]) -> list[RoleResult]:
    """One (role, source) per section title, in the order given. Pure: no I/O (spec §3.2).

    `overrides` are the reader's fixes, keyed on the exact heading text."""
    headings = [None if title is None else _parse(title) for title in titles]
    refs = next(
        (i for i, h in enumerate(headings) if h and titles[i] not in overrides and _REFERENCES.search(h.text)),
        len(titles),
    )
    known = [_direct(title, heading, overrides, i > refs) for i, (title, heading) in enumerate(zip(titles, headings))]
    return _by_position(headings, _front_matter(_inherit(headings, known)))
