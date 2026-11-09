from types import MappingProxyType

import pytest

from app.core.manuscript_checks import wording
from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo

INFO = ManuscriptInfo("m", "main.tex", "never", None, None, None)


def run(name, files):
    files = files if isinstance(files, dict) else {"main.tex": files}
    check = next(c for c in wording.CHECKS if c.name == name)
    return check.run(CheckContext(MappingProxyType(files), frozenset(), INFO))


def test_lists_parse_and_every_pattern_compiles():
    rules = wording.load_rules()
    assert len(rules["ai_phrase"]) == 13
    ids = [r.id for group in rules.values() for r in group]
    assert len(ids) == len(set(ids))


def test_ai_phrases_flagged_with_file_line_message_and_hint():
    found = run("wording.ai_phrase", "Intro.\nIt is worth noting that this works.\nWe delve into the data.\n")
    assert [(f.file, f.line, f.severity) for f in found] == [("main.tex", 2, "warning"), ("main.tex", 3, "warning")]
    assert found[0].check == "wording.ai_phrase"
    assert found[0].message.startswith('"It is worth noting" reads like stock AI phrasing: ')
    assert found[0].fix_hint == "Say it plainly or cut it; PaperLab never rewrites your text."


@pytest.mark.parametrize("text", [
    "It should be noted that x.", "It plays a crucial role.", "A testament to effort.", "A rich tapestry of ideas.",
    "Tapestry of methods.", "Delving into the data.", "In the realm of vision.", "Within the realm of vision.",
    "An ever-evolving field.", "In today's world, data grows.", "We navigate the landscape of tools.",
    "A paradigm shift occurred.", "A game-changer for vision.", "It is worth mentioning that x.",
])
def test_each_phrase_family_is_flagged(text):
    assert len(run("wording.ai_phrase", text)) == 1


def test_phrases_need_word_boundaries():
    assert run("wording.ai_phrase", "The plot displays a central role of noise.") == []


def test_in_order_to_is_info_with_its_own_hint():
    [f] = run("wording.ai_phrase", "We sample in order to save time.\n")
    assert (f.severity, f.fix_hint) == ("info", 'Use "to".')


def test_phrase_split_across_a_line_or_a_tilde_matches_at_its_first_line():
    found = run("wording.ai_phrase", "It is worth\nnoting this.\nA testament~to effort.\n")
    assert [f.line for f in found] == [1, 3]


def test_comments_math_headings_proofs_and_bib_files_are_not_scanned():
    text = ("% it is worth noting\n$\\text{a testament to}$\n\\section{A paradigm shift}\n"
            "\\begin{proof}\nIt should be noted that x.\n\\end{proof}\n")
    assert run("wording.ai_phrase", text) == []
    assert run("wording.ai_phrase", {"refs.bib": "@misc{a, note={a testament to}}"}) == []
