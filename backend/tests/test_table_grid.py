from app.core.table_grid import CAPTION_NAME_CHARS, GridCell, Word, caption_name, split_header, words_to_grid


def word(x0: float, top: float, text: str, width: float | None = None, height: float = 10) -> Word:
    """A word on a line whose top is `top`; its width defaults to 5 points per character."""
    return Word(x0, top, x0 + (width if width is not None else 5 * len(text)), top + height, text)


def texts(grid: list[list[GridCell]]) -> list[list[str]]:
    return [[cell.text for cell in row] for row in grid]


def test_words_on_shared_lines_and_shared_gaps_become_rows_and_columns():
    words = [
        word(72, 100, "System"), word(200, 100, "Dev"), word(300, 100, "Test"),
        word(72, 114, "BERT-B"), word(200, 114, "88.5"), word(300, 114, "87.0"),
        word(72, 128, "BERT-L"), word(200, 128, "90.9"), word(300, 128, "91.8"),
    ]  # fmt: skip

    grid = words_to_grid(words)

    assert texts(grid) == [["System", "Dev", "Test"], ["BERT-B", "88.5", "87.0"], ["BERT-L", "90.9", "91.8"]]
    assert grid[1][1] == GridCell("88.5", (200, 114, 220, 124))


def test_close_words_are_one_cell_and_sparse_columns_and_spanning_rows_keep_the_columns():
    words = [
        word(72, 100, "Parser"), word(200, 100, "Training"), word(320, 100, "F1"),
        # "Vinyals & Kaiser" and "WSJ only" are single cells: their words are a space apart.
        word(72, 114, "Vinyals"), word(109, 114, "&"), word(116, 114, "Kaiser"),
        word(200, 114, "WSJ"), word(217, 114, "only"), word(320, 114, "88.3"),
        # A group label crossing both gaps, like "Published results" in BERT's tables.
        word(72, 128, "Published"), word(119, 128, "results"), word(156, 128, "from"), word(178, 128, "others", 140),
        # A row with an empty middle column.
        word(72, 142, "Dyer"), word(320, 142, "91.7"),
    ]  # fmt: skip

    assert texts(words_to_grid(words)) == [
        ["Parser", "Training", "F1"],
        ["Vinyals & Kaiser", "WSJ only", "88.3"],
        ["Published results from others", "", ""],
        ["Dyer", "", "91.7"],
    ]


def test_more_spanning_rows_than_allowed_merge_the_columns_they_cross():
    labels = [word(72, top, "A long group label spanning", 250) for top in (100, 128, 156)]
    values = [cell for top in (114, 142) for cell in (word(72, top, "x"), word(300, top, "1.0"))]

    # Three rows cross the gap between x and 1.0, one more than SPANNING_ROWS: no column boundary survives.
    assert [len(row) for row in words_to_grid(labels + values)] == [1, 1, 1, 1, 1]


def test_a_subscript_stays_on_its_line():
    subscript = Word(78, 104, 100, 112, "model")
    words = [word(72, 100, "d"), subscript, word(200, 100, "512"), word(72, 120, "h"), word(200, 120, "8")]

    assert texts(words_to_grid(words)) == [["d model", "512"], ["h", "8"]]


def test_one_or_two_row_tables_still_split_into_columns():
    assert texts(words_to_grid([word(72, 100, "BLEU"), word(200, 100, "28.4")])) == [["BLEU", "28.4"]]


def test_no_words_is_an_empty_grid():
    assert words_to_grid([]) == []


REGION = (72.0, 100.0, 400.0, 200.0)


def test_the_nearest_table_caption_names_the_dataset_up_to_its_first_sentence():
    blocks = [
        ((72, 40, 400, 60), "Table 9: Too far above to belong to this table."),
        ((72, 70, 400, 95), "Table 3: Variations on the\nTransformer architecture. Unlisted values are identical."),
        ((72, 205, 400, 215), "Figure 2: A caption below, but not a table caption."),
    ]
    assert caption_name(blocks, REGION) == "Table 3: Variations on the Transformer architecture."


def test_a_caption_below_or_inside_the_box_counts_but_not_one_beside_it():
    below = ((72, 210, 400, 222), "Table 2. SQuAD 1.1 results")
    beside = ((420, 150, 560, 160), "Table 5: in the other column")
    inside = ((72, 102, 400, 112), "Table 1: drawn into the box")

    assert caption_name([below, beside], REGION) == "Table 2. SQuAD 1.1 results"
    assert caption_name([beside], REGION) is None
    assert caption_name([below, inside], REGION) == "Table 1: drawn into the box"


def test_a_long_caption_is_cut_at_a_word_with_an_ellipsis():
    long = "Table 4: " + "word " * 40
    name = caption_name([((72, 80, 400, 95), long)], REGION)

    assert name is not None and name.endswith("…") and len(name) <= CAPTION_NAME_CHARS
    assert name.removesuffix("…").split()[-1] == "word"


def test_a_column_only_two_rows_fill_is_not_swallowed_by_its_neighbour():
    """A blank cell in a short table used to drop a column's row count to SPANNING_ROWS, so the splitter read the
    column itself as a gap a label was crossing and merged it into the column on its left."""
    words = [
        word(72, 100, "Model"), word(200, 100, "MNLI"), word(300, 100, "QQP"),
        word(72, 114, "BERT-B"), word(200, 114, "84.6"), word(300, 114, "71.2"),
        word(72, 128, "BERT-L"), word(300, 128, "72.1"),  # no MNLI score for this row
    ]  # fmt: skip

    assert texts(words_to_grid(words)) == [
        ["Model", "MNLI", "QQP"],
        ["BERT-B", "84.6", "71.2"],
        ["BERT-L", "", "72.1"],
    ]


def test_a_header_row_of_names_becomes_the_column_names():
    grid = words_to_grid([
        word(72, 100, "System"), word(200, 100, "Dev"), word(300, 100, "Test"),
        word(72, 114, "BERT-B"), word(200, 114, "88.5"), word(300, 114, "87.0"),
    ])  # fmt: skip

    names, rows = split_header(grid)

    assert names == ["System", "Dev", "Test"]
    assert texts(rows) == [["BERT-B", "88.5", "87.0"]]


def test_a_first_row_holding_numbers_is_data_and_leaves_the_columns_unnamed():
    grid = words_to_grid([
        word(72, 100, "BERT-B"), word(200, 100, "88.5"),
        word(72, 114, "BERT-L"), word(200, 114, "90.9"),
    ])  # fmt: skip

    names, rows = split_header(grid)

    assert names == ["", ""]
    assert texts(rows) == [["BERT-B", "88.5"], ["BERT-L", "90.9"]]


def test_a_single_row_is_data_not_a_header():
    grid = words_to_grid([word(72, 100, "System"), word(200, 100, "Dev")])

    assert split_header(grid) == (["", ""], grid)
