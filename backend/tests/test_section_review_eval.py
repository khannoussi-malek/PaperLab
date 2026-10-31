import pytest
from pydantic import ValidationError

from evals import section_review_eval as ev

pytestmark = pytest.mark.anyio


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        yield self.replies.pop(0)


GATES = {"missing_recall_min": 0.5, "complete_clean_min": 0.5, "usable_lines_min": 0.5}
CASES = [
    ev.Case(role="method", sentences=["a", "b"], expect_missing=[]),
    ev.Case(role="method", sentences=["a"], expect_missing=[["baseline", "compare"], ["data"]]),
    ev.Case(role="results", sentences=["a"], notes=["gap"], expect_missing=[["numbers"]], expect_note="N1"),
]
GOOD = [
    "Supported: fine [S1]",
    "Missing: no baseline here\nSupported: ok [S1]",
    "Missing: the gap in [N1] about numbers",
]


def config(**gates):
    return ev.Config(gates=ev.Gates(**{**GATES, **gates}), cases=CASES)


async def test_metrics_and_gates():
    metrics, rows = await ev.evaluate(CASES, Scripted(*GOOD), None)
    # groups met: baseline yes, data no, numbers yes -> 2/3
    assert metrics.cases == 3 and metrics.errors == 0
    assert metrics.missing_recall == pytest.approx(2 / 3)
    assert metrics.complete_clean == 1.0 and metrics.usable_lines == 1.0
    assert rows[2]["note_hit"] is True
    assert ev.passes(metrics, ev.Gates(**{**GATES, "missing_recall_min": 0.6})) is True
    assert ev.passes(metrics, ev.Gates(**{**GATES, "missing_recall_min": 0.7})) is False


async def test_complete_section_with_many_missing_is_not_clean_and_dropped_lines_lower_usable():
    noisy = "Missing: a\nMissing: b\nRewrite it as: no"
    metrics, _ = await ev.evaluate(CASES[:1], Scripted(noisy), None)
    assert metrics.complete_clean == 0.0
    assert metrics.usable_lines == pytest.approx(2 / 3)


async def test_model_error_is_counted():
    metrics, rows = await ev.evaluate(CASES, Scripted("x", "x"), 1)
    assert metrics.cases == 1 and metrics.errors == 1 and rows[0]["error"] is True


async def test_exit_codes_and_out(tmp_path, capsys):
    out = tmp_path / "rows.jsonl"
    assert await ev.execute(config(), Scripted(*GOOD), None, out) == 0
    assert out.read_text().count("\n") == 3
    capsys.readouterr()
    assert await ev.execute(config(missing_recall_min=0.9), Scripted(*GOOD), None, None) == 1
    assert "missing recall 0.67 < 0.9" in capsys.readouterr().out
    assert await ev.execute(config(), Scripted(*(["x"] * 6)), None, None) == 1


def test_config_file_loads_two_cases_per_reviewable_role():
    from app.core.section_rubrics import RUBRICS

    cfg = ev.load_config(ev.CONFIG)
    assert len(cfg.cases) >= 16
    for role in RUBRICS:
        mine = [c for c in cfg.cases if c.role == role]
        assert sum(not c.expect_missing for c in mine) >= 1 and sum(bool(c.expect_missing) for c in mine) >= 1
    assert any(c.notes and c.expect_note for c in cfg.cases)


def test_config_validation():
    with pytest.raises(ValidationError):
        ev.Gates(**{**GATES, "usable_lines_min": 1.5})
    with pytest.raises(ValidationError):
        ev.Config.model_validate({"gates": GATES, "cases": []})
    with pytest.raises(ValidationError):
        ev.Case.model_validate({"role": "nope", "sentences": ["a"], "expect_missing": []})


def run_main(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["section_review_eval", *args])
    with pytest.raises(SystemExit) as info:
        ev.main()
    return info.value.code


def test_cli_bad_input_exits_2(monkeypatch, tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("gates: {missing_recall_min: 0.5, complete_clean_min: 0.5, usable_lines_min: 0.5}\ncases: []\n")
    assert run_main(monkeypatch, "--config", str(empty)) == 2
    assert run_main(monkeypatch, "--config", str(tmp_path / "missing.yaml")) == 2
    assert run_main(monkeypatch, "--limit", "0") == 2
