"""Evidence cards (M39 F5): a structured, quote-backed summary of one paper. One retrieval per field, one model call,
and every item checked: its quote must be a verbatim passage fragment (core/quotes) and every number in its values
must appear in that quote (core/numbers). An item that fails either check is never shown as a fact."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, BeforeValidator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat import claims, quotes, retrieval
from app.core.platform import llm_json, prompts, queue
from app.core.workspaces import workspaces
from app.domain import numbers
from app.domain.errors import Conflict, InvalidInput, NotFound
from app.models import Chunk, EvidenceCard, LLMOutput, Paper, PaperStatus

CARD_PROMPT_VERSION = 2
JOB_TIMEOUT = 20 * 60  # seconds; the job's registered timeout. A card `generating` longer than this is stale.
OUTPUT_KIND = "evidence_card"
PER_FIELD = 4
MAX_PASSAGES = 16
LEAD_CHUNKS = 2  # the abstract and opening: where the question, sample and headline effect are stated
CAPS = {"findings": 5, "effect_sizes": 8, "limitations": 5}
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("evidence_card", CARD_PROMPT_VERSION).split("\n<!-- prompt -->\n")
FIELD_QUERIES = {
    "research_question": "research question aims objectives hypotheses",
    "design": "method design procedure participants materials",
    "sample": "sample participants N recruited population demographics",
    "findings": "results findings showed significant",
    "effect_sizes": "effect size Cohen's d odds ratio confidence interval p value",
    "limitations": "limitations future work caveats generalizability",
}


def _text(value):
    return None if value is None else str(value)  # a model often writes 0.001 or 120 where a string is asked


def _cap(limit: int):
    return BeforeValidator(lambda v: v[:limit] if isinstance(v, list) else v)


Text = Annotated[str | None, BeforeValidator(_text)]


class _Item(BaseModel):
    value: Text = None
    passage: int | None = None
    quote: str = ""


class _Sample(BaseModel):
    n: int | None = None
    population: Text = None
    passage: int | None = None
    quote: str = ""


class _Effect(BaseModel):
    value: Text = None
    statistic: Text = None
    ci: Text = None
    p: Text = None
    outcome: Text = None
    passage: int | None = None
    quote: str = ""


class _CardReply(BaseModel):
    research_question: _Item | None = None
    design: _Item | None = None
    sample: _Sample | None = None
    findings: Annotated[list[_Item], _cap(CAPS["findings"])] = []
    effect_sizes: Annotated[list[_Effect], _cap(CAPS["effect_sizes"])] = []
    limitations: Annotated[list[_Item], _cap(CAPS["limitations"])] = []


# Per item type: its stored value keys, and the ones whose numbers must be in the quote.
_SHAPES = {
    _Item: (("value",), ("value",)),
    _Sample: (("n", "population"), ("n", "population")),
    _Effect: (("value", "statistic", "ci", "p", "outcome"), ("value", "statistic", "ci", "p", "outcome")),
}


@dataclass(frozen=True)
class CardView:
    paper_id: uuid.UUID
    status: str  # generating | ready | failed
    error: str | None = None  # not_ready | no_text | needs_full_text | model_error
    fields: dict = field(default_factory=dict)
    provenance: str = "llm"
    model: str | None = None
    prompt_version: int | None = None
    output_id: uuid.UUID | None = None
    updated_at: datetime | None = None


def _blank(item_type, flags: list[str]) -> dict:
    keys = _SHAPES[item_type][0]
    return {**dict.fromkeys(keys), "quote": None, "page": None, "chunk_id": None, "flags": flags}


def _verified(item, passages: list[dict], texts: list[str]) -> dict | None:
    """The kept item with its page and chunk, a blank item carrying the flag that dropped it, or None when the model
    claimed nothing."""
    keys, checked = _SHAPES[type(item)]
    data = {k: getattr(item, k) for k in keys}
    if all(v in (None, "") for v in data.values()):
        return None
    found = quotes.locate(item.quote, item.passage, texts) if item.quote.strip() else None
    if found is None:
        return _blank(type(item), ["unsupported"])
    quote, index = found
    if type(item) is _Effect and not numbers.tokens(str(item.value or "")):
        return _blank(type(item), ["no_statistic"])
    if not all(numbers.all_in(str(data[k]), quote) for k in checked if data[k] is not None):
        return _blank(type(item), ["number_not_in_source"])
    chunk_id = passages[index]["chunk_id"]
    return {**data, "quote": quote, "page": passages[index]["page"], "chunk_id": str(chunk_id), "flags": []}


def _fields(reply: _CardReply, passages: list[dict], texts: list[str]) -> dict:
    out = {}
    for name, item_type in (("research_question", _Item), ("design", _Item), ("sample", _Sample)):
        out[name] = _verified(getattr(reply, name), passages, texts) if getattr(reply, name) else None
        out[name] = out[name] or _blank(item_type, [])
    for name in CAPS:
        out[name] = [v for item in getattr(reply, name) if (v := _verified(item, passages, texts))]
    return out


async def _passages(session: AsyncSession, paper_id: uuid.UUID) -> tuple[list[dict], list[str]]:
    """The opening chunks, then the best chunks per field interleaved so no field starves; deduped and capped."""
    per_field = [
        await retrieval.retrieve(session, query, paper_ids=[paper_id], k=PER_FIELD) for query in FIELD_QUERIES.values()
    ]
    opening = await session.execute(
        select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal).limit(LEAD_CHUNKS)
    )
    chosen: dict[uuid.UUID, retrieval.RetrievedChunk] = {
        c.id: retrieval.RetrievedChunk(c.id, c.paper_id, c.page, c.section_title, c.bbox, c.text)
        for c in opening.scalars()
    }
    for rank in range(PER_FIELD):
        for found in per_field:
            if rank < len(found):
                chosen.setdefault(found[rank].id, found[rank])
    kept = list(chosen.values())[:MAX_PASSAGES]
    return [{"chunk_id": c.id, "page": c.page, "section": c.section} for c in kept], [c.text for c in kept]


def _prompt(passages: list[dict], texts: list[str]) -> str:
    numbered = "\n\n".join(
        f"[{i}] (page {p['page']}, section {p['section']}) {t}"
        for i, (p, t) in enumerate(zip(passages, texts, strict=True), start=1)
    )
    return PROMPT_TEMPLATE.format(passages=numbered)  # str.format only parses the template: braces in passages are safe


async def _write_output(session, paper_id, content: dict, passages, model, connection_name) -> uuid.UUID:
    output = LLMOutput(
        paper_id=paper_id, kind=OUTPUT_KIND, content=json.dumps(content),
        source_chunks=[p["chunk_id"] for p in passages], model=model, connection_name=connection_name,
        prompt_version=CARD_PROMPT_VERSION,
    )
    session.add(output)
    await session.commit()
    return output.id


async def _store(session: AsyncSession, view: CardView) -> CardView:
    """Upserts the paper's card. A failed generation keeps the fields of an earlier card."""
    card = await session.scalar(select(EvidenceCard).where(EvidenceCard.paper_id == view.paper_id))
    if card is None:
        card = EvidenceCard(paper_id=view.paper_id, fields={})
        session.add(card)
    card.status, card.error = view.status, view.error
    if view.status == "ready":
        card.fields = view.fields
    card.provenance, card.model = view.provenance, view.model
    card.prompt_version, card.output_id = view.prompt_version, view.output_id
    card.updated_at = datetime.now(UTC)
    await session.commit()
    return CardView(
        view.paper_id, card.status, card.error, card.fields, card.provenance, card.model, card.prompt_version,
        card.output_id, card.updated_at,
    )


async def build_card(session: AsyncSession, paper_id: uuid.UUID, *, llm=None, record: bool = True) -> CardView:
    """Builds the paper's evidence card from its full text and (with `record`) stores it with an llm_outputs row.

    A paper that isn't ready is `failed` / `not_ready`, a ready one without chunks `failed` / `no_text`; neither
    asks the model. Two invalid model replies are `failed` / `model_error` (the row records the failure). With
    `record=False` nothing is written (for the eval) and the view has no output_id.
    """
    paper = await session.get(Paper, paper_id)
    if paper is None:
        raise NotFound("paper_not_found", detail=f"Paper {paper_id} does not exist.")
    failed = None
    if not paper.has_pdf:  # an abstract-only chunk is not the full text
        failed = "needs_full_text"
    elif paper.status != PaperStatus.READY:
        failed = "not_ready"
    elif not await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == paper_id)):
        failed = "no_text"
    if failed:
        view = CardView(paper_id, "failed", failed)
        return await _store(session, view) if record else view
    passages, texts = await _passages(session, paper_id)
    llm = await claims._llm(session, llm)
    model, connection_name = getattr(llm, "model", "unknown"), getattr(llm, "connection_name", None)
    reply = await llm_json.ask_json(llm, SYSTEM_PROMPT, _prompt(passages, texts), _CardReply)
    if reply is None:
        view = CardView(paper_id, "failed", "model_error", model=model, prompt_version=CARD_PROMPT_VERSION)
        content = {"error": "model_error"}
    else:
        view = CardView(
            paper_id, "ready", fields=_fields(reply, passages, texts), model=model, prompt_version=CARD_PROMPT_VERSION
        )
        content = reply.model_dump()
    if not record:
        return view
    output_id = await _write_output(session, paper_id, content, passages, model, connection_name)
    return await _store(session, CardView(**{**view.__dict__, "output_id": output_id}))


def _view(card: EvidenceCard) -> CardView:
    return CardView(
        card.paper_id, card.status, card.error, card.fields, card.provenance, card.model, card.prompt_version,
        card.output_id, card.updated_at,
    )


async def request_cards(
    session: AsyncSession, *, paper_ids: list[uuid.UUID], workspace_id: uuid.UUID | None = None,
    regenerate: bool = False, confirm: bool = False,
) -> list[CardView]:
    """Marks each target paper's card `generating` and queues ONE background job for the new targets.

    A `ready` card is left alone unless `regenerate`; replacing an edited card also needs `confirm` (Conflict
    `card_edited_needs_confirm`, checked for every paper before anything changes). A card already `generating` is
    returned as is and not queued again, so two requests make one job. Returns one view per paper, in order.
    """
    if workspace_id is not None:
        await workspaces.require_writable(session, workspace_id)
    paper_ids = original_ids = list(dict.fromkeys(paper_ids))
    if not paper_ids:
        return []
    found = {p.id: p for p in await session.scalars(select(Paper).where(Paper.id.in_(set(paper_ids))))}
    if len(found) != len(set(paper_ids)):
        raise NotFound("paper_not_found")
    # A card needs the full text. One paper asked for by name is refused; a whole workspace skips those without.
    no_pdf = [i for i in paper_ids if not found[i].has_pdf]
    if no_pdf and workspace_id is None:
        raise InvalidInput("needs_full_text", detail="A paper needs its PDF before it gets an evidence card.")
    skipped = {i: CardView(i, "failed", "needs_full_text") for i in no_pdf}
    paper_ids = [i for i in paper_ids if i not in skipped]
    if not paper_ids:
        return list(skipped.values())
    if regenerate and not confirm and await session.scalar(
        select(func.count()).select_from(EvidenceCard).where(
            EvidenceCard.paper_id.in_(paper_ids), EvidenceCard.status == "ready",
            EvidenceCard.provenance == "llm_edited",
        )
    ):
        raise Conflict("card_edited_needs_confirm")
    # Insert missing rows first (ON CONFLICT: a concurrent request may have just made one), then read them all.
    await session.execute(
        pg_insert(EvidenceCard).values([{"paper_id": i, "status": "failed", "fields": {}} for i in paper_ids])
        .on_conflict_do_nothing(index_elements=["paper_id"])
    )
    cards = {
        c.paper_id: c
        for c in await session.scalars(
            select(EvidenceCard).where(EvidenceCard.paper_id.in_(paper_ids)).execution_options(populate_existing=True)
        )
    }
    stale_before = datetime.now(UTC) - timedelta(seconds=JOB_TIMEOUT)
    queued = []
    for paper_id in paper_ids:
        card = cards[paper_id]
        if card.status == "ready" and not regenerate:
            continue
        if card.status == "generating" and card.updated_at > stale_before:
            continue  # a job has it (a stale one is a lost job: queue it again)
        card.status, card.error, card.updated_at = "generating", None, datetime.now(UTC)
        queued.append(paper_id)
    await session.commit()
    if queued:
        try:
            await queue.enqueue("generate_evidence_cards", None if workspace_id is None else str(workspace_id),
                                [str(i) for i in queued])
        except Exception:
            for paper_id in queued:  # no job will run: don't leave the cards `generating` until they go stale
                cards[paper_id].status, cards[paper_id].error = "failed", "queue_error"
            await session.commit()
            raise
    return [skipped[i] if i in skipped else _view(cards[i]) for i in original_ids]


