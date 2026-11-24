import json

import pytest

from app.core.chat import answer_check, claims
from app.core.chat.answer_check import CheckPassage, check_sentence
from app.providers.base import LLMError
from app.providers.llm_fake import FakeLLM

pytestmark = pytest.mark.anyio

PASSAGES = [
    CheckPassage("C1", "Attention Is All You Need", 3, "Results",
                 "On the WMT 2014 English-to-German task the big model reaches 28.4 BLEU.", False),
    CheckPassage("C2", "BERT", None, None, "BERT obtains new state-of-the-art results on eleven tasks.", False),
]


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    async def stream(self, system, prompt):
        self.prompts.append(prompt)
        yield self.replies.pop(0)


class Failing:
    model, connection_name = "fake:failing", "Test"

    async def stream(self, system, prompt):
        raise LLMError("the model returned 400 bad request")
        yield ""  # pragma: no cover


def reply(verdict="supported", passage=None, quote="", reason="It says so."):
    return json.dumps({"verdict": verdict, "passage": passage, "quote": quote, "reason": reason})


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(claims, "sleep", instant)


async def test_supported_with_kept_quote():
    result = await check_sentence(FakeLLM(), "The big model reaches 28.4 BLEU.", PASSAGES)
    assert result.verdict == "supported"
    assert result.quote_label == "C1"
    assert result.quote and result.quote in PASSAGES[0].text
    assert result.confidence == "high"


async def test_quote_not_in_passage_is_low_confidence():
    llm = Scripted(reply("supported", 1, "the model reaches 41.0 BLEU on French"))
    result = await check_sentence(llm, "It reaches 28.4 BLEU.", PASSAGES)
    assert result.verdict == "supported"
    assert result.quote is None
    assert result.confidence == "low"


async def test_not_supported_keeps_reason():
    llm = Scripted(reply("not_supported", 1, "", "The passage gives 28.4, not 32.4."))
    result = await check_sentence(llm, "It reaches 32.4 BLEU.", PASSAGES)
    assert result.verdict == "not_supported"
    assert result.reason == "The passage gives 28.4, not 32.4."
    assert result.confidence == "high"


async def test_quote_in_second_passage_names_its_label():
    llm = Scripted(reply("supported", 2, "new state-of-the-art results on eleven tasks"))
    result = await check_sentence(llm, "BERT set new results on eleven tasks.", PASSAGES)
    assert result.quote_label == "C2"


async def test_model_error_is_couldnt_check():
    result = await check_sentence(Failing(), "It reaches 28.4 BLEU.", PASSAGES)
    assert result.verdict == "couldnt_check"
    assert result.confidence is None
    assert result.quote is None


async def test_unreadable_reply_is_couldnt_check():
    result = await check_sentence(Scripted("not json", "still not json"), "It reaches 28.4 BLEU.", PASSAGES)
    assert result.verdict == "couldnt_check"


async def test_prompt_names_each_passage():
    llm = FakeLLM()
    await check_sentence(llm, "The big model reaches 28.4 BLEU.", PASSAGES)
    system, prompt = llm.calls[0]
    assert system == answer_check.SYSTEM_PROMPT
    assert '[1] (page 3, section Results, paper "Attention Is All You Need") On the WMT' in prompt
    assert '[2] (abstract, paper "BERT") BERT obtains' in prompt
    assert "The big model reaches 28.4 BLEU." in prompt


async def test_fake_llm_answers_the_new_prompt():
    llm = FakeLLM()
    tokens = [t async for t in llm.stream(answer_check.SYSTEM_PROMPT, answer_check._prompt("A claim.", PASSAGES))]
    assert claims._Reply.model_validate_json("".join(tokens)).verdict in claims.VERDICT_WORDS


async def test_a_number_missing_from_the_passages_caps_supported():
    llm = Scripted(reply("supported", 1, "the big model reaches 28.4 BLEU"))
    result = await check_sentence(llm, "The big model reaches 32.4 BLEU.", PASSAGES)
    assert result.verdict == "partially_supported"
    assert "32.4" in result.reason


async def test_numbers_match_with_or_without_thousands_separators():
    passages = [CheckPassage("C1", "Attention Is All You Need", 7, "5.2", "The big models were trained for 300,000 "
                             "steps (3.5 days).", False)]
    for sentence in ("It trained for 300,000 steps in 3.5 days.", "It trained for 300000 steps in 3.5 days."):
        llm = Scripted(reply("supported", 1, "trained for 300,000 steps"))
        assert (await check_sentence(llm, sentence, passages)).verdict == "supported"


async def test_the_number_guard_leaves_other_verdicts_alone():
    llm = Scripted(reply("not_supported", 1, "", "Different figure."))
    assert (await check_sentence(llm, "It reaches 99.9 BLEU.", PASSAGES)).verdict == "not_supported"
