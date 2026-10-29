import json

import pytest

from app.core import claim_detect, prompts
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        yield self.replies.pop(0)


def test_prompt_loads_and_has_the_split():
    text = prompts.load("claim_detect", claim_detect.PROMPT_VERSION)
    system, template = text.split("\n<!-- prompt -->\n")
    assert "never suggest" in system.lower() and "{sentence}" in template
    assert claim_detect.SYSTEM_PROMPT == system


async def test_true_and_false_replies():
    yes = await claim_detect.classify("It cut errors by 40%.", llm=Scripted('{"is_claim": true, "reason": "a number"}'))
    no = await claim_detect.classify("In this section we plan.", llm=Scripted('{"is_claim": false, "reason": "plan"}'))
    assert (yes.is_claim, yes.reason, yes.model) == (True, "a number", "fake:scripted")
    assert no.is_claim is False


async def test_prose_around_the_json_still_parses():
    det = await claim_detect.classify("s", llm=Scripted('Sure! {"is_claim": true, "reason": "r"} Hope it helps.'))
    assert det.is_claim is True


async def test_two_invalid_replies_give_model_error():
    det = await claim_detect.classify("s", llm=Scripted("nope", "still nope"))
    assert (det.is_claim, det.reason, det.model) == (False, "model_error", "fake:scripted")


async def test_reason_is_truncated():
    det = await claim_detect.classify("s", llm=Scripted(json.dumps({"is_claim": True, "reason": "x" * 500})))
    assert len(det.reason) == 300


async def test_fake_llm_claim_detect_branch():
    llm = FakeLLM()
    assert (await claim_detect.classify("Accuracy was 91%.", llm=llm)).is_claim is True
    assert (await claim_detect.classify("Prior work shows this.", llm=llm)).is_claim is True
    assert (await claim_detect.classify("We describe the layout.", llm=llm)).is_claim is False


async def test_fake_llm_claim_check_branch_quotes_the_first_passage():
    from app.core import claims

    prompt = claims.PROMPT_TEMPLATE.format(
        claim="c",
        quoted_text="",
        passages="[1] (page 2, section A) The model reached high accuracy on the task.\n\n[2] (page 3) Other.",
    )
    reply = json.loads("".join([t async for t in FakeLLM().stream(claims.SYSTEM_PROMPT, prompt)]))
    assert reply["verdict"] == "supported" and reply["passage"] == 1
    assert reply["quote"] in "The model reached high accuracy on the task."
    assert len(reply["quote"].split()) >= 3
