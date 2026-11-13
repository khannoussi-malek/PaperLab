import pytest

from app.core import draft_review_issues as di
from app.core.finding_lines import grams

MAIN = (
    "\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n\\input{sections/a}\n"
    "% \\input{sections/hidden}\n\\input{sections/b}\n\\end{document}\nTRAILING\n"
)
FILES = {
    "main.tex": MAIN,
    "sections/a.tex": (
        "\\section{Intro}\nWe show that sleep improves memory in adults.\n% a commented line nobody reads\n"
    ),
    "sections/b.tex": "\\section{Results}\nAccuracy reached ninety percent on the held-out split.\n",
    "sections/hidden.tex": "hidden text",
}
QUOTE = "sleep improves memory in adults"


def issue(**kw):
    return {
        "severity": "major",
        "section": "Intro",
        "summary": "The memory claim has no figure behind it",
        "evidence_quote": QUOTE,
        "close_criterion": "The claim must point to a number or a source",
    } | kw


def check(raw, files=FILES):
    paper, used = di.assemble(files, "main.tex")
    return di.check_issue(raw, "ideas", used, grams([paper]), paper)


def test_assemble_expands_inputs_in_order_and_cuts_the_preamble_and_tail():
    paper, used = di.assemble(FILES, "main.tex")
    assert paper.index("sleep improves memory") < paper.index("Accuracy reached")
    assert not any(x in paper for x in ("documentclass", "amsmath", "hidden text", "TRAILING", "commented line"))
    assert set(used) == {"main.tex", "sections/a.tex", "sections/b.tex"}


def test_assemble_survives_an_input_cycle_and_a_missing_file():
    files = {"main.tex": "\\input{a}\\input{nope}", "a.tex": "A text \\input{main}"}
    paper, used = di.assemble(files, "main.tex")
    assert "A text" in paper and "\\input{nope}" in paper and set(used) == {"main.tex", "a.tex"}


def test_locate_tolerates_whitespace_and_gives_the_line():
    place = di.locate(FILES, "sleep  improves\nmemory in adults")
    assert (place.file, place.line) == ("sections/a.tex", 2)


@pytest.mark.parametrize(
    "quote", ["a commented line nobody reads", "short one", "x" * 401, "sleep cures every disease known"]
)
def test_locate_refuses_comments_short_long_and_made_up_quotes(quote):
    assert di.locate(FILES, quote) is None


def test_a_good_issue_is_kept_and_located():
    got, why = check(issue())
    assert why is None and got.place.file == "sections/a.tex" and got.raised_by == ("ideas",)


@pytest.mark.parametrize(
    "raw, why",
    [
        ("text", "invalid"),
        (issue(severity="huge"), "invalid"),
        (issue(close_criterion=""), "criterion"),
        (issue(close_criterion="   "), "criterion"),
        ({k: v for k, v in issue().items() if k != "close_criterion"}, "criterion"),
        (issue(evidence_quote="sleep cures every disease known"), "quote"),
        (issue(summary='Rewrite it as "Sleep helps memory a lot."'), "wording"),
        (issue(close_criterion="You could say that sleep helps recall"), "wording"),
        (issue(summary="Then show that sleep improves memory in adults too"), "wording"),  # a 7-word run of the paper
        (issue(evidence_quote="\\usepackage{amsmath}"), "quote"),  # in the preamble: in a file, not in the paper
        (issue(summary="word " * 41), "wording"),
        (issue(section='Rewrite it as "Sleep helps memory a lot."'), "wording"),
        (issue(section="Then show that sleep improves memory in adults too"), "wording"),
    ],
)
def test_a_bad_issue_is_dropped_with_its_reason(raw, why):
    got, reason = check(raw)
    assert got is None and reason == why


AB = {"a": "", "b": ""}


def mk(severity, file, start, end, lens):
    place = di.Place(file, 1, start, end)
    return di.Issue(severity, "s", "sum", "quote", "crit", (lens,), place)


def test_merge_joins_overlaps_keeps_the_higher_severity_and_unions_lenses():
    out = di.merge(
        [mk("minor", "a", 0, 50, "ideas"), mk("major", "a", 40, 90, "evidence"), mk("nit", "a", 200, 250, "practice")],
        AB,
    )
    assert [(i.severity, i.raised_by) for i in out] == [("major", ("evidence", "ideas")), ("nit", ("practice",))]


def test_unseen_drops_issues_over_an_earlier_span_in_the_same_file_only():
    seen = [di.Place("a", 1, 0, 50)]
    out = di.unseen([mk("major", "a", 10, 20, "x"), mk("major", "b", 10, 20, "x"), mk("major", "a", 60, 70, "x")], seen)
    assert [(i.place.file, i.place.start) for i in out] == [("b", 10), ("a", 60)]


def test_document_order_is_the_input_order_not_alphabetical():
    files = {"z.tex": "", "a.tex": ""}  # z went into the paper first
    out = di.merge([mk("major", "a.tex", 0, 9, "ideas"), mk("major", "z.tex", 0, 9, "ideas")], files)
    assert [i.place.file for i in out] == ["z.tex", "a.tex"]


def test_merge_keeps_the_same_span_in_two_files_apart_and_sorts_by_severity():
    out = di.merge(
        [mk("nit", "a", 0, 9, "ideas"), mk("blocker", "b", 0, 9, "ideas"), mk("major", "a", 50, 60, "ideas")], AB
    )
    assert [i.severity for i in out] == ["blocker", "major", "nit"]


def section(n, size):  # exactly `size` characters, ending on a line break so the next heading starts a line
    head = f"\\section{{S{n}}}\n"
    return head + "x" * (size - len(head) - 1) + "\n"


def test_a_short_paper_is_one_part_and_unchanged():
    paper = "\\section{A}\nA short paper.\n\n\\section{B}\nStill short.\n"
    assert di.split_parts(paper) == [paper]


def test_sections_pack_greedily_and_cut_before_each_heading():
    s1, s2, s3 = section(1, 20_000), section(2, 20_000), section(3, 20_000)
    parts = di.split_parts(s1 + s2 + s3)
    assert parts == [s1 + s2, s3]  # 40,000 fits exactly, so sections 1 and 2 share a part


def test_a_section_over_the_limit_is_cut_at_blank_lines():
    big = "\\section{Big}\n" + "\n\n".join(f"p{i:04d} " + "w" * 44 for i in range(1000))
    parts = di.split_parts(big)
    assert len(big) > di.MAX_PAPER_CHARS and len(parts) >= 2
    assert all(len(p) <= di.MAX_PAPER_CHARS for p in parts)
    assert all(p.endswith("\n\n") for p in parts[:-1])  # every cut falls on a blank line
    assert "".join(parts) == big


def test_a_paragraph_with_no_breaks_is_cut_at_the_limit():
    paper = "\\section{X}\n" + "y" * 90_000
    parts = di.split_parts(paper)
    assert [len(p) for p in parts] == [di.MAX_PAPER_CHARS, di.MAX_PAPER_CHARS, len(paper) - 2 * di.MAX_PAPER_CHARS]


def test_text_before_the_first_heading_is_its_own_block():
    preamble = "Front matter.\n" * 1_000  # 14,000 characters, ending on a line break; it fits with section 1 only
    paper = preamble + section(1, 20_000) + section(2, 20_000)
    assert di.split_parts(paper) == [preamble + section(1, 20_000), section(2, 20_000)]


@pytest.mark.parametrize(
    "paper",
    [
        "",
        "tiny",
        section(1, 45_000),
        section(1, 45_000) + "\n\n\\chapter*{Two}\n" + section(2, 30_000),
        "lead " * 9_000 + "\n\\section{Mid}\n" + "text \\section{inline is not a heading}\n" * 2_000,
        "\\section{Gap}\n" + "\n \n".join("z" * 1_000 for _ in range(60)),
    ],
)
def test_joining_the_parts_gives_back_the_paper(paper):
    parts = di.split_parts(paper)
    assert "".join(parts) == paper
    assert all(len(p) <= di.MAX_PAPER_CHARS for p in parts)


def test_the_total_cap_is_four_parts_worth():
    assert di.MAX_TOTAL_CHARS == 160_000
