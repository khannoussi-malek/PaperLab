import pytest
from pydantic import ValidationError

from evals import diagram_eval as ev

pytestmark = pytest.mark.anyio


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        yield self.replies.pop(0)


def pic(*labels):
    nodes = "\n".join(f"\\node (n{i}) at ({i},0) {{{label}}};" for i, label in enumerate(labels))
    return f"<tikz>\n\\begin{{tikzpicture}}\n{nodes}\n\\end{{tikzpicture}}\n</tikz>"


GATES = {"compile_rate_min": 0.5, "nodes_present_min": 0.5, "invented_label_rate_max": 0.5}
CASES = [
    ev.Case(description="An encoder feeds a decoder.", nodes=["encoder", "decoder"]),
    ev.Case(description="Sensors feed a model.", nodes=["sensors", "model"]),
]


async def compiles(libraries, picture):
    return True


async def test_metrics_and_gates():
    llm = Scripted(pic("Encoder", "Decoder"), pic("Sensors", "Model", "Cache"))
    metrics, rows = await ev.evaluate(CASES, llm, None, compiles)
    assert (metrics.cases, metrics.errors, metrics.compile_rate, metrics.nodes_present) == (2, 0, 1.0, 1.0)
    assert metrics.invented_label_rate == pytest.approx(1 / 5)  # "Cache" is not in its description
    assert ev.passes(metrics, ev.Gates(**GATES)) and rows[1]["invented"] == ["Cache"]


async def test_a_case_that_does_not_compile_lowers_the_compile_rate():
    async def first_only(libraries, picture):
        return "Encoder" in picture

    metrics, _ = await ev.evaluate(
        CASES, Scripted(pic("Encoder", "Decoder"), pic("Sensors", "Model")), None, first_only
    )
    assert metrics.compile_rate == 0.5
    assert not ev.passes(metrics, ev.Gates(**{**GATES, "compile_rate_min": 0.9}))


async def test_a_guard_failure_never_reaches_the_compiler():
    calls = []

    async def spy(libraries, picture):
        calls.append(picture)
        return True

    bad = pic("Encoder", "Decoder").replace("{Decoder}", "{\\input{x}}")
    metrics, rows = await ev.evaluate(CASES[:1], Scripted(bad), None, spy)
    assert calls == [] and metrics.compile_rate == 0.0 and rows[0]["guard"]


async def test_a_missing_node_lowers_node_coverage_and_a_model_error_counts_as_none_found():
    metrics, _ = await ev.evaluate(CASES, Scripted(pic("Encoder"), "no block", "still none"), None, compiles)
    assert metrics.nodes_present == pytest.approx(1 / 4) and metrics.errors == 1
    assert not ev.passes(metrics, ev.Gates(**GATES))


async def test_execute_fails_when_every_call_failed(capsys):
    config = ev.Config(gates=ev.Gates(**GATES), cases=CASES[:1])
    assert await ev.execute(config, Scripted("x", "y"), None, None, compiles) == 1
    assert "no real model answer" in capsys.readouterr().out


def test_config_validation(tmp_path):
    with pytest.raises(ValidationError):
        ev.Case(description="", nodes=["a"])
    with pytest.raises(ValidationError):
        ev.Case(description="An encoder.", nodes=[])
    with pytest.raises(ValidationError):
        ev.Gates(**{**GATES, "extra": 1})
    bad = tmp_path / "d.yaml"
    bad.write_text("gates: {}\ncases: []\n")
    with pytest.raises(ev.EvalError):
        ev.load_config(bad)


def test_the_shipped_config_is_valid_and_names_each_node_in_its_description():
    config = ev.load_config(ev.CONFIG)
    assert len(config.cases) >= 12
    for case in config.cases:
        assert all(node.lower() in case.description.lower() for node in case.nodes), case.description


def test_no_tectonic_binary_is_bad_input(monkeypatch):
    monkeypatch.setattr(ev.settings, "tectonic_bin", "/nonexistent/tectonic")
    with pytest.raises(ev.EvalError, match="Tectonic"):
        ev.require_tectonic()
