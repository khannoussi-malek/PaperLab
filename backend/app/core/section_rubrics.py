"""What each kind of section must contain, written for the author (M27e). Fixed text; the model only judges it.

The reader's checklist (D180, M16b) is not built yet; this file is the single home so M16b can share the items.
"""

from dataclasses import dataclass

from app.core.errors import InvalidInput
from app.core.sections import Role


@dataclass(frozen=True)
class RubricItem:
    id: str
    text: str


def _items(*pairs: tuple[str, str]) -> tuple[RubricItem, ...]:
    return tuple(RubricItem(i, t) for i, t in pairs)


RUBRICS: dict[Role, tuple[RubricItem, ...]] = {
    "abstract": _items(
        ("problem", "States the problem or question the paper takes on."),
        ("approach", "Says in a phrase what was done."),
        ("findings", "Reports the main result, with a number where there is one."),
        ("takeaway", "Says what the result means for the reader."),
    ),
    "intro": _items(
        ("problem", "Names the problem and why it matters."),
        ("known", "Says what is already known and where the gap is."),
        ("aim", "States the question or aim."),
        ("adds", "Says what this paper adds."),
    ),
    "related": _items(
        ("groups", "Groups earlier work by theme, not one paper at a time."),
        ("compare", "Says how each group differs from this paper."),
        ("gap", "Makes clear what earlier work leaves open."),
    ),
    "method": _items(
        ("design", "Describes the design or approach in enough detail to follow it."),
        ("data", "Says what data, sample or materials were used and where they came from."),
        ("measures", "Defines the measures or metrics used."),
        ("analysis", "Explains how the results were analysed."),
        ("reproduce", "Gives what a reader needs to repeat the work."),
    ),
    "results": _items(
        ("findings", "Reports what was found, answering each question asked."),
        ("numbers", "Gives the numbers behind each claim, with spread or uncertainty."),
        ("baseline", "Compares against a baseline or alternative."),
        ("neutral", "Keeps interpretation for the discussion."),
    ),
    "discussion": _items(
        ("meaning", "Says what the results mean for the question."),
        ("context", "Relates the results to earlier work."),
        ("surprises", "Addresses results that were unexpected or mixed."),
        ("implications", "Says what follows for readers or practice."),
    ),
    "limitations": _items(
        ("threats", "Names the threats to validity that apply to this study."),
        ("effect", "Says how each limit could affect the conclusions."),
        ("handled", "Says what was done about each limit."),
    ),
    "conclusion": _items(
        ("answer", "Answers the question asked in the introduction."),
        ("summary", "Sums up the main findings without new results."),
        ("next", "Points to future work."),
    ),
}


def rubric_for(role: str) -> tuple[RubricItem, ...]:
    if role not in RUBRICS:
        raise InvalidInput("unknown_role", detail="Pick what kind of section this is.")
    return RUBRICS[role]  # type: ignore[index]
