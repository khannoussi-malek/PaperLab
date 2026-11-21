"""Answer check (M34): is one cited sentence of a chat answer supported by the passages it cites? One model call per
sentence, reusing the claim check's reply, quote check and retries (M39 F4) with its own prompt. Never rewrites the
answer (D118)."""

import logging
from dataclasses import dataclass

from app.core import claims, prompts
from app.providers.base import LLMError, LLMUnavailable

ANSWER_CHECK_PROMPT_VERSION = 1
OUTPUT_KIND = "answer_check"
MAX_CHECK_SENTENCES = 20
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("answer_check", ANSWER_CHECK_PROMPT_VERSION).split("\n<!-- prompt -->\n")
NO_ANSWER = "The model didn't answer."

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckPassage:
    label: str  # "C3"
    paper_title: str
    page: int | None  # None: the abstract
    section: str | None
    text: str
    shortened: bool  # only the snapshot's cut copy was left (the chunk was replaced by a re-ingest)


@dataclass(frozen=True)
class SentenceVerdict:
    verdict: str  # supported | partially_supported | not_supported | not_addressed | couldnt_check
    reason: str
    quote: str | None
    quote_label: str | None
    confidence: str | None  # high | low; None when it couldn't be checked


def _line(number: int, passage: CheckPassage) -> str:
    paper = f'paper "{passage.paper_title}"'
    where = f"abstract, {paper}" if passage.page is None else f"page {passage.page}, section {passage.section}, {paper}"
    return f"[{number}] ({where}) {passage.text}"


def _prompt(sentence: str, passages: list[CheckPassage]) -> str:
    numbered = "\n\n".join(_line(i, p) for i, p in enumerate(passages, start=1))
    return PROMPT_TEMPLATE.format(sentence=sentence, passages=numbered)  # braces in the texts are safe in .format


async def check_sentence(llm, sentence: str, passages: list[CheckPassage]) -> SentenceVerdict:
    try:
        reply = await claims._ask_with_retry(llm, SYSTEM_PROMPT, _prompt(sentence, passages), claims._Reply)
    except (LLMError, LLMUnavailable) as exc:
        logger.info("answer check: the model failed on a sentence (%s)", exc)
        reply = None
    if reply is None:
        return SentenceVerdict("couldnt_check", NO_ANSWER, None, None, None)
    texts = [p.text for p in passages]
    quote, index, dropped, _ = claims._pick_quote(reply, texts, [""] * len(texts))
    low = dropped or (reply.verdict in claims.CHECKED and quote is None)
    label = passages[index].label if index is not None else None
    return SentenceVerdict(reply.verdict, reply.reason.strip(), quote, label, "low" if low else "high")
