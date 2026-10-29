from pathlib import Path

from app.core.manuscript_sentences import cite_spans, claim_hash, in_range, split_sentences, to_plain

TEX = (Path(__file__).parent / "fixtures" / "review_sample.tex").read_text()


def _span(raw: str) -> tuple[int, int]:
    i = TEX.index(raw)
    return i, i + len(raw)


def test_fixture_sentences_and_offsets():
    sents = split_sentences(TEX)
    want = [
        ("We study retrieval for long papers and report gains.", ()),
        ("Smith et al. (2020) show that dense retrieval beats keyword search \\citep{smith2020}.", ("smith2020",)),
        ("Fig.~3 shows the main effect of chunk size on recall \\citep{a,b}.", ("a", "b")),
        ("The gap is significant when p < 0.05.", ()),
        ("Another claim holds e.g.\\ this one \\citet{lee19}.", ("lee19",)),
        ("This sentence spans\ntwo lines and is cited \\citep{span}.", ("span",)),
        ("First item says something quite useful here", ()),
        ("Second item is also a full sentence \\citep{item2}.", ("item2",)),
        ("A paragraph ends at the blank line without any period", ()),
        ("Dr. Jones reports 100\\% accuracy at 0.95 confidence level.", ()),
    ]
    assert [(s.start, s.end, s.keys) for s in sents] == [(*_span(r), k) for r, k in want]
    assert all(s.raw == TEX[s.start : s.end] for s in sents)


def test_hash_ignores_reflow_but_not_case_or_key():
    assert claim_hash("a  b\nc ") == claim_hash("a b c")
    assert claim_hash("A b") != claim_hash("a b")
    assert claim_hash("x \\citep{a}.") != claim_hash("x \\citep{b}.")
    s = next(s for s in split_sentences(TEX) if s.raw.startswith("This sentence spans"))
    assert s.norm == "This sentence spans two lines and is cited \\citep{span}." and s.hash == claim_hash(s.raw)


def test_comment_cites_ignored_and_cite_spans():
    assert "ghost" not in [k for s in split_sentences(TEX) for k in s.keys]
    spans = cite_spans(TEX)
    assert all(k != "ghost" for k, _ in spans)
    assert ("b", TEX[: TEX.index("\\citep{a,b}")].count("\n") + 1) in spans
    assert cite_spans("x\n\\citep{a,\n b}") == [("a", 2), ("b", 2)]


def test_short_and_skipped_pieces_are_not_sentences():
    raws = [s.raw for s in split_sentences(TEX)]
    assert not any("Short one" in r or "caption" in r or "mc^2" in r or "Introduction" in r for r in raws)
    assert split_sentences("One two three.") == []


def test_in_range_overlap_and_cursor():
    sents = split_sentences(TEX)
    i = TEX.index("two lines")
    assert [s.raw[:9] for s in in_range(sents, i, i + 3)] == ["This sent"]
    j = TEX.index("Fig.~3")
    k = TEX.index("Another claim")
    assert len(in_range(sents, j + 5, k + 5)) == 3
    assert len(in_range(sents, i, i)) == 1
    assert in_range(sents, 0, 0) == []


def test_to_plain():
    raw = "As \\emph{shown} in Fig.~3 with $x$ \\citep{a} we gain 5\\% more."
    assert to_plain(raw) == "As shown in Fig. 3 with x we gain 5% more."
