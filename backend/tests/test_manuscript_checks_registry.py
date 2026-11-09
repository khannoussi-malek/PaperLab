import logging
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from app.core.errors import InvalidInput
from app.core.manuscript_checks.base import Check, CheckContext, Finding, ManuscriptInfo
from app.core.manuscript_checks.registry import run_selected, select

INFO = ManuscriptInfo("m", "main.tex", "never", None, None, None)
CTX = CheckContext(MappingProxyType({}), frozenset(), INFO)


def f(check="a.one", severity="warning", file="a.tex", line=1, message="m"):
    return Finding(check, severity, file, line, message)


def stub(name, *findings, cost="cheap"):
    return Check(name, cost, "d", lambda ctx: list(findings))


def boom(ctx):
    raise RuntimeError("secret detail")


def test_findings_sorted_by_severity_file_line_with_none_last():
    a = stub("a.one", f(severity="info", file="a.tex", line=1), f(severity="error", file=None, line=None),
             f(severity="error", file="b.tex", line=2), f(severity="error", file="a.tex", line=None),
             f(severity="error", file="a.tex", line=9), f(severity="warning", file="a.tex", line=1))
    got = [(x.severity, x.file, x.line) for x in run_selected(CTX, [a]).findings]
    assert got == [("error", "a.tex", 9), ("error", "a.tex", None), ("error", "b.tex", 2), ("error", None, None),
                   ("warning", "a.tex", 1), ("info", "a.tex", 1)]


def test_counts_have_all_three_keys_and_ran_keeps_selection_order():
    run = run_selected(CTX, [stub("b.two"), stub("a.one", f(severity="info"))])
    assert run.counts == {"error": 0, "warning": 0, "info": 1}
    assert run.ran == ["b.two", "a.one"]


def test_a_crashing_check_becomes_one_error_finding_and_the_rest_still_run(caplog):
    with caplog.at_level(logging.ERROR):
        run = run_selected(CTX, [Check("x.boom", "cheap", "d", boom), stub("a.one", f())])
    crashed = [x for x in run.findings if x.check == "x.boom"]
    assert len(crashed) == 1 and crashed[0].severity == "error" and crashed[0].file is None
    assert crashed[0].message == "This check crashed: RuntimeError"
    assert "secret detail" not in crashed[0].message  # no internals in the finding
    assert any("x.boom" in r.getMessage() or r.exc_info for r in caplog.records)  # logged with the traceback
    assert any(x.check == "a.one" for x in run.findings)
    assert run.ran == ["x.boom", "a.one"]


@pytest.mark.parametrize("bad", [f(check="other.name"), f(severity="fatal")])
def test_a_finding_with_the_wrong_name_or_severity_is_handled_like_a_crash(bad):
    run = run_selected(CTX, [stub("a.one", bad, f())])
    assert [(x.check, x.severity) for x in run.findings] == [("a.one", "error")]
    assert run.findings[0].message.startswith("This check crashed:")


def test_select_by_names_by_cost_and_both():
    reg = (stub("a.one"), stub("b.two", cost="full"), stub("c.three"))
    assert [c.name for c in select(None, None, reg)] == ["a.one", "b.two", "c.three"]
    assert [c.name for c in select(["c.three", "a.one"], None, reg)] == ["a.one", "c.three"]  # registry order
    assert [c.name for c in select(None, "cheap", reg)] == ["a.one", "c.three"]
    assert [c.name for c in select(["b.two", "a.one"], "cheap", reg)] == ["a.one"]
    assert [c.name for c in select(None, "full", reg)] == ["a.one", "b.two", "c.three"]  # "full" = no filter


def test_select_unknown_name_is_invalid_input_and_lists_what_exists():
    with pytest.raises(InvalidInput, match="unknown_check") as caught:
        select(["nope"], None, (stub("a.one"),))
    assert caught.value.details["available"] == ["a.one"]


def test_finding_is_frozen():
    with pytest.raises(FrozenInstanceError):
        f().message = "x"
