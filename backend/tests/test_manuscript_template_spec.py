import pytest
from pydantic import ValidationError

from app.core import manuscript_template_spec as spec
from app.core import manuscript_templates as mt

GOOD = {
    "name": "t", "label": "T", "order": 9, "official": False, "provenance": "p", "page_limit": 6,
    "references_count": True, "abstract_words": [10, 20], "citation_style": "numeric",
    "sections": [{"id": "intro", "title": "Intro", "words": [1, 5]}],
}


def test_every_shipped_folder_lints_clean():
    for name in mt.TEMPLATES:
        assert spec.lint(mt.DIR / name) == [], name


def test_templates_dict_is_unchanged_and_ordered():
    assert list(mt.TEMPLATES.items()) == [
        ("article", "Plain article"), ("ieee", "IEEE conference"), ("acm", "ACM (sigconf)"),
        ("lncs", "Springer LNCS"), ("elsevier", "Elsevier"),
    ]


def test_shipped_values():
    got = {n: (s.page_limit, s.references_count, s.official) for n, s in mt.specs().items()}
    assert got == {
        "article": (None, False, False), "ieee": (6, True, True), "acm": (9, False, True),
        "lncs": (12, True, True), "elsevier": (None, False, True),
    }
    for s in mt.specs().values():
        assert [x.id for x in s.sections] == [
            "introduction", "related-work", "method", "results", "discussion", "conclusion"]


def test_get_is_none_for_custom_unknown_and_none():
    assert mt.get("ieee").label == "IEEE conference"
    assert mt.get("custom") is None and mt.get("nope") is None and mt.get(None) is None


def test_files_unchanged():
    files = mt.files("ieee")
    assert "main.tex" in files and not any(p.endswith(".json") for p in files)


@pytest.mark.parametrize("change", [
    {"extra_key": 1},
    {"abstract_words": [30, 20]},
    {"page_limit": 0},
    {"citation_style": "harvard"},
    {"sections": [{"id": "a", "title": "A", "words": [1, 2]}, {"id": "a", "title": "B", "words": [1, 2]}]},
    {"sections": [{"id": "Bad Id", "title": "A", "words": [1, 2]}]},
    {"sections": [{"id": "a", "title": "A", "words": [5, 2]}]},
    {"sections": []},
])
def test_bad_spec_is_rejected(change):
    with pytest.raises(ValidationError):
        spec.TemplateSpec(**{**GOOD, **change})


def test_lint_reports_problems(tmp_path):
    (tmp_path / "sections").mkdir()
    (tmp_path / "main.tex").write_text("\\input{sections/other}\n")
    (tmp_path / "sections/intro.tex").write_text("\\section{Wrong}\n")
    (tmp_path / "sections/stray.tex").write_text("\\section{Stray}\n")
    import json
    (tmp_path / "template.json").write_text(json.dumps({**GOOD, "name": "elsewhere"}))
    problems = "\n".join(spec.lint(tmp_path))
    assert "name" in problems and "elsewhere" in problems
    assert "sections/intro.tex does not start with \\section{Intro}" in problems
    assert "stray.tex" in problems
    assert "\\input{sections/intro}" in problems


def test_lint_missing_json(tmp_path):
    assert spec.lint(tmp_path) == ["template.json is missing"]
