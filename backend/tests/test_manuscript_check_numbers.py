import math

from app.core.manuscript_checks import number_provenance as numbers


def truth(files):
    blanked = {p: t for p, t in files.items() if p.endswith(".tex")}
    return numbers.harvest(files, blanked)


def labelled(t, value):
    return {label for v, label in zip(t.values, t.labels) if abs(v - value) < 1e-9}


def test_no_data_file_and_no_table_number_means_no_truth():
    assert truth({"main.tex": "We reach 91.4.", "refs.bib": "@misc{a}"}) is None
    assert truth({"main.tex": "\\begin{tabular}{p{2.5cm}c} A & B \\end{tabular}"}) is None  # the spec is no cell


def test_csv_cells_rows_and_columns():
    t = truth({"r.csv": "seed,acc,note\n1,91.1,88.5 ± 0.3\n2,91.3,34%\n3,91.5,\"1,234\"\n"})
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
