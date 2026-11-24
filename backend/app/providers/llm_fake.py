"""The fake model: deterministic and offline. LLM_PROVIDER=fake makes build_llm return it, so tests and the E2E
stack answer without a model. It tells features apart by their system prompt, so it imports each feature's prompt
from core lazily (core imports providers at module level)."""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Callable

from app.providers.base import LLMError

FAKE_ANSWER = "Fake answer: the method is described here [C1]."
# Word by word, with the citation marker split across two tokens like a real model does.
FAKE_TOKENS = ["Fake ", "answer: ", "the ", "method ", "is ", "described ", "here ", "[C", "1]", "."]
# Given the workspace system prompt: cites a passage from each of two papers and a note, as the workspace chat
# end-to-end spec expects.
FAKE_WORKSPACE_ANSWER = "Fake workspace answer: both papers describe the method [C1][C2], as your note says [N1]."
FAKE_WORKSPACE_TOKENS = [
    "Fake ",
    "workspace ",
    "answer: ",
    "both ",
    "papers ",
    "describe ",
    "the ",
    "method ",
    "[C",
    "1]",
    "[C",
    "2]",
    ", ",
    "as ",
    "your ",
    "note ",
    "says ",
    "[N",
    "1]",
    ".",
]
# note_suggestions.py's format: one "[C{i}]: body" line per passage — a middle one deliberately skipped, so the
# E2E stack exercises "the model covered fewer passages than it was given" too, not just the happy count.
FAKE_NOTE_SUGGESTIONS = "[C1]: Fake first passage note.\n[C3]: Fake third passage note."
FAKE_NOTE_SUGGESTIONS_TOKENS = [
    "[C1]: Fake ",
    "first ",
    "passage ",
    "note.\n[C3]: Fake ",
    "third ",
    "passage ",
    "note.",
]
# The check's reply (spec §3.7) without the "99%" (the number rule would drop it): three kept lines and one dropped,
# the [C / 1] marker split across tokens.
FAKE_CHECK_TOKENS = [
    "Missing: the main result ",
    "on the second page [C",
    "1].\n- Unsupported: the claimed accuracy [C",
    "1].\nSupported: the method described here [C1].\n",
    "Here is a better summary you could use.",
]
# The screening suggestion on the fake stack (M31b): an exclude with a reason, as the E2E spec expects.
FAKE_SCREENING_TOKENS = ["EXCLUDE ", "wrong_study_type\n", "A review, ", "not a primary study."]


def fake_screening_reply(prompt: str) -> str:
    """The v2 screening JSON on the fake stack: relevance from a stable hash of the title (so a rerun agrees), and one
    quote of three words copied from the abstract, so the quote check keeps it."""
    title = prompt.partition("Title: ")[2].partition("\n")[0]
    abstract = prompt.partition("Abstract:\n")[2]
    bucket = sum(title.encode()) % 4
    relevance, decision, reason = [
        (5, "include", None), (4, "include", None), (2, "exclude", "wrong_topic"), (3, "unsure", None),
    ][bucket]  # fmt: skip
    quotes = [" ".join(abstract.split()[:3])] if decision != "unsure" and len(abstract.split()) >= 3 else []
    return json.dumps(
        {"relevance": relevance, "decision": decision, "reason": reason, "quotes": quotes, "why": "Fake stack verdict."}
    )


_FIRST_PASSAGE = re.compile(r"\[1\] \(page [^)]*\) (.*?)(?:\n\n\[2\] |\Z)", re.DOTALL)


def fake_claim_check_reply(prompt: str) -> str:
    """A supported verdict on the fake stack, with the first numbered passage's first words as the quote (so the
    quote check keeps it); not_addressed when no passage carries text."""
    passage = _FIRST_PASSAGE.search(prompt)
    quote = " ".join(passage.group(1).split()[:10]) if passage else ""
    if len(quote.split()) < 3:
        return json.dumps({"verdict": "not_addressed", "passage": None, "quote": "", "reason": "Fake: no passage."})
    return json.dumps({"verdict": "supported", "passage": 1, "quote": quote, "reason": "Fake: the passage says so."})


def fake_claim_detect_reply(prompt: str) -> str:
    """A claim when the sentence has a digit or the word "show"."""
    sentence = prompt.split("Sentence:\n", 1)[-1]
    flag = any(c.isdigit() for c in sentence) or "show" in sentence.lower()
    return json.dumps({"is_claim": flag, "reason": "Fake: a number or 'show'." if flag else "Fake: neither."})


def fake_draft_review_reply(prompt: str) -> str:
    """One issue whatever the lens: the paper's first eight words as the quote, so three lenses merge into one issue.
    The summary and criterion have no colon, bracket or SUGGEST word ("says" is one), so they pass the wording guard."""
    paper = prompt.split("Paper (LaTeX source):\n", 1)[1]
    quote = " ".join(paper.split()[:8])
    issue = {"severity": "major", "section": "Paper", "summary": "This opening claim has no result behind it",
             "evidence_quote": quote, "close_criterion": "The claim must point to a result or a source"}
    return json.dumps({"issues": [issue]})


def fake_section_review_reply(prompt: str) -> str:
    """The first checklist item as Missing, and Supported on [S1] when a first sentence exists."""
    item = re.search(r"Checklist:\n- (.+)", prompt)
    lines = [f"Missing: {item.group(1)}" if item else "Missing: nothing to check"]
    if "[S1]" in prompt:
        lines.append("Supported: the opening states its topic [S1]")
    return "\n".join(lines)


def fake_diagram_reply(prompt: str) -> str:
    """One node per double-quoted phrase of the description (else its first three words), left to right with arrows."""
    description = prompt.split("Description:\n", 1)[-1].split("\n\nLibraries you may load:", 1)[0]
    phrases = re.findall(r'"([^"]+)"', description) or [" ".join(description.split()[:3])]
    labels = [re.sub(r"[\\{}$&%#_^~]", "", p).strip() or "box" for p in phrases]
    nodes = [f"\\node[draw] (n0) {{{labels[0]}}};"]
    nodes += [f"\\node[draw, right=of n{i - 1}] (n{i}) {{{label}}};" for i, label in enumerate(labels[1:], 1)]
    arrows = [f"\\draw[->] (n{i - 1}) -- (n{i});" for i in range(1, len(labels))]
    head = "\\usetikzlibrary{arrows.meta,positioning}\n\\begin{tikzpicture}[>={Stealth}]"
    return "\n".join(["<tikz>", head, *nodes, *arrows, "\\end{tikzpicture}", "</tikz>"])


def fake_number_suggest_reply(prompt: str) -> str:
    """Up to three numbers of the section, each with its sentence (at most 25 words) as the quote (D33)."""
    from app.domain.numbers import find_numbers  # providers never import core at module level

    text = prompt.split("\n\n", 1)[-1]
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        words = sentence.split()[:25]
        quote = " ".join(words).rstrip(".")
        candidates = find_numbers(quote)
        if candidates and len(found) < 3:
            raw = candidates[0].raw
            found.append({"label": f"Number {len(found) + 1}", "value": raw, "unit": candidates[0].unit_hint or "",
                          "quote": quote})
    return json.dumps({"numbers": found})


def fake_chart_reply(prompt: str) -> str:
    """A bar of D1's second column by its first, read from the datasets block the chart prompt lists (M14)."""
    first = next((line for line in prompt.splitlines() if line.startswith("D1 · ")), None)
    if first is None:
        return json.dumps({"chart": False, "reason": "The fake model saw no dataset."})
    columns = [c.split(" (")[0].strip() for c in first.split("columns: ", 1)[1].split(" · first row:")[0].split(", ")]
    if len(columns) < 2:
        return json.dumps({"chart": False, "reason": "The fake model needs two columns."})
    return json.dumps({"chart": True, "type": "bar", "dataset": "D1", "x": columns[0], "y": [columns[1]],
                       "title": f"{columns[1]} by {columns[0]}", "caption": "The fake model drew the first table."})


def fake_evidence_card_reply(prompt: str) -> str:
    """The evidence-card JSON on the fake stack: the first numbered passage's first words, copied exactly, as the
    research question, design and one finding. The value is the quote itself, so every number in it is in the quote."""
    passage = _FIRST_PASSAGE.search(prompt)
    quote = " ".join(passage.group(1).split()[:10]) if passage else ""
    item = {"value": quote, "passage": 1, "quote": quote}
    if len(quote.split()) < 3:
        return json.dumps(
            {
                "research_question": None,
                "design": None,
                "sample": None,
                "findings": [],
                "effect_sizes": [],
                "limitations": [],
            }
        )
    return json.dumps(
        {
            "research_question": item,
            "design": item,
            "sample": None,
            "findings": [item],
            "effect_sizes": [],
            "limitations": [],
        }
    )


# Asked for notes, in either chat: two suggested notes, the first citing a passage and the second nothing, then a line
# after them, as the note-suggestion end-to-end spec expects.
FAKE_NOTES_TOKENS = [
    "Here ", "are ", "two ", "notes.\n",
    ":::note\n",
    "The ", "method ", "anchors ", "every ", "note ", "on ", "a ", "passage ", "[C", "1].\n",
    ":::\n",
    ":::note\n",
    "Keep ", "one ", "idea ", "per ", "note.\n",
    ":::\n",
    "Both ", "come ", "from ", "the ", "method ", "section ", "[C", "1].",
]  # fmt: skip
FAKE_NOTES_ANSWER = "".join(FAKE_NOTES_TOKENS)
_NOTES_WORD = re.compile(r"\bnotes\b", re.IGNORECASE)


def asks_for_notes(prompt: str) -> bool:
    """Whether the question asks for notes: the word "notes" after the prompt's last "Question: ". The prompt above
    it always says "Notes (newest first)", whatever was asked."""
    _, found, question = prompt.rpartition("Question: ")
    return bool(found) and _NOTES_WORD.search(question) is not None


# What every connection lists on the fake stack, and the key its Test connection rejects.
FAKE_MODELS = ["fake-large", "fake-small"]
FAKE_BAD_KEY = "bad-key"
# Between fake tokens on the E2E stack, so answers stream visibly instead of in one burst.
FAKE_DELAY = 0.05


class FakeLLM:
    """Deterministic, offline. LLM_PROVIDER=fake makes build_llm return it, so the E2E stack answers without a model."""

    host = "fake"

    def __init__(
        self, model: str = "fake", connection_name: str = "Fake", fail_after: int | None = None, delay: float = 0.0
    ):
        self.model = model
        self.connection_name = connection_name
        self.fail_after = fail_after  # raise LLMError after this many tokens
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        self.calls.append((system, prompt))
        tokens = fake_tokens(system, prompt)
        for index, token in enumerate(tokens):
            if index == self.fail_after:
                raise LLMError("fake model failed mid-answer")
            await asyncio.sleep(self.delay)
            yield token


def fake_tokens(system: str, prompt: str) -> list[str]:
    """The fake reply to one call. The check comes first: a reader's note in its prompt may say "notes"."""
    check, replies = _replies()
    if system != check and asks_for_notes(prompt):
        return FAKE_NOTES_TOKENS
    reply = replies.get(system)
    return reply(prompt) if reply else FAKE_TOKENS


def _replies() -> tuple[str, dict[str, Callable[[str], list[str]]]]:
    """Each feature's system prompt and the fake reply to it. A new AI feature adds one line here.

    Imported here, not at module level: core.chat → retrieval → embedding → http_embedders → providers.
    """
    from app.core.answer_check import SYSTEM_PROMPT as ANSWER_CHECK_SYSTEM_PROMPT
    from app.core.chat import WORKSPACE_SYSTEM_PROMPT
    from app.core.chat_charts import SYSTEM_PROMPT as CHART_SYSTEM_PROMPT
    from app.core.checks import SYSTEM_PROMPT as CHECK_SYSTEM_PROMPT
    from app.core.claim_detect import SYSTEM_PROMPT as CLAIM_DETECT_SYSTEM_PROMPT
    from app.core.claims import SYSTEM_PROMPT as CLAIM_CHECK_SYSTEM_PROMPT
    from app.core.diagram import SYSTEM_PROMPT as DIAGRAM_SYSTEM_PROMPT
    from app.core.draft_review import SYSTEM_PROMPT as DRAFT_REVIEW_SYSTEM_PROMPT
    from app.core.draft_review import VERIFY_SYSTEM_PROMPT as DRAFT_VERIFY_SYSTEM_PROMPT
    from app.core.each_paper import EACH_PAPER_SYSTEM
    from app.core.each_paper import READING_SYSTEM as PAPER_READING_SYSTEM_PROMPT
    from app.core.evidence_cards import SYSTEM_PROMPT as EVIDENCE_CARD_SYSTEM_PROMPT
    from app.core.note_suggestions import SYSTEM_PROMPT as NOTE_SUGGESTIONS_SYSTEM_PROMPT
    from app.core.number_suggest import SYSTEM_PROMPT as NUMBER_SUGGEST_SYSTEM_PROMPT
    from app.core.screening_suggest import SYSTEM_PROMPT as SCREENING_SYSTEM_PROMPT
    from app.core.screening_suggest import SYSTEM_PROMPT_V2 as SCREENING_SYSTEM_PROMPT_V2
    from app.core.section_review import SYSTEM_PROMPT as SECTION_REVIEW_SYSTEM_PROMPT

    one = lambda reply: lambda prompt: [reply(prompt)]  # noqa: E731
    fixed = lambda tokens: lambda prompt: tokens  # noqa: E731
    pairs = [
        (CHECK_SYSTEM_PROMPT, fixed(FAKE_CHECK_TOKENS)),
        (WORKSPACE_SYSTEM_PROMPT, fixed(FAKE_WORKSPACE_TOKENS)),
        (EACH_PAPER_SYSTEM, fixed(FAKE_WORKSPACE_TOKENS)),
        # M8.5: every paper covers it, from its first passage.
        (PAPER_READING_SYSTEM_PROMPT,
         fixed([json.dumps({"status": "found", "answer": "The paper addresses this.", "cites": ["P1"]})])),
        (NOTE_SUGGESTIONS_SYSTEM_PROMPT, fixed(FAKE_NOTE_SUGGESTIONS_TOKENS)),
        (SCREENING_SYSTEM_PROMPT, fixed(FAKE_SCREENING_TOKENS)),
        (SCREENING_SYSTEM_PROMPT_V2, one(fake_screening_reply)),
        (EVIDENCE_CARD_SYSTEM_PROMPT, one(fake_evidence_card_reply)),
        (ANSWER_CHECK_SYSTEM_PROMPT, one(fake_claim_check_reply)),  # the claim check's reply shape (M34)
        (CLAIM_CHECK_SYSTEM_PROMPT, one(fake_claim_check_reply)),
        (CLAIM_DETECT_SYSTEM_PROMPT, one(fake_claim_detect_reply)),
        (SECTION_REVIEW_SYSTEM_PROMPT, one(fake_section_review_reply)),
        (NUMBER_SUGGEST_SYSTEM_PROMPT, one(fake_number_suggest_reply)),
        (CHART_SYSTEM_PROMPT, one(fake_chart_reply)),
        (DIAGRAM_SYSTEM_PROMPT, one(fake_diagram_reply)),
        (DRAFT_REVIEW_SYSTEM_PROMPT, one(fake_draft_review_reply)),
        (DRAFT_VERIFY_SYSTEM_PROMPT,
         fixed([json.dumps({"refuted": False, "reason": "The fake skeptic found the issue fair."})])),
    ]
    replies: dict[str, Callable[[str], list[str]]] = {}
    for system, reply in pairs:
        replies.setdefault(system, reply)  # the first match wins, as an if/elif chain would
    return CHECK_SYSTEM_PROMPT, replies
