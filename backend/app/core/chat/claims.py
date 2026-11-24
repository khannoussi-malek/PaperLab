"""Claim verification (M39 F4): is a claim supported by a library paper? One model call over the paper's best
passages, a verbatim quote that is checked against them, and an llm_outputs row for provenance."""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat import quotes, retrieval
from app.core.notes import ai_notes
from app.core.platform import llm_connections, llm_json, prompts
from app.domain.doi import normalize_doi
from app.domain.errors import InvalidInput, NotFound
from app.models import Chunk, LLMOutput, Paper, PaperStatus
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm

CLAIM_PROMPT_VERSION = 3
PASSAGES = 6
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("claim_check", CLAIM_PROMPT_VERSION).split("\n<!-- prompt -->\n")
OUTPUT_KIND = "claim_check"
VERDICT_WORDS = {
    "supported": "Supported",
    "partially_supported": "Partly supported",
    "not_supported": "Not supported",
    "not_addressed": "Not addressed",
}
CHECKED = ("supported", "partially_supported")  # verdicts that must rest on a kept quote


logger = logging.getLogger(__name__)


class _Reply(BaseModel):
    verdict: Literal["supported", "partially_supported", "not_supported", "not_addressed"]
    passage: int | None = None
    quote: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ClaimCheck:
    claim: str
    paper_id: uuid.UUID
    paper_title: str
    verdict: str  # supported | partially_supported | not_supported | not_addressed | cannot_verify
    reason: str
    evidence_level: str  # full_text | abstract_only | metadata_only
    quote: str | None = None
    quote_page: int | None = None
    quote_section: str | None = None
    quote_chunk_id: uuid.UUID | None = None
    passages: list[dict] = field(default_factory=list)  # {chunk_id, page, section}; chunk_id None for an abstract
    confidence: str | None = None  # high | low
    model: str | None = None
    answered_by: str | None = None  # the model that answered, when a router names it; else `model`
    prompt_version: int = CLAIM_PROMPT_VERSION
    output_id: uuid.UUID | None = None
    note_id: uuid.UUID | None = None
    paper_status: str | None = None  # set when the paper is still being ingested (reason not_ready)
    quote_page_start: int | None = None  # page where a quote starts, when it began on an earlier page than quote_page


async def _paper(session: AsyncSession, paper_id: uuid.UUID | None, doi: str | None) -> Paper:
    if (paper_id is None) == (not doi):
        raise InvalidInput("claim_scope", detail="Give either a paper_id or a doi.")
    if paper_id is not None:
        paper = await session.get(Paper, paper_id)
    else:
        wanted = normalize_doi(doi) or doi.strip().lower()
        paper = await session.scalar(select(Paper).where(func.lower(Paper.doi) == wanted))
    if paper is None:
        raise NotFound("paper_not_in_library", detail=f"{doi or paper_id} is not in the library.", doi=doi)
    return paper


SCOPE_MARKS = re.compile(r"\s*\[(?:this paper|other source)\]")  # the reviewer's cite marks: not search words
# A figure such as 28.95 or 73 sits in a table chunk the vectors rank low; its exact words find it (2026-11-11).
FIGURE = re.compile(r"(?<![\w.])(?:\d+\.\d+|\d{2,})(?!\w)")

LEAD_CHARS = 300  # how much of a sentence's start, from the chunk before, the verifier is shown
_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*\s+")


def _dangles(text: str) -> bool:
    """True when the text ends mid-sentence: its last character (past closing quotes/brackets) isn't . ! ? :"""
    return not text.rstrip().rstrip("\"'”’)]").rstrip().endswith((".", "!", "?", ":"))


async def _predecessor(session, chunk) -> tuple[str, int | None]:
    """The text a lower-case-starting chunk continues: the chunk before it if that ends mid-sentence, else the last
    chunk of the previous page (a sidebar or figure caption can sit between the halves), else nothing
    as (text, page)."""
    ordinal = select(Chunk.ordinal).where(Chunk.id == chunk.id).scalar_subquery()
    queries = (
        select(Chunk.text, Chunk.page).where(Chunk.paper_id == chunk.paper_id, Chunk.ordinal == ordinal - 1),
        select(Chunk.text, Chunk.page)
        .where(Chunk.paper_id == chunk.paper_id, Chunk.page == chunk.page - 1)
        .order_by(Chunk.ordinal.desc())
        .limit(1),
    )
    for query in queries:
        row = (await session.execute(query)).first()
        if row and row.text.strip() and _dangles(row.text):
            return row.text, row.page
    return "", None


async def _leads(session, found) -> tuple[list[str], list[int | None]]:
    """For each passage that starts mid-sentence (its first letter is lower-case), the start of that sentence: the
    text after the last sentence end of its predecessor chunk. Chunks never cross a page, so a sentence over a page
    break is split, and its first half can hold the negation ("none of" | "the LLMs … correlate positively", pilot 2
    N1). Also the page each lead came from. Quotes are still taken from the passage itself."""
    leads, pages = [], []
    for chunk in found:
        before, page = await _predecessor(session, chunk) if chunk.text.lstrip()[:1].islower() else ("", None)
        ends = list(_SENTENCE_END.finditer(before))
        leads.append((before[ends[-1].end() :] if ends else before).strip()[-LEAD_CHARS:])
        pages.append(page)
    return leads, pages


async def _passages(
    session, paper: Paper, claim: str, quoted_text: str | None
) -> tuple[str, list[dict], list[str], list[str], list[int | None]]:
    """(evidence level, passage descriptions, passage texts, sentence starts, their pages):
    the best chunks, else the abstract."""
    # A paper saved without a PDF has only its abstract chunk: it is read as the abstract below, never as full text.
    has_chunks = (
        paper.has_pdf
        and paper.status == PaperStatus.READY
        and await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == paper.id))
    )
    if has_chunks:
        query = SCOPE_MARKS.sub("", claim)
        found = await retrieval.retrieve(
            session,
            f"{query} {quoted_text}" if quoted_text else query,
            paper_ids=[paper.id],
            k=PASSAGES,
            words=True if FIGURE.search(query) else None,
        )
        if found:
            leads, lead_pages = await _leads(session, found)
            return (
                "full_text",
                [{"chunk_id": c.id, "page": c.page, "section": c.section} for c in found],
                [c.text for c in found],
                leads,
                lead_pages,
            )
    if (paper.abstract or "").strip():
        return "abstract_only", [{"chunk_id": None, "page": None, "section": None}], [paper.abstract], [""], [None]
    return "metadata_only", [], [], [], []


def _prompt(claim: str, quoted_text: str | None, texts: list[str], passages: list[dict], leads: list[str]) -> str:
    def line(i, p, t, lead):
        if p["page"] is None:
            return f"[{i}] (abstract) {t}"
        cont = f" (continues a sentence that began: \"…{lead}\")" if lead else ""
        return f"[{i}] (page {p['page']}, section {p['section']}){cont} {t}"

    numbered = "\n\n".join(
        line(i, p, t, lead) for i, (p, t, lead) in enumerate(zip(passages, texts, leads, strict=True), start=1)
    )
    quoted = f"\nThe researcher quotes this from the paper: {quoted_text}\n" if quoted_text else ""
    # str.format only parses the template, so braces in the claim or passages are safe.
    return PROMPT_TEMPLATE.format(claim=claim, passages=numbered, quoted_text=quoted)


def _pick_quote(reply: _Reply, texts: list[str], leads: list[str]) -> tuple[str | None, int | None, bool, bool]:
    """(kept quote, 0-based passage index, a quote was asked for but dropped,
    it ran from the lead). The named passage is tried first
    (a number outside the passages counts as none), then every passage; the quote's passage wins over the named one.
    A quote that starts in a passage's marked lead and ends in the passage is kept too;
    one wholly in the lead is not."""
    if not reply.quote.strip():
        return None, None, False, False
    found = quotes.locate(reply.quote, reply.passage, texts)
    if found:
        return found[0], found[1], False, False
    named = reply.passage - 1 if reply.passage is not None and 1 <= reply.passage <= len(texts) else None
    order = ([named] if named is not None else []) + [i for i in range(len(texts)) if i != named]
    for i in order:
        if not leads[i]:
            continue
        kept, _ = quotes.check_quotes([reply.quote], [f"{leads[i]} {texts[i]}"], 1)
        if kept and quotes.fold(kept[0][0]) not in quotes.fold(leads[i]):
            return kept[0][0], i, False, True
    return None, None, True, False


async def _write_output(session, paper, claim, content: dict, passages, model, connection_name) -> uuid.UUID:
    output = LLMOutput(
        paper_id=paper.id,
        kind=OUTPUT_KIND,
        question=claim,
        content=json.dumps(content),
        source_chunks=[p["chunk_id"] for p in passages if p["chunk_id"] is not None],
        model=model,
        connection_name=connection_name,
        prompt_version=CLAIM_PROMPT_VERSION,
    )
    session.add(output)
    await session.commit()
    return output.id


async def _llm(session: AsyncSession, llm):
    if llm is not None:
        return llm
    connection, model = await llm_connections.resolve(session, None)
    return build_llm(connection, model.name)


RETRY_WAITS = (2.0, 5.0, 15.0)  # seconds; 4 of 30 real checks failed on a busy router, and most clear within this
sleep = asyncio.sleep  # tests replace it
_STATUS = re.compile(r"returned (\d{3})\b")


def _may_clear(exc: Exception) -> bool:
    """Whether a retry can help: a busy or unreachable model, not a rejected key, a missing model or a bad request."""
    if isinstance(exc, LLMUnavailable):
        return str(exc).startswith("Can't reach")
    status = _STATUS.search(str(exc))
    return status is None or int(status[1]) >= 500 or int(status[1]) in (408, 429)


async def _ask_with_retry(llm, system: str, prompt: str, model: type[BaseModel]) -> BaseModel | None:
    for wait in (*RETRY_WAITS, None):
        try:
            return await llm_json.ask_json(llm, system, prompt, model)
        except (LLMError, LLMUnavailable) as exc:
            if wait is None or not _may_clear(exc):
                raise
            logger.info("the model failed (%s); trying again in %s s", exc, wait)
            await sleep(wait)
    return None  # never reached: the last pass returns or raises


def _answered_by(llm) -> str:
    return getattr(llm, "last_model", None) or getattr(llm, "model", "unknown")


async def verify_claim(
    session: AsyncSession,
    claim: str,
    *,
    paper_id: uuid.UUID | None = None,
    doi: str | None = None,
    quoted_text: str | None = None,
    llm=None,
    save: bool = False,
) -> ClaimCheck:
    """Checks `claim` against one library paper (by id or by DOI, exactly one) and returns the verdict.

    A metadata-only paper (no chunks, no abstract) is `cannot_verify` / `no_text`: no model call and no llm_outputs
    row, since nothing was asked. Every other check writes an llm_outputs row and returns its id as `output_id`,
    including two invalid model replies (`cannot_verify` / `model_error`), whose content records the failure.
    `save` writes the verdict as an AI note on the quoted passage (unanchored when it can't be placed) and returns
    its id as `note_id`; a `cannot_verify` check is never saved.
    """
    if not claim.strip():
        raise InvalidInput("empty_claim", detail="The claim is empty.")
    paper = await _paper(session, paper_id, doi)
    level, passages, texts, leads, lead_pages = await _passages(session, paper, claim, quoted_text)
    base = {"claim": claim, "paper_id": paper.id, "paper_title": paper.title, "evidence_level": level}
    if level == "metadata_only":
        if paper.status not in (PaperStatus.READY, PaperStatus.FAILED):  # still ingesting: text may come
            return ClaimCheck(**base, verdict="cannot_verify", reason="not_ready", paper_status=str(paper.status))
        return ClaimCheck(**base, verdict="cannot_verify", reason="no_text")
    llm = await _llm(session, llm)
    model = getattr(llm, "model", "unknown")
    connection_name = getattr(llm, "connection_name", None)
    reply = await _ask_with_retry(llm, SYSTEM_PROMPT, _prompt(claim, quoted_text, texts, passages, leads), _Reply)
    if reply is None:
        content = {"verdict": "cannot_verify", "reason": "model_error"}
        output_id = await _write_output(session, paper, claim, content, passages, model, connection_name)
        return ClaimCheck(
            **base, verdict="cannot_verify", reason="model_error", passages=passages, model=model, output_id=output_id
        )
    quote, index, dropped, spans = _pick_quote(reply, texts, leads)
    chosen = passages[index] if index is not None else {}
    start = lead_pages[index] if spans and lead_pages[index] != chosen.get("page") else None
    low = dropped or (reply.verdict in CHECKED and quote is None)
    check = ClaimCheck(
        **base,
        verdict=reply.verdict,
        reason=reply.reason.strip(),
        quote=quote,
        quote_page=chosen.get("page"),
        quote_page_start=start,
        quote_section=chosen.get("section"),
        quote_chunk_id=chosen.get("chunk_id"),
        passages=passages,
        confidence="low" if low else "high",
        model=model,
        answered_by=_answered_by(llm),
    )
    content = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in asdict(check).items() if k != "passages"}
    output_id = await _write_output(session, paper, claim, content, passages, model, connection_name)
    note_id = None
    if save:
        body = f"Claim: {claim}\nVerdict: {VERDICT_WORDS[check.verdict]}. {check.reason}"
        note = await ai_notes.create_ai_note(session, paper.id, body, output_id, quote)
        note_id = note.id
    return ClaimCheck(**{**asdict(check), "output_id": output_id, "note_id": note_id})


