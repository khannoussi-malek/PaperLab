"""The local-model screening suggestion for one hit (M31b spec §4.4): the prompt, and a parser that turns anything
off-format into `unsure` so a malformed reply never becomes an exclude."""

from dataclasses import dataclass

from app.core import prompts

SCREENING_PROMPT_VERSION = 1
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("screening_suggest", SCREENING_PROMPT_VERSION).split(
    "\n<!-- prompt -->\n"
)
EXCLUDE_REASONS = ("wrong_topic", "wrong_study_type", "duplicate", "language", "inaccessible", "other")
NOTE_CHARS = 300


@dataclass(frozen=True)
class Suggestion:
    verdict: str  # include | exclude | unsure
    reason: str | None
    note: str | None


def build_prompt(criteria: str, title: str | None, abstract: str | None) -> str:
    # str.format only parses the template, so braces in the criteria or abstract are safe.
    return PROMPT_TEMPLATE.format(criteria=criteria, title=title or "(no title)", abstract=abstract or "(no abstract)")


def parse_reply(text: str) -> Suggestion:
    """The model's two-line reply. Anything that isn't exactly the format is `unsure`: a malformed reply never
    becomes an exclude and never raises."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return Suggestion("unsure", None, None)
    note = lines[1][:NOTE_CHARS] if len(lines) > 1 else None
    words = lines[0].lower().split()
    if words == ["include"]:
        return Suggestion("include", None, note)
    if len(words) == 2 and words[0] == "exclude" and words[1] in EXCLUDE_REASONS:
        return Suggestion("exclude", words[1], note)
    return Suggestion("unsure", None, note if words == ["unsure"] else None)
