"""A failed compile must say why in `errors`, and a compile's undefined citations and references come as a list."""

from pathlib import Path

import pytest

from app.core import latex_compile
from app.core.manuscript_agent_compile import undefined_keys

FIX = Path(__file__).parent / "fixtures" / "tectonic"

XDV_STDERR = """Requested font "ntxsym" at 7.3pt
error: something bad happened inside xdvipdfmx; its output follows:

===============================================================================
xdvipdfmx:fatal: Cannot proceed without .vf or "physical" font for PDF output...
===============================================================================
error: the xdvipdfmx engine had an unrecoverable error
caused by: Cannot proceed without .vf or "physical" font for PDF output...
"""
XDV_LOG = 'Could not locate a virtual/physical font for TFM "ntxsy5".\nxdvipdfmx:fatal: Cannot proceed\n'


def test_an_engine_failure_with_no_tex_error_is_reported_in_errors():
    result = latex_compile.finish(1, XDV_STDERR, XDV_LOG, None)
    assert result.ok is False and result.friendly == "font_missing"
    engine = [e for e in result.errors if e["kind"] == "engine"]
    assert engine and 'font for TFM "ntxsy5"' in engine[0]["message"]
    assert engine[0]["file"] is None and engine[0]["line"] is None


def test_any_unexplained_failure_names_the_engines_own_last_words():
    stderr = "note: Running TeX ...\nerror: something bad happened\ncaused by: out of cheese\n"
    result = latex_compile.finish(1, stderr, "", None)
    assert [e["message"] for e in result.errors if e["kind"] == "engine"] == ["out of cheese"]


def test_a_failure_with_nothing_said_still_gets_one_entry():
    result = latex_compile.finish(1, "", "", None)
    assert [e["kind"] for e in result.errors] == ["engine"]
    assert "no error" in result.errors[0]["message"].lower()


def test_a_tex_error_needs_no_engine_entry():
    stderr = "error: main.tex:3: Undefined control sequence\nerror: something bad happened\n"
    result = latex_compile.finish(1, stderr, "", None)
    assert [e["kind"] for e in result.errors] == ["error"]


def test_a_good_compile_adds_nothing():
    assert latex_compile.finish(0, "note: Writing `main.pdf`\n", "", b"%PDF").errors == []


def test_a_timeout_or_outside_file_keeps_its_own_message():
    stderr = "accessing absolute path /etc/passwd\nerror: nope\n"
    assert latex_compile.finish(1, stderr, "", None).friendly == "outside_file"


@pytest.mark.parametrize(
    ("log", "citations", "references"),
    [
        ("LaTeX Warning: Citation `smith2021' on page 1 undefined on input line 12.\n", ["smith2021"], []),
        ("Package natbib Warning: Citation `a:b' on page 2 undefined on input line 3.\n", ["a:b"], []),
        ("LaTeX Warning: Reference `tab:x' on page 1 undefined on input line 9.\n", [], ["tab:x"]),
        ("LaTeX Warning: Hyper reference `sec:y' on page 1 undefined on input line 9.\n", [], ["sec:y"]),
        # TeX wraps a log line at 79 characters, even in the middle of a key.
        ("LaTeX Warning: Citation `a_very_long_citation_key_that_runs_past_the_edge_of_th\ne_log' on page 1 undefined "
         "on input line 4.\n", ["a_very_long_citation_key_that_runs_past_the_edge_of_the_log"], []),
        ("LaTeX Warning: Citation `dup' on page 1 undefined on input line 1.\n"
         "LaTeX Warning: Citation `dup' on page 2 undefined on input line 8.\n", ["dup"], []),
        ("LaTeX Warning: There were undefined references.\n", [], []),
        ("", [], []),
    ],
)
def test_undefined_keys_are_read_from_the_log(log, citations, references):
    assert undefined_keys(log) == (citations, references)


def test_a_real_tectonic_log_gives_the_undefined_key():
    # \\cite{known1,missingkey,known2} compiled by the pinned Tectonic 0.17 (the warning wraps across two lines)
    assert undefined_keys((FIX / "undefcite_multi.main.log").read_text()) == (["missingkey"], [])


@pytest.mark.parametrize("size", ["small", "footnotesize", "scriptsize", "tiny"])
def test_the_images_font_cache_is_warmed_with_math_at_each_small_size(size):
    """A compile reads the images' cache only, and each size loads its own math fonts: $\\times10^{-5}$ in a \\small
    table failed the PDF step in the ACM template (ntxsy5) because nothing had fetched that font."""
    warm = (latex_compile.Path(__file__).parents[1] / "app/manuscript_templates/warm-results.tex").read_text()
    line = next(row for row in warm.splitlines() if row.startswith(f"{{\\{size}"))
    assert "$\\times10^{-5}$" in line
