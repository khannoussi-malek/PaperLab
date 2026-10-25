"""Section roles (M16 spec §3.2): assign_roles is pure, so every rule is tested on heading lists alone."""

import json
from pathlib import Path

import pytest

from app.core.sections import ROLES, assign_roles

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "section_roles.json").read_text())


def roles_of(titles, overrides=None) -> list[tuple[str, str]]:
    return [tuple(result) for result in assign_roles(titles, overrides or {})]


@pytest.mark.parametrize("paper", sorted(GOLDEN))
def test_each_golden_heading_list_gets_exactly_its_roles_and_sources(paper):
    rows = GOLDEN[paper]

    found = assign_roles([title for title, _, _ in rows], {})

    assert [(title, *result) for (title, _, _), result in zip(rows, found)] == [tuple(row) for row in rows]


def test_the_ten_roles_of_the_spec():
    assert ROLES == (
        "abstract",
        "intro",
        "related",
        "method",
        "results",
        "discussion",
        "limitations",
        "conclusion",
        "back",
        "other",
    )


def test_no_headings_give_no_roles():
    assert assign_roles([], {}) == []


def test_text_before_the_first_heading_is_other():
    assert roles_of([None, "1 Introduction"]) == [("other", "none"), ("intro", "keyword")]


def test_a_bare_capital_letter_is_text_not_a_number():
    # "A Background" is unnumbered, so it is nobody's parent and "A.1 Setup" is placed by position (7c).
    assert roles_of(["1 Introduction", "A Background", "A.1 Setup", "4 Results"]) == [
        ("intro", "keyword"),
        ("related", "keyword"),
        ("method", "position"),
        ("results", "keyword"),
    ]


def test_a_number_with_a_trailing_dot_still_names_its_parent():
    assert roles_of(["1 Introduction", "2. Methods", "2.1. Setup Details", "3 Results"]) == [
        ("intro", "keyword"),
        ("method", "keyword"),
        ("method", "inherited"),
        ("results", "keyword"),
    ]


def test_a_fix_beats_a_keyword():
    assert roles_of(["1 Introduction", "2 Method", "3 Results"], {"2 Method": "conclusion"}) == [
        ("intro", "keyword"),
        ("conclusion", "user"),
        ("results", "keyword"),
    ]


def test_subsections_follow_a_fixed_parent():
    titles = ["1 Introduction", "3 BERT", "3.1 Pre-training BERT", "3.2 Fine-tuning", "4 Results"]

    assert roles_of(titles, {"3 BERT": "results"}) == [
        ("intro", "keyword"),
        ("results", "user"),
        ("results", "inherited"),
        ("results", "inherited"),
        ("results", "keyword"),
    ]


def test_back_matter_keywords_need_no_references_heading():
    titles = ["1 Introduction", "Acknowledgements", "7 Data Availability", "Supplementary Material", "2 Method"]

    assert roles_of(titles) == [
        ("intro", "keyword"),
        ("back", "keyword"),
        ("back", "keyword"),
        ("back", "keyword"),
        ("method", "keyword"),
    ]


def test_everything_after_references_is_back():
    titles = ["1 Introduction", "References", "Attention Visualizations", "A.1 Proof of Lemma 1", "B Results Tables"]

    assert roles_of(titles) == [("intro", "keyword")] + [("back", "keyword")] * 4


@pytest.mark.parametrize(
    ("title", "role"),
    [
        ("5 Discussion and Future Work", "conclusion"),  # conclusion comes before discussion in the table
        ("2 Background and Related Work", "related"),
        ("6 Results and Discussion", "discussion"),
        ("3 METHODS", "method"),  # plurals match
        ("6 LIMITATIONS", "limitations"),
        ("4.2 RQ2: Outcomes", "results"),
        ("Motivation", "intro"),
        ("8 Threats to Validity", "limitations"),
        ("4 Experimental Setup", "method"),
    ],
)
def test_the_first_keyword_in_table_order_wins(title, role):
    assert roles_of([title]) == [(role, "keyword")]


def test_limitations_inside_a_discussion_keep_their_own_role():
    assert roles_of(["5 Discussion", "5.3 Implications", "5.4 Limitations"]) == [
        ("discussion", "keyword"),
        ("discussion", "inherited"),
        ("limitations", "keyword"),
    ]


def test_a_subsection_takes_its_parents_role_over_its_own_keyword():
    # "4.4 Summary of Context Factors" is results, not conclusion (spec rule 5); "Future Work" would be conclusion.
    assert roles_of(["4 RQ2. Smells", "4.4 Summary of Context Factors", "4.5 Future Work"]) == [
        ("results", "keyword"),
        ("results", "inherited"),
        ("results", "inherited"),
    ]


def test_a_subsections_own_back_match_is_kept():
    assert roles_of(["3 Method", "3.9 Acknowledgements"]) == [("method", "keyword"), ("back", "keyword")]


def test_unresolved_sections_before_the_abstract_are_front_matter():
    # "CCS CONCEPTS" comes after the abstract, so it is placed by position, and 7f leaves it other.
    assert roles_of(["Jane Doe", "jane@example.org", "Abstract", "CCS CONCEPTS", "1 Introduction"]) == [
        ("other", "none"),
        ("other", "none"),
        ("abstract", "keyword"),
        ("other", "none"),
        ("intro", "keyword"),
    ]


@pytest.mark.parametrize(
    ("titles", "expected"),
    [
        (  # 7a: between two results sections
            ["4 RESULTS", "4.1 Accuracy", "Table 1: Reflections", "4.5 Creative Process"],
            [("results", "keyword"), ("results", "inherited"), ("results", "position"), ("results", "inherited")],
        ),
        (  # 7b
            ["1 Introduction", "2.2 Reasons to Expect Homogenization", "3 Methods"],
            [("intro", "keyword"), ("related", "position"), ("method", "keyword")],
        ),
        (  # 7c
            ["2 Related Work", "3 BERT", "4 Experiments"],
            [("related", "keyword"), ("method", "position"), ("results", "keyword")],
        ),
        (  # 7d
            ["5 Training", "6.1 Machine Translation", "7 Conclusion"],
            [("method", "keyword"), ("results", "position"), ("conclusion", "keyword")],
        ),
        (  # 7d, with nothing after
            ["3 Method", "4 Numbers"],
            [("method", "keyword"), ("results", "position")],
        ),
        (  # 7e
            ["4 Results", "6 Related Work", "7.1 Context Matters", "8 Threats to Validity"],
            [("results", "keyword"), ("related", "keyword"), ("discussion", "position"), ("limitations", "keyword")],
        ),
        (  # 7f
            ["Mockups?", "(1) Context improves specificity:"],
            [("other", "none"), ("other", "none")],
        ),
    ],
)
def test_the_position_rules(titles, expected):
    assert roles_of(titles) == expected
