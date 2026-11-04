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
