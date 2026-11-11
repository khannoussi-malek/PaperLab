import math
import time
from types import MappingProxyType

import pytest

from app.core.manuscript_checks import number_provenance as numbers
from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo

INFO = ManuscriptInfo("m", "main.tex", "never", None, None, None)
DATA = {"results.csv": "model,acc\nours,91.27\n"}


def run(files):
    files = files if isinstance(files, dict) else {**DATA, "main.tex": files}
    return numbers.CHECKS[0].run(CheckContext(MappingProxyType(files), frozenset(), INFO))


def truth(files):
    blanked = {p: t for p, t in files.items() if p.endswith(".tex")}
    return numbers.harvest(files, blanked)


def labelled(t, value):
    return {label for v, label in zip(t.values, t.labels) if abs(v - value) < 1e-9}


def test_no_data_file_and_no_table_number_means_no_truth():
    assert truth({"main.tex": "We reach 91.4.", "refs.bib": "@misc{a}"}) is None
    assert truth({"main.tex": "\\begin{tabular}{p{2.5cm}c} A & B \\end{tabular}"}) is None  # the spec is no cell


def test_csv_cells_rows_and_columns():
    t = truth({"r.csv": 'seed,acc,note\n1,91.1,88.5 ± 0.3\n2,91.3,34%\n3,91.5,"1,234"\n'})
    assert {91.1, 91.3, 91.5, 88.5, 0.3, 34.0, 1234.0} <= set(t.values)
    assert "mean of column acc in r.csv" in labelled(t, 91.3)
    assert "std of column acc in r.csv" in labelled(t, 0.2)
    assert not any("row" in label for label in t.labels)  # rows mix unlike columns: no row statistics


def test_json_walks_everything_and_aggregates_lists_and_records():
    text = '{"a": {"b": [0.5, 0.7]}, "c": "91.3%", "ok": true, "runs": [{"acc": 0.8}, {"acc": 0.9}], "n": null}'
    t = truth({"r.json": text})
    assert {0.5, 0.7, 91.3, 0.8, 0.9} <= set(t.values) and 1.0 not in t.values
    assert "mean of a list in r.json" in labelled(t, 0.6)
    assert "mean of acc in r.json" in labelled(t, 0.85)


def test_tabular_cells_count_on_their_own():
    tex = "\\begin{longtable}{lc} A & \\textbf{91.3} $\\pm$ 0.2 \\\\ \\end{longtable}"
    t = truth({"main.tex": tex})
    assert {91.3, 0.2} <= set(t.values) and labelled(t, 91.3) == {"a table in main.tex"}


def test_non_finite_values_never_enter_the_truth():
    t = truth({"r.csv": "a\n1e400\n" + "9" * 400 + "\nnan\n0.5\n", "r.json": "[1e400, 0.25]"})
    assert all(math.isfinite(v) for v in t.values) and {0.5, 0.25} <= set(t.values)


def test_broken_json_is_one_warning_at_its_line():
    t = truth({"r.json": '{"a": 1,\n}'})
    [f] = t.problems
    assert (f.check, f.file, f.line, f.severity) == ("numbers.unbacked", "r.json", 2, "warning")
    assert f.message.startswith("r.json could not be read (") and t.values == []


def test_one_cheap_check_named_numbers_unbacked():
    [check] = numbers.CHECKS
    assert (check.name, check.cost) == ("numbers.unbacked", "cheap")


def test_silent_without_data_files_or_table_numbers():
    assert run({"main.tex": "We reach 91.4 and 34\\% here.\\begin{tabular}{c} A \\end{tabular}"}) == []


def test_a_manuscript_with_only_a_tabular_is_checked():
    table = "\\begin{table}\\begin{tabular}{lc} Ours & 91.27 \\\\ \\end{tabular}\\end{table}\n"
    assert run({"main.tex": table + "We reach 91.3 here."}) == []
    [f] = run({"main.tex": table + "We reach 88.8 here."})
    assert (f.severity, f.line) == ("warning", 2)
    assert f.fix_hint.startswith("Nearest data value: 91.27 (a table in main.tex).")


def test_unbacked_decimal_flagged_with_line_and_nearest_value():
    [f] = run("Intro.\nOur model reaches 91.4 on the test set.\n")
    assert (f.check, f.file, f.line, f.severity) == ("numbers.unbacked", "main.tex", 2, "warning")
    assert f.message == '"91.4" matches no number in the manuscript\'s data files or tables'
    assert f.fix_hint == (
        "Nearest data value: 91.27 (results.csv). Check the number, or add the file it comes "
        "from; PaperLab never edits your text."
    )


def test_broken_data_file_warns_and_flags_nothing_else():
    [f] = run({"r.json": '{"a": 1,\n}', "main.tex": "We reach 91.4 here."})
    assert (f.file, f.line) == ("r.json", 2)


@pytest.mark.parametrize("cell", ["91.27", "91.25", "91.34", "91.3"])
def test_matches_after_rounding_to_the_shown_places(cell):
    assert run({"r.csv": f"acc\n{cell}\n", "main.tex": "We reach 91.3 here."}) == []


def test_a_short_plain_decimal_is_not_read_as_a_percent_of_a_large_value():
    assert len(run({"r.csv": "n\n200\n", "main.tex": "Ours is 2.0 times faster."})) == 1


def test_a_value_outside_the_rounding_window_is_flagged():
    assert len(run({"r.csv": "acc\n91.36\n", "main.tex": "We reach 91.3 here."})) == 1


@pytest.mark.parametrize(
    ("cell", "text"),
    [
        ("0.913", "We reach 91.3\\% accuracy."),
        ("0.9127", "We reach 91.3\\% accuracy."),
        ("91.3", "We reach 0.913 accuracy."),
        ("0.34", "In 34 percent of runs it fails."),
        ("0.913", "We reach \\SI{91.3}{\\percent} accuracy."),
        ("91.27", "We reach 91\\% accuracy."),
        ("0.913", "We reach 91.3\\,\\% accuracy."),
    ],
)
def test_percent_and_fraction_forms_match_each_other(cell, text):
    assert run({"r.csv": f"acc\n{cell}\n", "main.tex": text}) == []


def test_mean_and_std_of_a_column_back_the_prose():
    files = {"r.csv": "seed,acc\n1,91.1\n2,91.3\n3,91.5\n", "main.tex": "Mean accuracy is 91.30 with std 0.20 here."}
    assert run(files) == []


def test_a_tabular_cell_backs_the_prose():
    tex = "\\begin{table}\\begin{tabular}{c} 77.7 \\end{tabular}\\end{table}\nWe reach 77.7 here."
    assert run({"r.json": "[]", "main.tex": tex}) == []


@pytest.mark.parametrize(
    "text",
    [
        "As shown in Section 4.2 and Sec.~3.1, it works.",
        "See Table~\\ref{tab:main}, Figure 2.3, Fig.~5.1, Eq.~(2.4) and Appendix A.2.",
        "Results \\cref{sec:4.2} and \\eqref{eq:1.5} hold.",
        "In 2019 and between 2018 and 2020, 5 seeds and 300 epochs were used.",
        "We use Python 3.12, PyTorch 2.1, CUDA 11.8, version 1.4, v2.3.1 and Llama 3.1 here.",
        "Latency is 3.5 ms at 2.4 GHz with 12.5 dB, 1.5\\,s and \\SI{3.5}{\\milli\\second} here.",
        "We set the learning rate to 0.001, dropout of 0.1, weight decay 0.01, momentum 0.9 and epsilon 0.1.",
        "With $\\beta$ of 0.99 and $\\lambda$ = 0.5 we train.",
        "Math $x = 0.73$ and \\[ y = 0.42 \\] and \\begin{equation} z = 0.31 \\end{equation} stay out.",
        "Text.\n% a comment with 0.77\n",
        "ResNet reaches 76.1\\% top-1~\\cite{he2016} on it.",
        "As \\citet[p.~3.5]{smith2020} say.",
        "\\begin{figure}\\caption{Error is 0.66 here}\\end{figure}",
        "\\begin{tabular}{cc} 0.55 & 0.44 \\end{tabular}",
        "\\section{Results 2.5}\nSee \\url{https://x.org/1.2.3} and \\href{https://arxiv.org/abs/2101.12345}{it}.",
        "\\linespread{1.3}\\scalebox{0.8}{x} width=0.5\\textwidth [0.5] text.",
        "See §4.2, § 5.1 and \\S~6.3 for it.",
        "We use XGBoost 1.7, LightGBM 4.1, SQLite 3.45, ROS 2.0 and TensorRT 8.6.",
        "The draft was written by Claude Sonnet 5.5 (Anthropic) in one pass.",
        "We ran the baselines once to GPT-4o mini and once to Gemini 3.5 Flash.",
        "Postgres 16.15 with pgvector 0.8.6 stores the index.",
        "We used Claude Opus 4.1 and Claude Haiku 4.5 and PostgreSQL 15.2 with Docker 24.0.",
        "We use dropout probability of 0.5, label smoothing factor 0.1, warmup ratio 0.1 and momentum coefficient 0.9.",
        "Run \\texttt{--alpha 0.5} and \\verb|--beta 0.7| here.",
    ],
)
def test_false_positive_guards(text):
    assert run(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Smith et al. reached 85.2\\% \\cite{smith}.",
        "Smith et al. reached 85.2\\% on it \\citep{smith}.",
        "\\citet{smith} et al. reached 85.2\\% on it.",
        "They reached 85.2\\% \\parencite{smith} and 0.66 \\autocite{lee}, e.g. 0.77 as \\textcite{kim} says.",
    ],
)
def test_a_number_in_a_sentence_with_a_citation_is_exempt(text):
    # lead ruling: such numbers come from another paper, not the author's own results
    assert run(text) == []


@pytest.mark.parametrize(
    "product",
    [
        "Sonnet",
        "Opus",
        "Haiku",
        "Gemini",
        "Claude",
        "Postgres",
        "PostgreSQL",
        "Python",
        "Node",
        "Docker",
        "pgvector",
        "Ollama",
        "Qwen",
        "Mistral",
        "Phi",
        "GPT",
    ],  # the product word list lives once, in CUE_WORDS
)
def test_a_version_after_a_product_name_is_silent(product):
    assert run(f"We used {product} 4.5 here.") == []


@pytest.mark.parametrize(
    "text",
    [
        "The gain is significant (p = 0.03), p < 0.001 and p-value of 0.04.",
        "We use $\\alpha$ = 0.05 and alpha = 0.01 as levels.",
        "We report 95\\% confidence intervals and a 99.9\\% CI.",
    ],
)
def test_p_values_significance_and_confidence_levels_are_exempt(text):
    assert run(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Prior work is strong~\\cite{a}. Ours reaches 77.7\\% here.",
        "Cliff's delta = 0.42 here.",
        "Kappa 0.81 and Accuracy 0.85 here.",
        "Ours reaches \\textbf{77.7} here.",
        "The BLEU score is BLEU 32.4 here.",
        "With dropout of 0.1 we reach 77.7 here.",
        "Ours reaches 77.7 here, a 1,234.5 gain.",
    ],
)
def test_results_are_still_checked(text):
    found = run(text)
    assert found and all(f.severity == "warning" for f in found)


@pytest.mark.parametrize(
    "text",
    [
        "Ours improves by 4.2 points here.",
        "A gain of 1.5 here.",
        "Ours is 2.5 pp better.",
        "A drop of about 0.8 percentage points.",
        "Ours is higher than 77.7\\% here.",
        "It reduces by 3.3\\% here.",
        "Accuracy increased by 3.2\\% here.",
        "Loss decreased by 1.1 here.",
        "It dropped by 0.7 here.",
        "An improvement by 2.2 here.",
        "A 12.5\\% improvement here.",
        "A 12\\% gain here.",
    ],
)
def test_a_number_after_a_difference_cue_is_info(text):
    [f] = run(text)
    assert f.severity == "info" and f.message.endswith("may be a computed difference; no data file or table has it")
    assert f.fix_hint.endswith(
        "PaperLab does not compute differences, so check this one by hand; PaperLab never edits your text."
    )


@pytest.mark.parametrize(
    "text",
    [
        "Runs take 1.19\\,s each.",
        "The model needs 5.17\\,GB of memory.",
        "Latency is 24~ms per call.",
        "Latency is 24\\ ms per call.",
        "It took 1.97\\,\\text{s} in total.",
        "It took 1.97\\,\\mathrm{ms} here.",
        "It took 1.97~\\textrm{s} here.",
        "It took 1.97\\thinspace s here.",
    ],
)
def test_a_thin_space_tilde_or_escaped_space_before_a_unit_is_exempt(text):
    assert run(text) == []


def test_only_the_unbacked_decimals_are_flagged_next_to_a_unit_thin_space():
    flagged = {f.message.split('"')[1] for f in run("Times were 0.96, 1.19 and 1.97\\,s in total.")}
    assert flagged == {"0.96", "1.19"}


def test_a_plain_unbacked_decimal_is_still_flagged():
    [f] = run("Runs take 1.19 each.")
    assert f.severity == "warning"


def test_an_unbacked_number_after_an_ordinary_word_is_still_flagged():
    [f] = run("Our accuracy of 5.5 here.")
    assert f.severity == "warning"


def test_a_plain_unmatched_percent_is_still_a_warning():
    [f] = run("Ours reaches 93.1\\% here.")
    assert f.severity == "warning"


def test_more_than_the_cap_gives_one_info_summary():
    found = run("\n".join(f"Ours reaches {i}.5 here." for i in range(100, 130)))
    assert [f.severity for f in found].count("warning") == 25
    assert found[-1].severity == "info" and found[-1].message.startswith("More numbers in main.tex match no data")
    assert found[-1].line == 26


def test_a_thousand_unbacked_numbers_stay_cheap_and_capped():
    text = "\n".join(f"Ours reaches {i}.5 here." for i in range(100, 1100))
    start = time.perf_counter()
    found = run(text)
    assert time.perf_counter() - start < 0.5
    assert len(found) <= numbers.MAX_PER_FILE + 1
    assert found[-1].severity == "info" and "match no data" in found[-1].message


def test_a_data_file_over_512_kb_is_skipped_with_one_info():
    big = "value\n77.7\n" + "a" * (600 * 1024)
    [f] = run({"big.csv": big, "main.tex": "We reach 77.7 here."})
    assert (f.check, f.file, f.line, f.severity) == ("numbers.unbacked", "big.csv", None, "info")
    assert f.message == "This data file is too large to read for number checks (over 512 KB)."
    found = run({**DATA, "big.csv": big, "main.tex": "We reach 77.7 here."})
    assert [f.severity for f in found] == ["info", "warning"]  # 77.7 is not backed by the skipped file


def test_data_bib_and_markdown_files_are_not_scanned_as_prose():
    assert run({**DATA, "refs.bib": "@misc{a, note={0.5}}", "notes.md": "We reach 99.9"}) == []


def test_thesis_sized_manuscript_is_fast():
    line = ("We train the model on the corpus and report 90.27 over five seeds in the appendix " * 18)[:1500]
    text = "\\section{Results}\n" + "\n".join([line] * 390) + "\nOurs reaches 0.98765 here.\n"
    data = "seed,acc,loss\n" + "".join(f"{i},{90 + i % 100 / 100:.2f},{0.1 + i % 7 / 100:.3f}\n" for i in range(2500))
    start = time.perf_counter()
    assert len(run({"results.csv": data, "main.tex": text})) == 1
    assert time.perf_counter() - start < 2.0  # target 200 ms; prototype measured ~80 ms on the dev Mac


@pytest.mark.parametrize(
    "text",
    [
        "We use a significance level of 0.01 here.",
        "We use a significance level 0.05 here.",
        "Alpha level 0.05 is used here.",
        "We set an alpha of 0.05 here.",
    ],
)
def test_significance_and_alpha_levels_are_exempt(text):
    assert run(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "We use gamma 0.99 here.",
        "We use a discount factor of 1.0 here.",
        "We use a threshold of 0.5 here.",
        "We use temperature 0.7 here.",
        "We use a 0.75 sampling rate here.",
        "We sample with top-p 0.9 here.",
        "We sample with top p 0.9 here.",
    ],
)
def test_hyperparameter_cues_are_exempt(text):
    assert run(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "We split the data 0.8/0.1/0.1 for training, validation and test.",
        "We split the data 80/10/10 for training, validation and test.",
    ],
)
def test_split_ratios_are_exempt(text):
    assert run(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "It costs $12.50 per GPU hour.",
        "It costs \\$12.50 per GPU hour.",
        "It costs €3.20 here.",
        "It costs £4.50 here.",
    ],
)
def test_currency_amounts_are_exempt(text):
    assert run(text) == []


def test_one_huge_integer_skips_only_that_value():
    text = '{"big": ' + "9" * 400 + ', "v": 91.3}'
    assert run({"r.json": text, "main.tex": "We reach 91.3 here."}) == []


def test_blueprint_json_is_configuration_not_data():
    bp = '{"title": "T", "target_words": {"introduction": [400, 900]}}'
    # the only .json is the blueprint: the check stays silent (no truth)
    assert run({"blueprint.json": bp, "main.tex": "We reach 91.4 and wrote 400 here."}) == []
    # its numbers back nothing, even next to a real data file
    found = run({"blueprint.json": '{"x": 91.4}', "r.json": '{"acc": 0.85}', "main.tex": "We reach 91.4 here."})
    assert [f.message.split('"')[1] for f in found] == ["91.4"]
    # an unreadable blueprint is blueprint.words' to report, not this check's
    assert run({"blueprint.json": "nope", "r.json": '{"acc": 0.85}', "main.tex": "Ours 0.85."}) == []
