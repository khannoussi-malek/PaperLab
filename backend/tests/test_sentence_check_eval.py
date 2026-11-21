import pytest
import yaml

from app.providers.llm import FakeLLM
from evals import sentence_check_eval as ev

pytestmark = pytest.mark.anyio

PASSAGE = {"paper": "Attention Is All You Need", "page": 8, "section": "Results",
           "text": "On the WMT 2014 English-to-German translation task, the big transformer model outperforms "
                   "the best previously reported models by more than 2.0 BLEU, establishing a new "
                   "state-of-the-art BLEU score of 28.4."}


def config(*cases, runs_flagged=3, supported_ok=2) -> ev.Config:
    return ev.Config.model_validate({
        "gates": {"unsupported_flagged_runs": runs_flagged, "supported_ok_runs": supported_ok},
        "cases": list(cases),
    })


def case(case_id, answer, sentences, kind="true"):
    return {"id": case_id, "kind": kind, "answer": answer, "passages": {"C1": PASSAGE}, "sentences": sentences}


SUPPORTED = case("true-bleu", "The big model reached 28.4 BLEU [C1]. Ask a colleague.", [
    {"role": "supported", "accept": ["supported", "partially_supported"]},
    {"role": "uncited", "accept": ["not_cited"]},
])
PLANTED = case("wrong-architecture", "The big model relies on recurrent layers [C1].", [
    {"role": "unsupported", "accept": ["partially_supported", "not_supported", "not_addressed"]},
], kind="contradicted")


def test_a_bad_file_is_refused(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"cases": [{"id": "x"}]}))
    with pytest.raises(ev.EvalError):
        ev.load_config(path)


def test_sentence_count_must_match_the_answer():
    broken = case("short", "One [C1]. Two [C1].", [{"role": "supported", "accept": ["supported"]}])
    with pytest.raises(ev.EvalError, match="short"):
        ev.check_cases(config(broken))


def test_the_shipped_cases_load_and_match_their_answers():
    loaded = ev.load_config(ev.CONFIG)
    ev.check_cases(loaded)
    kinds = {c.kind for c in loaded.cases}
    assert {"true", "contradicted", "missing_number", "overstated", "second_passage", "uncited"} <= kinds


async def test_fake_model_passes_a_supported_case():
    result = await ev.execute(config(SUPPORTED), FakeLLM(), runs=3)
    assert result.failures == []
    assert result.passed is True


async def test_fake_model_misses_a_planted_unsupported_sentence():
    result = await ev.execute(config(PLANTED), FakeLLM(), runs=3)
    assert result.passed is False
    assert any("wrong-architecture" in failure for failure in result.failures)


async def test_main_exit_codes(tmp_path, monkeypatch):
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(config(SUPPORTED).model_dump()))

    async def fake_llm(_model_id):
        return FakeLLM()

    monkeypatch.setattr(ev, "model_llm", fake_llm)
    assert await ev.run(["--config", str(path), "--runs", "1"]) == 0
    path.write_text(yaml.safe_dump(config(PLANTED).model_dump()))
    assert await ev.run(["--config", str(path), "--runs", "1"]) == 1
    path.write_text("cases: [{id: x}]")
    assert await ev.run(["--config", str(path)]) == 2
