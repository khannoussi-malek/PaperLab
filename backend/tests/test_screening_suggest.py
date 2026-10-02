import pytest

from app.core.screening_suggest import SYSTEM_PROMPT, Suggestion, build_prompt, parse_reply
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(("text", "expected"), [
    ("INCLUDE\nAn RCT in adults.", Suggestion("include", None, "An RCT in adults.")),
    ("exclude wrong_study_type\nA review.", Suggestion("exclude", "wrong_study_type", "A review.")),
    ("\n  EXCLUDE   Wrong_Topic  \n\n Off topic. \n", Suggestion("exclude", "wrong_topic", "Off topic.")),
    ("UNSURE\nNo abstract.", Suggestion("unsure", None, "No abstract.")),
    ("INCLUDE", Suggestion("include", None, None)),
    ("EXCLUDE\nno reason given", Suggestion("unsure", None, None)),
    ("EXCLUDE bad_reason\nx", Suggestion("unsure", None, None)),
    ("Sure! I think this should be excluded.", Suggestion("unsure", None, None)),
    ("", Suggestion("unsure", None, None)),
])  # fmt: skip
def test_parse_reply(text, expected):
    assert parse_reply(text) == expected


def test_note_is_cut_to_300_characters():
    assert len(parse_reply("INCLUDE\n" + "x" * 500).note) == 300


def test_prompt_carries_criteria_title_and_abstract_and_tolerates_braces():
    prompt = build_prompt("RCTs {adults}", "Sleep {trial}", None)
    assert "RCTs {adults}" in prompt and "Sleep {trial}" in prompt and "(no abstract)" in prompt


def test_system_prompt_lists_every_reason_and_the_reply_format():
    for reason in ("wrong_topic", "wrong_study_type", "duplicate", "language", "inaccessible", "other"):
        assert reason in SYSTEM_PROMPT
    assert "INCLUDE" in SYSTEM_PROMPT and "UNSURE" in SYSTEM_PROMPT


async def test_fake_llm_answers_the_screening_prompt_in_format():
    text = "".join([t async for t in FakeLLM().stream(SYSTEM_PROMPT, build_prompt("c", "t", "a"))])
    assert parse_reply(text) == Suggestion("exclude", "wrong_study_type", "A review, not a primary study.")
