import json

import pytest

from app.core import draft_review as dr
from app.core import draft_review_issues as di
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio
FILES = {
    "main.tex": "\\begin{document}\n\\section{Intro}\n"
    + " ".join(f"Claim number {i} says that method {i} beats baseline {i} on every single task." for i in range(30))
    + "\n\\end{document}\n"
}
PAPER, USED = di.assemble(FILES, "main.tex")


def item(i, **kw):
    return {
        "severity": "major",
        "section": "Intro",
        "summary": f"Claim {i} has no figure behind it",
        "evidence_quote": f"Claim number {i} says that method {i} beats baseline {i}",
        "close_criterion": "The claim must point to a number or a source",
    } | kw


class Routed:
    """Fake model. `reviews`: replies for reviewer calls in order (a dict is JSON-encoded; empty list left: no issues).
    `verdicts`: a function (summary, angle) -> bool refuted, default not refuted. A str reply is sent as is."""

    model = "fake:routed"

    def __init__(self, *reviews, verdicts=lambda summary, angle: False, reason="Because of the paper"):
        self.reviews, self.verdicts, self.reason, self.calls = list(reviews), verdicts, reason, []

    async def stream(self, system, prompt):
        self.calls.append((system, prompt))
        if system == dr.SYSTEM_PROMPT:
            reply = self.reviews.pop(0) if self.reviews else {"issues": []}
        else:
            summary = prompt.split("Issue: ", 1)[1].split("\n", 1)[0]
            angle = prompt.split("Angle: ", 1)[1].split("\n", 1)[0]
            reply = {"refuted": self.verdicts(summary, angle), "reason": self.reason}
        if isinstance(reply, Exception):
            raise reply
        yield reply if isinstance(reply, str) else json.dumps(reply)


async def run(llm, mode="light", stops_at=None):
    seen = []

    async def progress(stage, done):
        seen.append((stage, done))
        return stops_at is None or len(seen) <= stops_at

    return await dr.review(PAPER, USED, llm=llm, progress=progress, mode=mode), seen


def issues(lo, hi):
    return {"issues": [item(i) for i in range(lo, hi)]}


def test_the_call_numbers_come_from_the_mode_table():
    assert (dr.max_calls("light"), dr.max_calls("full")) == (11, 54)
    assert (dr.likely_calls("light"), dr.likely_calls("full")) == (11, 42)
    assert dr.estimates(1000)[1]["approx_input_tokens"] > dr.estimates(1000)[0]["approx_input_tokens"]


async def test_light_three_lenses_each_get_the_whole_paper_then_one_skeptic_per_issue():
    llm = Routed(issues(0, 1), issues(1, 2), issues(2, 3))
    result, seen = await run(llm)
    lens_prompts = [p for _, p in llm.calls[:3]]
    assert all(PAPER in p for p in lens_prompts) and len({p.split("\n")[0] for p in lens_prompts}) == 3
    assert len(llm.calls) == 6 == result.calls and [i["id"] for i in result.issues] == ["I-01", "I-02", "I-03"]
    assert seen[0] == ("Reviewer 1 of 3: Ideas and definitions", 0) and seen[3] == ("Skeptic 1 of 3", 3)
    assert result.counts["rounds_run"] == 1


async def test_bad_issues_are_dropped_and_counted_without_losing_their_siblings():
    bad = [item(1, close_criterion=""), item(2, evidence_quote="made up quote that is not there"), "oops", item(3)]
    result, _ = await run(Routed({"issues": bad}))
    assert [i["quote"][:14] for i in result.issues] == ["Claim number 3"]
    assert (result.counts["dropped_criterion"], result.counts["dropped_quote"], result.counts["dropped_invalid"]) == (
        1,
        1,
        1,
    )


async def test_a_reviewer_that_fails_is_counted_and_all_three_failing_fails_the_run():
    # a bad reply is not retried: reviewer 1 fails on its one call; reviewer 3 raises LLMError
    result, _ = await run(Routed("not json", issues(1, 2), LLMError("x")))
    assert result.counts["reviewers_failed"] == 2 and [i["id"] for i in result.issues] == ["I-01"]
    with pytest.raises(dr.ReviewFailed):
        await run(Routed("a", "b", LLMError("x"), LLMError("y")))


class Garbled(Routed):
    """Reviewers answer as Routed; every skeptic reply is text with no JSON object in it."""

    async def stream(self, system, prompt):
        if system == dr.SYSTEM_PROMPT:
            async for token in super().stream(system, prompt):
                yield token
            return
        self.calls.append((system, prompt))
        yield "no json here"


async def test_light_with_bad_json_makes_no_more_than_its_eleven_counted_calls():
    llm = Garbled(issues(0, 3), issues(3, 6), issues(6, 9))  # 9 candidates: 8 reach the skeptics, all garbled
    result, _ = await run(llm)
    assert len(llm.calls) == result.calls == dr.max_calls("light") == 11
    assert result.counts["skeptics_failed"] == 8 and len(result.issues) == 8


async def test_full_with_bad_json_makes_no_more_than_its_fifty_four_counted_calls():
    llm = Garbled(issues(0, 3), issues(3, 6), issues(6, 8), issues(8, 11), issues(11, 14), issues(14, 17))
    result, _ = await run(llm, mode="full")
    assert len(llm.calls) == result.calls == dr.max_calls("full") == 54
    assert result.counts["rounds_run"] == 2 and len(result.issues) == 16


async def test_light_one_skeptic_refuting_drops_the_issue_and_a_broken_skeptic_keeps_it():
    llm = Routed(issues(1, 3), verdicts=lambda summary, angle: "Claim 1 " in summary)
    result, _ = await run(llm)
    assert [i["summary"][:7] for i in result.issues] == ["Claim 2"]
    assert result.refuted == [{"summary": "Claim 1 has no figure behind it", "reason": "Because of the paper"}]
    result, _ = await run(Routed(issues(1, 2), verdicts=lambda s, a: "junk"))  # not a bool: invalid, retried, kept
    assert len(result.issues) == 1 and result.counts["skeptics_failed"] == 1


async def test_light_caps_at_eight_issues_and_eleven_calls():
    result, _ = await run(Routed(issues(0, 5), issues(5, 10), issues(10, 14)))  # 14 distinct spans
    assert len(result.issues) == 8 and result.counts["over_cap"] == 6 and result.calls == dr.max_calls("light") == 11


async def test_full_asks_three_angles_per_issue_and_drops_on_a_majority_of_refutes():
    angles = {}

    def verdicts(summary, angle):
        angles.setdefault(summary, []).append(angle)
        n = len(angles[summary])
        return {"Claim 1": [True, False, True], "Claim 2": [True, False, False]}[summary[:7]][n - 1]

    result, _ = await run(Routed(issues(1, 3), verdicts=verdicts), mode="full")
    assert [i["summary"][:7] for i in result.issues] == ["Claim 2"]  # 2 of 3 refuted: gone; 1 of 3: stays
    assert len(set(angles["Claim 1 has no figure behind it"])) == 3  # three different angles
    assert result.counts["refuted"] == 1


async def test_full_runs_two_rounds_and_its_call_count_matches_the_estimate():
    # round 1: 8 issues (3+3+2) -> 24 skeptics; round 2: 4 new issues -> 12 skeptics. 3+24 + 3+12 = 42
    llm = Routed(issues(0, 3), issues(3, 6), issues(6, 8), issues(8, 10), issues(10, 12))
    result, _ = await run(llm, mode="full")
    assert result.calls == len(llm.calls) == 42 == dr.likely_calls("full") and result.counts["rounds_run"] == 2
    assert len(result.issues) == 12 and result.calls <= dr.max_calls("full")


async def test_full_round_two_never_repeats_round_one_spans_and_stops_when_dry():
    # round 2 only repeats round 1's spans (all seen): no new candidates, so the loop ends and nothing is added
    llm = Routed(issues(0, 2), issues(0, 2), issues(0, 2), issues(0, 2), issues(0, 2), issues(0, 2))
    result, _ = await run(llm, mode="full")
    assert result.counts["rounds_run"] == 2 and result.calls == (3 + 2 * 3) + 3 and len(result.issues) == 2
    assert result.counts["dropped_seen"] > 0


async def test_full_stops_after_a_round_whose_issues_were_all_refuted():
    llm = Routed(issues(0, 2), verdicts=lambda s, a: True)
    result, _ = await run(llm, mode="full")
    assert result.counts["rounds_run"] == 1 and result.issues == [] and result.calls == 3 + 2 * 3


async def test_an_issue_refuted_in_round_one_stays_suppressed_in_round_two():
    llm = Routed(
        issues(0, 2),
        issues(2, 3),
        issues(0, 2),
        issues(0, 1),
        issues(1, 2),
        issues(0, 2),
        verdicts=lambda s, a: s.startswith("Claim 0 "),
    )
    result, _ = await run(llm, mode="full")
    assert [i["summary"][:7] for i in result.issues] == ["Claim 1", "Claim 2"]


async def test_a_skeptic_reason_with_wording_is_replaced_by_a_fixed_text():
    for reason in ('You could say "it is fine" instead', "word " * 41, "  "):
        llm = Routed(issues(1, 2), verdicts=lambda s, a: True, reason=reason)
        result, _ = await run(llm)
        assert result.refuted == [{"summary": "Claim 1 has no figure behind it", "reason": dr.MASKED_REASON}]
        assert result.counts["reasons_masked"] == 1


async def test_full_cancel_is_checked_before_every_skeptic_call():
    llm = Routed(issues(0, 1))
    with pytest.raises(dr.Cancelled):
        await run(llm, mode="full", stops_at=4)  # three reviewer steps, then the first skeptic step, then stop
    assert len(llm.calls) == 4  # three reviewers and one skeptic: no second angle ran


async def test_unavailable_propagates_and_a_false_progress_cancels():
    with pytest.raises(LLMUnavailable):
        await run(Routed(LLMUnavailable("down")))
    with pytest.raises(dr.Cancelled):
        await run(Routed(issues(0, 1)), stops_at=0)


async def test_fake_model_light_end_to_end_one_merged_issue_raised_by_all_three_lenses():
    llm = FakeLLM()
    result, _ = await run(llm)
    assert len(result.issues) == 1 and sorted(result.issues[0]["raised_by"]) == ["evidence", "ideas", "practice"]
    assert result.issues[0]["file"] == "main.tex" and result.issues[0]["line"] >= 1
    assert len(llm.calls) == 4  # three reviewers and one skeptic


async def test_fake_model_full_end_to_end_runs_round_two_which_is_dry():
    llm = FakeLLM()
    result, _ = await run(llm, mode="full")
    # round 1: 3 reviewers + 3 skeptics on the one merged issue; round 2: 3 reviewers, same quote, all seen = dry
    assert len(llm.calls) == 9 == result.calls and len(result.issues) == 1 and result.counts["rounds_run"] == 2
