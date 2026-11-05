from app.core.chunking import BLOCK_CAP, Block, chunk_blocks, join_lines

BODY = 10.0


def prose(letter: str, chars: int) -> str:
    return ((letter * 4 + " ") * (chars // 5)).strip()


def para(page: int, y: float, text: str, size: float = BODY) -> Block:
    return Block(page=page, bbox=(72, y, 290, y + 40), text=text, size=size, bold=False)


def heading(page: int, y: float, text: str) -> Block:
    return Block(page=page, bbox=(72, y, 200, y + 11), text=text, size=BODY, bold=True)


def test_sections_pages_and_size_limits():
    blocks = [
        para(1, 50, prose("a", 400)),
        heading(1, 100, "1 Introduction"),
        para(1, 120, prose("b", 400)),
        para(1, 170, "figure label is tiny", size=5.0),  # dropped: far below body size
        para(1, 200, "Pre-training Fine-Tuning"),  # dropped: too few words to be prose
        para(1, 210, "3"),  # dropped: page number
        para(1, 220, prose("c", 400)),
        para(2, 50, prose("d", 400)),  # new page -> new chunk even within a section
        heading(2, 100, "2 Method"),
        para(2, 120, prose("e", 900)),
        para(2, 170, prose("f", 900)),  # would exceed max_chars -> new chunk
    ]
    chunks = chunk_blocks(blocks, max_chars=1500)

    assert [(c.page, c.section_title) for c in chunks] == [
        (1, None), (1, "1 Introduction"), (2, "1 Introduction"), (2, "2 Method"), (2, "2 Method"),
    ]
    assert chunks[1].text == prose("b", 400) + "\n\n" + prose("c", 400)
    assert len(chunks[1].bbox) == 2  # one rect per source block
    all_text = "".join(c.text for c in chunks)
    assert "figure label" not in all_text and "Fine-Tuning" not in all_text and "3" not in all_text
    assert [c.ordinal for c in chunks] == list(range(5))


def test_overlap_only_without_headings():
    blocks = [para(1, 50 * i, prose(str(i), 300)) for i in range(1, 7)]
    chunks = chunk_blocks(blocks, max_chars=1000)
    # 3 blocks fit per chunk; the last block of each chunk is repeated at the start of the next.
    assert chunks[1].text.startswith(prose("3", 300))
    assert all(c.section_title is None for c in chunks)


def test_join_lines_rejoins_hyphenated_words():
    assert join_lines(["effective trans-", "fer from", " ", "BERT-", "Large"]) == "effective transfer from BERT- Large"


def test_a_block_too_long_to_embed_is_split_at_word_boundaries():
    sentence = "The dose was reduced in patients with renal impairment. "
    text = (sentence * 600).strip()  # 33,000 characters
    chunks = chunk_blocks([heading(1, 40, "1 Dosing"), para(1, 100, text)])

    assert len(chunks) > 1
    assert all(len(c.text) <= BLOCK_CAP for c in chunks)
    assert all((c.page, c.section_title, c.bbox) == (1, "1 Dosing", [[72, 100, 290, 140]]) for c in chunks)
    assert " ".join(c.text for c in chunks).split() == text.split()
    assert all(c.text.endswith(".") for c in chunks)  # at sentence ends, while there are any


def test_a_block_with_no_spaces_still_splits():
    chunks = chunk_blocks([heading(1, 40, "1 Data"), para(1, 100, "x" * 30_000 + " end of it")])

    assert all(len(c.text) <= BLOCK_CAP for c in chunks)
    assert "".join(c.text.replace(" end of it", "") for c in chunks) == "x" * 30_000


def test_a_long_paragraph_that_can_be_embedded_stays_whole():
    """Splitting at MAX_CHARS lost answers further down the results (top 12: 28 to 26 of 33, measured 2026-11-04)."""
    text = prose("a", 6000)

    [chunk] = chunk_blocks([heading(1, 40, "1 Long"), para(1, 100, text)])

    assert chunk.text == text


def cell(page: int, y: float, text: str, table: int | None = 1, bold: bool = False) -> Block:
    return Block(page=page, bbox=(72, y, 290, y + 12), text=text, size=BODY, bold=bold, table=table)


def test_a_table_stays_in_one_chunk_with_its_header_past_the_chunk_size():
    """A chunk with "2.5" but not its column reads as a different dose (41% kept both, measured 2026-11-05)."""
    header = cell(1, 100, "Patient group dose mg", bold=True)
    rows = [cell(1, 120 + i, f"Row {i} with renal impairment {i}.5 mg " + "x" * 300) for i in range(8)]

    chunks = chunk_blocks([para(1, 40, prose("a", 400)), header, *rows, para(1, 300, prose("b", 400))], max_chars=1500)

    assert len(chunks) == 3  # the prose before, the table, the prose after
    assert chunks[1].text.startswith("Patient group dose mg")
    assert all(row.text in chunks[1].text for row in rows)
    assert len(chunks[1].text) > 1500


def test_a_tables_bold_cells_are_not_section_titles():
    table = [cell(1, 100, "Total", bold=True), cell(1, 120, "2.5 mg")]
    blocks = [heading(1, 40, "4.2 Posology"), para(1, 60, prose("a", 400)), *table]

    chunks = chunk_blocks(blocks)

    assert [c.section_title for c in chunks] == ["4.2 Posology", "4.2 Posology"]


def test_a_tables_short_and_small_cells_are_kept():
    blocks = [para(1, 40, prose("a", 400)), Block(1, (72, 100, 200, 110), "2.5 mg", 6.0, False, table=1)]

    assert "2.5 mg" in chunk_blocks(blocks)[-1].text


def test_a_table_past_the_block_cap_still_splits():
    rows = [cell(1, 100 + i, f"Row {i} " + "x" * 3000) for i in range(5)]

    assert all(len(c.text) <= BLOCK_CAP for c in chunk_blocks([para(1, 40, prose("a", 400)), *rows]))


def test_two_tables_are_two_chunks():
    chunks = chunk_blocks([cell(1, 100, "First table cell here"), cell(1, 200, "Second table cell here", table=2)])

    assert [c.text for c in chunks] == ["First table cell here", "Second table cell here"]


RUNNING_TEXT = "A long paragraph of ordinary running text about the study design and how it was run. " * 8


def test_a_tables_caption_and_column_heads_join_its_numbers():
    # Real case: the dyspnea-by-age table's numbers were alone in a chunk, so nothing about age or dyspnea found them.
    chunks = chunk_blocks([
        para(1, 40, RUNNING_TEXT),
        para(1, 100, "Table 12 Dyspnea by age group, safety analysis set"),
        para(1, 120, "Treatment under 65 years, 65 to 75 years, over 75 years"),
        cell(1, 140, "Ticagrelor 653 (12.43%) 439 (16.89%) 253 (18.29%)"),
        cell(1, 160, "Clopidogrel 377 (7.15%) 246 (10.05%) 180 (12.30%)"),
    ])

    assert len(chunks) == 2
    assert chunks[0].text == RUNNING_TEXT
    assert chunks[1].text.startswith("Table 12 Dyspnea by age group")
    assert "Treatment under 65" in chunks[1].text and "253 (18.29%)" in chunks[1].text


def test_a_long_paragraph_before_a_table_stays_where_it_was():
    chunks = chunk_blocks([para(1, 40, RUNNING_TEXT), cell(1, 100, "Ticagrelor 653 (12.43%) 439 (16.89%)")])

    assert [c.text for c in chunks] == [RUNNING_TEXT, "Ticagrelor 653 (12.43%) 439 (16.89%)"]


def test_text_on_the_page_before_never_joins_a_table():
    caption = para(1, 40, "Table 12 Dyspnea by age group, safety set")
    chunks = chunk_blocks([caption, cell(2, 40, "Ticagrelor 653 (12.43%)")])

    assert [c.page for c in chunks] == [1, 2]


def test_a_split_before_a_row_of_numbers_takes_the_caption_along_when_no_table_was_detected():
    # Real case: find_tables missed this table and the size limit fell between its column heads and its numbers.
    chunks = chunk_blocks([
        para(1, 40, prose("a", 1300)),
        para(1, 100, "Table 22: Patients with dyspnea AE by treatment"),
        para(1, 120, "Treatment under 65 years old, 65 to 75 years old, over 75 years old N=5252 N=2599"),
        para(1, 140, "Ticagrelor 653 (12.43%) 439 (16.89%) 253 (18.29%)"),
    ], max_chars=1450)

    assert chunks[-1].text.startswith("Table 22")
    assert "253 (18.29%)" in chunks[-1].text


def test_a_split_before_ordinary_prose_leaves_short_text_where_it_was():
    short = "A short closing remark about the study."
    blocks = [para(1, 40, prose("a", 1300)), para(1, 100, short), para(1, 120, prose("b", 400))]
    chunks = chunk_blocks(blocks, max_chars=1400)

    assert chunks[0].text.endswith(short)
