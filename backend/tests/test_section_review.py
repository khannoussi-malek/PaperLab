import pytest

from app.core import section_review as sr
from app.core.section_rubrics import RUBRICS
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    async def stream(self, system, prompt):
        self.calls += 1
        yield self.replies.pop(0)


def test_prompt_loads_with_split_and_never_rewrite():
    assert sr.PROMPT_VERSION == 2
    assert "never writes, rewrites, quotes back or suggests wording" in sr.SYSTEM_PROMPT
    assert "{role}" in sr.PROMPT_TEMPLATE and "<!-- prompt -->" not in sr.SYSTEM_PROMPT


def test_build_prompt_numbers_and_only_this_roles_checklist():
    text = sr.build_prompt("method", ["We sampled 40 users.", "We logged clicks."], ["Check the sample."])
    assert "[S1] We sampled 40 users." in text and "[S2] We logged clicks." in text
    assert "[N1] Check the sample." in text
    assert RUBRICS["method"][0].text in text
    assert RUBRICS["abstract"][0].text not in text
    assert "No notes." in sr.build_prompt("method", ["A."], [])


def test_parse_keeps_well_formed_lines():
    reply = (
        "Missing: no baseline is compared.\n"
        "Unsupported: the claim of speed has no number [S2]\n"
        "Supported: the aim is stated [S1] and noted [N1]\n"
        "Missing: the gap in [N1]"
    )
    findings, dropped = sr.parse_findings(reply, 2, 1)
    assert dropped == 0
    assert [f.kind for f in findings] == ["missing", "unsupported", "supported", "missing"]
    assert findings[0].refs == ()
    assert findings[2].refs == (sr.Ref("S", 1), sr.Ref("N", 1))


def test_parse_ignores_chatter_around_lines():
    reply = "Sure, here is my review:\n\n- Missing: no data source named.\nHope this helps!\n"
    findings, dropped = sr.parse_findings(reply, 1, 0)
    assert [f.kind for f in findings] == ["missing"] and dropped == 0


@pytest.mark.parametrize(
    "line",
    [
        "Missing: rewrite it as “Sleep is vital for health every night.”",
        "Rewrite it as: Sleep is vital.",
        'Supported: says "sleep is vital for health every night" [S1]',
        "Supported: the opening should read better [S1]",
        "Missing: use this instead of the old one",
        "Unsupported: replace this sentence [S1]",
        "Missing: " + "word " * 26,
        "Unsupported: cites a sentence that is absent [S9]",
        "Supported: cites a note that is absent [N2]",
        "Unsupported: cites nothing at all",
        "Supported: cites nothing either",
        "Missing: try: adding a number",
        "Supported: opening is clear [S1]. You could say: Sleep matters for health a lot.",
        "Missing: Add a sentence such as Sleep is vital for health every night.",
        "Missing: for example, write: sleep is vital",
        'Missing: e.g. say "sleep"',
        "Missing: use \u2018Sleep is vital for health every night\u2019 here",
        "Missing: use \u00abSleep is vital for health every night\u00bb here",
        "Missing: use \u201eSleep is vital for health every night\u201c here",
        'Missing: write "Sleep is vital for health every night',
        "Missing: write \u201cSleep is vital for health every night",
    ],
)
def test_parse_drops_each_bad_kind(line):
    findings, dropped = sr.parse_findings(line, 2, 1)
    assert findings == [] and dropped == 1


def test_parse_markdown_numbering_spacing_and_duplicates():
    reply = (
        "**Missing:** no baseline.\n1. Supported : aim is clear [S1]\n2) *Unsupported:* a claim [S2]\n"
        "**Missing:** no baseline.\n- Missing:   no   baseline."
    )
    findings, dropped = sr.parse_findings(reply, 2, 0)
    assert [(f.kind, f.point) for f in findings] == [
        ("missing", "no baseline."),
        ("supported", "aim is clear [S1]"),
        ("unsupported", "a claim [S2]"),
    ]
    assert dropped == 0


def test_parse_short_quote_is_fine_and_caps_at_12():
    findings, dropped = sr.parse_findings('Supported: says "sleep is vital" [S1]', 1, 0)
    assert len(findings) == 1 and dropped == 0
    many = "\n".join(f"Missing: gap number {i}" for i in range(15))
    assert [len(x) if isinstance(x, list) else x for x in sr.parse_findings(many, 1, 0)] == [12, 3]


async def test_review_one_call():
    llm = Scripted("Missing: no baseline.\nSupported: aim is clear [S1]")
    result = await sr.review("results", ["We report 3 results."], [], llm=llm)
    assert llm.calls == 1 and len(result.findings) == 2 and result.dropped == 0 and result.model == "fake:scripted"


async def test_review_retries_once_then_model_error():
    llm = Scripted("I cannot help.", "Missing: no baseline.")
    result = await sr.review("results", ["A."], [], llm=llm)
    assert llm.calls == 2 and len(result.findings) == 1
    llm = Scripted("nothing", "still nothing")
    with pytest.raises(sr.ReviewFailed, match="model_error"):
        await sr.review("results", ["A."], [], llm=llm)
    assert llm.calls == 2


async def test_fake_llm_reply_parses():
    llm = FakeLLM(model="fake:x", connection_name="t", delay=0)
    result = await sr.review("method", ["Opening sentence.", "Second."], [], llm=llm)
    assert result.findings[0].kind == "missing" and RUBRICS["method"][0].text.rstrip(".") in result.findings[0].point
    assert any(f.kind == "supported" and f.refs == (sr.Ref("S", 1),) for f in result.findings)
    assert result.dropped == 0
