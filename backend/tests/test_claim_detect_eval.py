import json

import pytest
from pydantic import ValidationError

from evals import claim_detect_eval as ev

pytestmark = pytest.mark.anyio


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        yield self.replies.pop(0)


def reply(flag):
    return json.dumps({"is_claim": flag, "reason": "because"})


CASES = [ev.Case(sentence=f"s{i}", expected=e) for i, e in enumerate(["claim", "claim", "not_claim", "not_claim"])]


def config(**gates):
    return ev.Config(gates=ev.Gates(**{"accuracy_min": 0.7, "claim_recall_min": 0.7, **gates}), cases=CASES)


async def test_metrics_and_gates():
    # one missed claim: recall 0.5, accuracy 0.75
    metrics, rows = await ev.evaluate(CASES, Scripted(reply(True), reply(False), reply(False), reply(False)), None)
    assert (metrics.cases, metrics.accuracy, metrics.claim_recall, metrics.errors) == (4, 0.75, 0.5, 0)
    assert [r["correct"] for r in rows] == [True, False, True, True]
    assert ev.passes(metrics, ev.Gates(accuracy_min=0.7, claim_recall_min=0.5)) is True
    assert ev.passes(metrics, ev.Gates(accuracy_min=0.7, claim_recall_min=0.6)) is False


async def test_model_error_counts_as_wrong_and_is_counted():
    metrics, rows = await ev.evaluate(CASES, Scripted("x", "x"), 1)
    assert metrics.cases == 1 and metrics.errors == 1 and rows[0]["correct"] is False


async def test_exit_codes_and_out(tmp_path, capsys):
    out = tmp_path / "rows.jsonl"
    good = [reply(True), reply(True), reply(False), reply(False)]
    assert await ev.execute(config(), Scripted(*good), None, out) == 0
    assert {"sentence", "expected", "is_claim", "correct", "seconds"} <= set(
        json.loads(out.read_text().splitlines()[0])
    )
    capsys.readouterr()
    missed = [reply(True), reply(False), reply(False), reply(False)]
    assert await ev.execute(config(claim_recall_min=0.9), Scripted(*missed), None, None) == 1
    assert "claim recall 0.50 < 0.9" in capsys.readouterr().out
    assert await ev.execute(config(), Scripted(*(["x"] * 8)), None, None) == 1  # no real model answer


def test_config_file_loads_with_enough_cases():
    cfg = ev.load_config(ev.CONFIG)
    assert len(cfg.cases) >= 24
    assert {c.expected for c in cfg.cases} == {"claim", "not_claim"}
    assert (
        sum(c.expected == "claim" for c in cfg.cases) >= 10 and sum(c.expected == "not_claim" for c in cfg.cases) >= 10
    )


def test_config_validation():
    with pytest.raises(ValidationError):
        ev.Gates(accuracy_min=1.5, claim_recall_min=0.5)
    with pytest.raises(ValidationError):
        ev.Config.model_validate({"gates": {"accuracy_min": 1, "claim_recall_min": 1}, "cases": []})
    with pytest.raises(ValidationError):
        ev.Case.model_validate({"sentence": "s", "expected": "maybe"})


def run_main(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["claim_detect_eval", *args])
    with pytest.raises(SystemExit) as info:
        ev.main()
    return info.value.code


def test_cli_bad_input_exits_2(monkeypatch, tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("gates: {accuracy_min: 0.7, claim_recall_min: 0.7}\ncases: []\n")
    assert run_main(monkeypatch, "--config", str(empty)) == 2
    assert run_main(monkeypatch, "--config", str(tmp_path / "missing.yaml")) == 2
    assert run_main(monkeypatch, "--limit", "0") == 2
