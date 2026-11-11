import re

import pytest
from pydantic import ValidationError

from app.core import reporting_guidelines as rg
from app.core.errors import InvalidInput

ML_IDS = ("data.source data.size data.splits data.preprocessing data.leakage method.algorithm method.hyperparameters "
          "method.training eval.metrics eval.baselines eval.runs results.variance results.ablations repro.seeds "
          "repro.environment repro.availability limits.scope limits.failures").split()
ML_SECTIONS = ["Data", "Method", "Evaluation", "Results", "Reproducibility", "Limitations"]
SIZES = {"prisma2020": 27, "strobe": 22, "consort": 25, "ml": 18}


def test_loader_order_and_sizes():
    assert [g.id for g in rg.all_guidelines()] == ["prisma2020", "strobe", "consort", "ml"]
    assert {g.id: len(g.items) for g in rg.all_guidelines()} == SIZES


def test_official_ids_are_one_to_n_in_order_and_ml_ids_are_the_spec_ids():
    for gid in ("prisma2020", "strobe", "consort"):
        assert [i.id for i in rg.get(gid).items] == [str(n) for n in range(1, SIZES[gid] + 1)]
    assert [i.id for i in rg.get("ml").items] == ML_IDS


def test_every_item_is_short_one_sentence_with_a_section():
    for g in rg.all_guidelines():
        assert g.source.strip() and g.label.strip() and g.applies_to.strip()
        for i in g.items:
            assert i.section.strip() and i.text.strip() and ":" not in i.id
            assert len(i.text) <= 140, (g.id, i.id)
            assert len(re.findall(r"[.!?](?:\s|$)", i.text.strip())) <= 1, (g.id, i.id)


def test_ml_sections_in_order_and_ids_match_file_stems():
    sections = list(dict.fromkeys(i.section for i in rg.get("ml").items))
    assert sections == ML_SECTIONS
    for path in rg.DIR.glob("*.json"):
        assert rg.Guideline.model_validate_json(path.read_text()).id == path.stem


def _g(**over):
    base = {"id": "x", "label": "X", "applies_to": "a", "source": "s",
            "items": [{"id": "1", "section": "S", "text": "a"}]}
    return {**base, **over}


def test_bad_files_are_rejected():
    for bad in (_g(items=[{"id": "1", "section": "S", "text": "a"}, {"id": "1", "section": "S", "text": "b"}]),
                _g(items=[{"id": "1", "section": "S", "text": " "}]),
                _g(items=[{"id": "a:b", "section": "S", "text": "a"}]),
                _g(id="x:y"), _g(id=" ")):
        with pytest.raises(ValidationError):
            rg.Guideline.model_validate(bad)


def test_unknown_guideline():
    with pytest.raises(InvalidInput, match="unknown_guideline"):
        rg.get("nope")


def test_view_empty_and_counts():
    assert rg.view({}).guideline is None and rg.view({}).items == [] and rg.view({}).total == 0
    v = rg.view({"guideline": "ml", "ml:data.splits": True, "prisma2020:3": True, "Submit": True})
    assert (v.guideline, v.done, v.total) == ("ml", 1, 18)
    assert [i.id for i in v.items if i.ticked] == ["data.splits"]


def test_apply_is_pure_and_keeps_other_keys():
    before = {"Submit": True, "guideline": "prisma2020", "prisma2020:3": True}
    after = rg.apply(before, guideline="ml", tick=["data.splits"])
    assert before == {"Submit": True, "guideline": "prisma2020", "prisma2020:3": True}
    assert after == {"Submit": True, "guideline": "ml", "prisma2020:3": True, "ml:data.splits": True}
    back = rg.apply(after, guideline="prisma2020", untick=["3"])
    assert back == {"Submit": True, "guideline": "prisma2020", "ml:data.splits": True}


def test_choosing_a_guideline_ticks_nothing_and_ticking_is_idempotent():
    assert rg.apply({}, guideline="strobe") == {"guideline": "strobe"}
    once = rg.apply({}, guideline="strobe", tick=["1"])
    assert rg.apply(once, tick=["1"]) == once


def test_apply_errors_list_valid_ids_in_file_order():
    with pytest.raises(InvalidInput, match="unknown_item") as e:
        rg.apply({"guideline": "ml"}, tick=["99"])
    assert e.value.details["available"] == ML_IDS and e.value.details["unknown"] == ["99"]
    with pytest.raises(InvalidInput, match="unknown_guideline"):
        rg.apply({}, tick=["1"])
    with pytest.raises(InvalidInput, match="unknown_guideline"):
        rg.apply({}, guideline="nope")
