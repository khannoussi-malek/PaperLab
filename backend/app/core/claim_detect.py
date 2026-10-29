"""Uncited-claim classifier (M27 slice D): does one plain sentence state a claim that needs a source? Judges only;
it never suggests wording (D118). Writes no llm_outputs row: provenance is `model` on the caller's check row."""

from dataclasses import dataclass

from pydantic import BaseModel

from app.core import llm_json, prompts

PROMPT_VERSION = 1
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("claim_detect", PROMPT_VERSION).split("\n<!-- prompt -->\n")
MAX_REASON = 300
MODEL_ERROR = "model_error"


class _Reply(BaseModel):
    is_claim: bool
    reason: str = ""


@dataclass(frozen=True)
class Detection:
    is_claim: bool
    reason: str
    model: str  # reason == MODEL_ERROR: the reply never parsed; the caller marks the sentence cannot_verify


async def classify(sentence: str, *, llm) -> Detection:
    model = getattr(llm, "model", "unknown")
    # str.format only parses the template, so braces in the sentence are safe.
    reply = await llm_json.ask_json(llm, SYSTEM_PROMPT, PROMPT_TEMPLATE.format(sentence=sentence), _Reply)
    if reply is None:
        return Detection(False, MODEL_ERROR, model)
    return Detection(reply.is_claim, reply.reason[:MAX_REASON], model)
