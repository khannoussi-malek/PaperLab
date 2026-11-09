import time
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
    assert len(rules["overclaim"]) == 8
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


FLAGGED = [
    "Our method significantly improves accuracy.",
    "These results prove that our model is better.",
    "The model is robust.",
    "Our method generalizes to all domains.",
    "We reach state-of-the-art accuracy.",
    "The rule holds universally.",
    "We ran extensive experiments.",
    "We are the first to study this problem.",
    "This is the first work to combine both signals.",
]
LEGIT = [
    "The gain is significant ($p < 0.01$).",
    "The gain is significant under a paired t-test.",
    "Our method significantly outperforms the baselines (Table~\\ref{tab:main}).",
    "The difference is significant (Wilcoxon, 30 runs).",
    "The most significant bit is stored first.",
    "We keep four significant digits.",
    "We prove Theorem~\\ref{thm:main} in the appendix.",
    "This approach may prove useful in practice.",
    "Proof sketch: the bound proves tight when n grows.",
    "We approve the plan and improve the draft, as its provenance shows.",
    "We use robust standard errors throughout.",
    "The model is robust to noise (Table~\\ref{tab:noise}).",
    "Robustness checks are in Section 5.",
    "We train a generalized linear model.",
    "We generalize Definition 1 to graphs.",
    "It beats the prior state-of-the-art~\\cite{lee2020}.",
    "The formula is universally quantified over x.",
    "We ran extensive experiments on 12 datasets.",
    "Lee et al.~\\cite{lee} were the first to propose it.",
    "Transformers have proven effective for translation~\\cite{v17}.",
    "Proofs of this kind have proven useful~\\cite{lee}.",
    "The encoder is the first layer to see the input.",
]


AMBIGUOUS = ("significantly", "robust", "generalizes")  # word sense is unclear: info, never in the badge


@pytest.mark.parametrize("text", FLAGGED)
def test_overclaims_are_flagged_once_with_the_right_severity(text):
    [f] = run("wording.overclaim", text)
    expected = "info" if any(w in text for w in AMBIGUOUS) else "warning"
    assert (f.check, f.severity, f.line) == ("wording.overclaim", expected, 1)
    assert f.message.startswith('"') and "is a strong claim: " in f.message and f.fix_hint


@pytest.mark.parametrize("text", LEGIT)
def test_legitimate_uses_are_silent(text):
    assert run("wording.overclaim", text) == []


def test_robust_to_x_is_still_flagged_because_the_gap_is_evidence_not_the_object():
    [f] = run("wording.overclaim", "The model is robust to noise.")
    assert f.message == '"robust" is a strong claim: no table or figure in this sentence shows it.'


def test_significant_in_the_sense_of_important_is_flagged_honestly_as_info():
    [f] = run("wording.overclaim", "A significant challenge is noise.")
    assert f.severity == "info" and "no p-value or test name in this sentence" in f.message


def test_a_prove_hit_is_a_warning():
    [f] = run("wording.overclaim", "These results prove that our model is better.")
    assert f.severity == "warning"


def test_significant_message_and_hint_are_exact():
    [f] = run("wording.overclaim", "Our method significantly improves accuracy.")
    assert f.message == '"significantly" is a strong claim: no p-value or test name in this sentence.'
    assert f.fix_hint == ('Name the test and report the p-value or an interval, or write '
                          '"improves by <delta> (no significance test performed)". If you mean "important", say so.')


def test_a_p_value_in_the_next_sentence_does_not_excuse_significant():
    found = run("wording.overclaim", "The gains are significant. We report p < 0.01 in Table 1.")
    assert len(found) == 1


def test_proofs_headings_and_captions_are_not_scanned():
    text = ("\\begin{proof}\nThis proves it is robust.\n\\end{proof}\n\\caption{A robust model.}\n"
            "\\section{A robust method}\n")
    assert run("wording.overclaim", text) == []


def test_overclaim_on_a_thesis_sized_file_is_fast_and_does_not_split_every_sentence():
    # One guarded hit ("significant") used to split every sentence of the file with pylatexenc (1.6 s on a thesis)
    line = "We train the model on the corpus and report the mean over five seeds in the appendix " * 18
    body = "\n".join([line[:1500]] * 390) + "\nThe gain is significant."
    start = time.perf_counter()
    assert len(run("wording.overclaim", "\\section{Method}\n" + body)) == 1
    assert time.perf_counter() - start < 2.0  # measured ~0.2 s; was ~4.3 s before the fix
