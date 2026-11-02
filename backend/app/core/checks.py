"""The exit-test check's wording and the pure rules for which of its lines survive (M22, D118, D171).

A check names gaps only. A model line that hands over the answer (wording, a copied run, a number the reader didn't
write) is dropped and counted, and never reaches the browser.
"""

import re
import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import lenses, prompts, sections
from app.core.briefs import cut_to_budget
from app.core.chat import SMALL_PAPER_CHARS, Prepared, _size, chunk_sources, format_context
from app.core.errors import Conflict, InvalidInput
from app.core.finding_lines import Kind, bare, clean_line, grams, reads_as_wording, split_label
from app.core.notes import _get_note, papers_of
from app.core.papers import get_paper
from app.core.retrieval import RetrievedChunk, retrieve, searchable
from app.models import Chunk, PaperStatus, Provenance

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
OUTLINE_CHARS = 1_000

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


@dataclass(frozen=True)
class PreparedCheck:
    prepared: Prepared
    note_id: uuid.UUID
    paper_id: uuid.UUID
    question: str  # the note's body exactly as checked: a later edit makes the check stale
    guard: CheckGuard


def _outline(found: list[sections.Section]) -> str:
    lines = [f"- {s.title} (p.{s.page})" for s in found if s.role == "method"]
    text = "Sections of the method, in order:\n" + "\n".join(lines)
    return text[:OUTLINE_CHARS].rstrip() + "\n\n"


def _lens_ids(kind: str, found: list[sections.Section]) -> tuple[list[uuid.UUID], list[uuid.UUID], str]:
    """(anchor, evidence, outline) for an exit test; both id lists in reading order."""
    ordered = lenses.ordered_roles(found)
    ids = lambda lens: lenses.pick(ordered, lenses.LENSES[lens]).chunk_ids  # noqa: E731
    if kind == "reconstruction":
        return [], ids("method"), _outline(found)
    anchor = ids("key_ideas")
    keep = set(anchor)
    evidence = [i for i in ids("critical") if i not in keep] or [
        i for i, role in ordered if role != "back" and i not in keep
    ]
    return anchor, evidence, ""


async def _retrieved(session, paper_id, kind, body, anchor, evidence, embedder) -> list[RetrievedChunk]:
    embedder = await searchable(session, [paper_id], embedder)
    if (await _size(session, paper_id))[1] == 0:
        raise Conflict("paper_not_indexed")
    kept = cut_to_budget(await chunk_sources(session, Chunk.id.in_(anchor))) if anchor else []
    hits = []
    if evidence:  # retrieve() returns [] for an empty chunk_ids: skip the pointless queries
        for query in queries(kind, body):
            hits.append(
                await retrieve(session, query, paper_ids=[paper_id], chunk_ids=evidence, k=CHECK_K, embedder=embedder)
            )
    room = SMALL_PAPER_CHARS - sum(len(c.text) for c in kept)
    chosen = take_turns(hits, room, taken=[c.id for c in kept])
    ids = [c.id for c in kept + chosen]
    return await chunk_sources(session, Chunk.id.in_(ids))


async def prepare_check(session: AsyncSession, note_id: uuid.UUID, embedder=None) -> PreparedCheck:
    """The passages an exit-test check reads (D170), as `briefs.prepare_brief` leaves the session open to commit.

    Raises NotFound, Conflict ("not_your_text" | "note_not_on_one_paper" | "needs_full_text" | "paper_not_ready" |
    "lens_empty" | "paper_not_indexed" | search errors) or InvalidInput ("not_checkable" | "nothing_written" |
    "note_too_long")."""
    note = await _get_note(session, note_id)
    if note.provenance != Provenance.HUMAN:
        raise Conflict("not_your_text")
    kind = note.kind
    if kind not in EXIT_TESTS:
        raise InvalidInput("not_checkable")
    written = written_text(kind, note.body)
    if not written:
        raise InvalidInput("nothing_written")
    if len(note.body) > CHECK_NOTE_CHARS:
        raise InvalidInput("note_too_long")
    linked = (await papers_of(session, [note_id])).get(note_id, [])
    if len(linked) != 1:
        raise Conflict("note_not_on_one_paper")
    paper = await get_paper(session, linked[0])
    if not paper.has_pdf:
        raise Conflict("needs_full_text")
    if paper.status != PaperStatus.READY:
        raise Conflict("paper_not_ready")
    anchor, evidence, outline = _lens_ids(kind, await sections.paper_sections(session, paper.id))
    if not anchor and not evidence:
        raise Conflict("lens_empty")
    every = await chunk_sources(session, Chunk.id.in_([*anchor, *evidence]))
    whole = sum(len(c.text) for c in every) <= SMALL_PAPER_CHARS
    sources = every if whole else await _retrieved(session, paper.id, kind, note.body, anchor, evidence, embedder)
    if not sources:
        raise Conflict("lens_empty")
    prompt = PROMPT_TEMPLATE.format(
        task=TASKS[kind], context=format_context(paper, sources), outline=outline, label=LABELS[kind], note=note.body
    )
    prepared = Prepared(
        sources=sources, system=SYSTEM_PROMPT, prompt=prompt, whole_paper=whole, prompt_version=CHECK_PROMPT_VERSION
    )
    return PreparedCheck(prepared, note.id, paper.id, note.body, guard_for(note.body, (c.text for c in sources)))
