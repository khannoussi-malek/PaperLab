"""The exit-test check's wording and the pure rules for which of its lines survive (M22, D118, D171).

A check names gaps only. A model line that hands over the answer (wording, a copied run, a number the reader didn't
write) is dropped and counted, and never reaches the browser.
"""

import re
import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field

from app.core import prompts
from app.core.finding_lines import Kind, bare, clean_line, grams, reads_as_wording, split_label
from app.core.retrieval import RetrievedChunk

OUTPUT_KIND = "check"  # the llm_outputs.kind of a check
CHECK_PROMPT_VERSION = 1
EXIT_TESTS = ("five_cs", "summary", "reconstruction")
LABELS = {"five_cs": "five Cs", "summary": "summary", "reconstruction": "reconstruction"}
CHECK_NOTE_CHARS = 8_000
CHECK_QUERIES = 12
CHECK_K = 3
MAX_WORDS = 25
MAX_LINES = 12
MIN_QUERY_WORDS = 4

_REF = re.compile(r"\[C(\d+)\]")
_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_FIVE_C_LABEL = re.compile(
    r"^\s*(?:\*\*)?(?:category|context|correctness|contributions|clarity)(?:\*\*)?\s*:(?:\*\*)?", re.IGNORECASE
)
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n")
_ORDER = {"missing": 0, "unsupported": 1, "supported": 2}


def _load(version: int) -> tuple[str, str, dict[str, str]]:
    """The system prompt, the template and one instruction per exit test, split on `<!-- name -->` lines."""
    system, *named = re.split(r"\n<!-- (\w+) -->\n", prompts.load("check", version).strip())
    parts = {name: part.strip() for name, part in zip(named[::2], named[1::2])}
    if sorted(parts) != sorted(("prompt", *EXIT_TESTS)):
        raise RuntimeError(f"check.v{version}.md needs the parts prompt, {', '.join(EXIT_TESTS)}")
    template = parts.pop("prompt")
    return system.strip(), template, parts


SYSTEM_PROMPT, PROMPT_TEMPLATE, TASKS = _load(CHECK_PROMPT_VERSION)


def written_text(kind: str, body: str) -> str:
    if kind == "five_cs":
        body = "\n".join(_FIVE_C_LABEL.sub("", line, count=1).strip() for line in body.split("\n"))
    return body.strip()


def queries(kind: str, body: str) -> list[str]:
    text = written_text(kind, body)
    if kind == "five_cs":
        found = [line for line in text.split("\n") if line.strip()]
    else:
        found = [s.strip() for s in _SENTENCES.split(text) if len(s.split()) >= MIN_QUERY_WORDS]
    # ponytail: a regex splits sentences; abbreviations cost only an extra retrieval.
    return found[:CHECK_QUERIES] or [text]


def take_turns(
    hits: list[list[RetrievedChunk]], budget: int, taken: Collection[uuid.UUID] = ()
) -> list[RetrievedChunk]:
    """Hits in rounds (every query's first, then every second...), no repeats, none of `taken`; a chunk that
    doesn't fit the budget is skipped, never split."""
    seen = set(taken)
    out: list[RetrievedChunk] = []
    for round_ in zip(*[hit + [None] * (max(map(len, hits), default=0) - len(hit)) for hit in hits]):
        for chunk in round_:
            if chunk is None or chunk.id in seen or len(chunk.text) > budget:
                continue
            seen.add(chunk.id)
            budget -= len(chunk.text)
            out.append(chunk)
    return out


@dataclass(frozen=True)
class CheckGuard:
    copied: frozenset
    numbers: frozenset[str]


def _numbers(text: str) -> set[str]:
    return {run.replace(",", "") for run in _NUMBER.findall(text)}


def guard_for(note_body: str, passages: Iterable[str]) -> CheckGuard:
    """Runs of the passages the reader didn't write themselves, and the numbers the reader did."""
    return CheckGuard(frozenset(grams(passages) - grams([note_body])), frozenset(_numbers(note_body)))


@dataclass(frozen=True)
class CheckLine:
    verdict: Kind
    text: str
    cited: list[int]


@dataclass(frozen=True)
class CheckReply:
    lines: list[CheckLine]
    dropped: int


class LineFilter:
    def __init__(self, n_sources: int, guard: CheckGuard):
        self.n_sources, self.guard = n_sources, guard
        self.lines: list[CheckLine] = []
        self.dropped = 0
        self._seen: set[str] = set()

    def feed(self, raw_line: str) -> CheckLine | None:
        cleaned = clean_line(raw_line)
        if not cleaned or cleaned in self._seen:
            return None
        self._seen.add(cleaned)
        line = self._judge(cleaned)
        if line is None:
            self.dropped += 1
        else:
            self.lines.append(line)
        return line

    def _judge(self, cleaned: str) -> CheckLine | None:
        labelled = split_label(cleaned)
        if labelled is None:
            return None
        verdict, text = labelled
        plain = bare(text, _REF)
        if not 1 <= len(plain.split()) <= MAX_WORDS or reads_as_wording(text, _REF, self.guard.copied):
            return None
        if _numbers(plain) - self.guard.numbers:  # the line would hand over the paper's number
            return None
        cited = list(dict.fromkeys(n for n in map(int, _REF.findall(text)) if 1 <= n <= self.n_sources))
        if verdict != "unsupported" and not cited:
            return None
        if len(self.lines) >= MAX_LINES:
            return None
        return CheckLine(verdict, text, cited)


def parse_check(content: str, n_sources: int, guard: CheckGuard) -> CheckReply:
    keep = LineFilter(n_sources, guard)
    for raw in content.split("\n"):
        keep.feed(raw)
    return CheckReply(sorted(keep.lines, key=lambda line: _ORDER[line.verdict]), keep.dropped)


@dataclass
class KeptLines:
    """An LLM whose stream yields only the lines that survive the rules, one per token, so the raw reply stays
    on the server (D118)."""

    llm: object
    n_sources: int
    guard: CheckGuard
    raw: str = field(default="", init=False)

    def __post_init__(self):
        self.model, self.connection_name, self.host = self.llm.model, self.llm.connection_name, self.llm.host
        self.filter = LineFilter(self.n_sources, self.guard)

    async def stream(self, system: str, prompt: str):
        buffer = ""
        async for token in self.llm.stream(system, prompt):
            self.raw += token
            buffer += token
            *done, buffer = buffer.split("\n")
            for raw_line in done:
                if line := self.filter.feed(raw_line):
                    yield f"{line.verdict.capitalize()}: {line.text}\n"
        if line := self.filter.feed(buffer):
            yield f"{line.verdict.capitalize()}: {line.text}\n"
