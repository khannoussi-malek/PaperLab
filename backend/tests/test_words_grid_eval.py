from evals.words_grid import Table, cell_accuracy, load_tables, measure
from tests.conftest import TABLE_ROWS


def test_every_cell_right_scores_all_of_them():
    assert cell_accuracy([["a", "b"], ["1", "2"]], [["a", "b"], ["1", " 2 "]]) == (4, 4)


def test_a_wrong_cell_and_a_shape_mismatch_cost_cells():
    assert cell_accuracy([["a", "x"], ["1", "2"]], [["a", "b"], ["1", "2"]]) == (3, 4)
    # An extra column shifts nothing that matched, but every cell of the wider grid counts.
    assert cell_accuracy([["a", "b", "extra"]], [["a", "b"]]) == (2, 3)
    # A missing row costs its cells.
    assert cell_accuracy([["a", "b"]], [["a", "b"], ["1", "2"]]) == (2, 4)
    assert cell_accuracy([], [["a"]]) == (0, 1)


def test_a_captured_table_is_measured_with_the_preview_code(table_pdf):
    truth = [list(row) for row in TABLE_ROWS]
    table = Table(paper="Generated", label="Table 1", page=1, region=(60, 135, 420, 185), rows=truth)
    assert measure(table_pdf, table) == (9, 9)
    wrong = table.model_copy(update={"rows": [*truth[:-1], [*truth[-1][:2], "91.9"]]})
    assert measure(table_pdf, wrong) == (8, 9)


def test_the_tables_file_parses(tmp_path):
    path = tmp_path / "tables.yaml"
    path.write_text("- paper: BERT\n  label: Table 2\n  page: 6\n  region: [1, 2, 3, 4]\n  rows: [[a, b]]\n")
    assert load_tables(path) == [Table(paper="BERT", label="Table 2", page=6, region=(1, 2, 3, 4), rows=[["a", "b"]])]
