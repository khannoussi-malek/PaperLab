import json
from types import MappingProxyType

from app.core.manuscript_checks import blueprint
from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo


def run(name, files, template="custom"):
    info = ManuscriptInfo("m", "main.tex", "never", None, None, None, template=template)
    check = next(c for c in blueprint.CHECKS if c.name == name)
    return check.run(CheckContext(MappingProxyType(files), frozenset(), info))


def plan(**kw):
    return json.dumps(kw)


def words(n):
    return " ".join(["word"] * n)


def test_silent_without_a_blueprint():
    assert run("blueprint.words", {"main.tex": "\\section{Method}\nshort\n"}) == []


def test_invalid_file_is_one_warning():
    f = run("blueprint.words", {"blueprint.json": '{"colour": 1}', "main.tex": "\\section{A}\n"})
    assert [(x.severity, x.file, x.line) for x in f] == [("warning", "blueprint.json", 1)]
    assert f[0].message == "blueprint.json is not valid: colour: Extra inputs are not permitted"
    assert f[0].fix_hint == "Fix the file; the blueprint checks are off until it parses."


def test_unparseable_file_names_the_json_problem():
    f = run("blueprint.words", {"blueprint.json": "nope", "main.tex": "\\section{A}\n"})
    assert f[0].message.startswith("blueprint.json is not valid: ") and "json" in f[0].message.lower()


def test_below_and_above_the_target_have_exact_text():
    bands = {"method": [10, 20], "results": [10, 20], "intro": [10, 20]}
    body = (f"\\section{{Method}}\n{words(4)}\n\\section{{Results}}\n{words(25)}\n"
            f"\\section{{Intro}}\n{words(15)}\n")
    files = {"blueprint.json": plan(target_words=bands), "main.tex": body}
    f = run("blueprint.words", files)
    assert [(x.line, x.severity) for x in f] == [(1, "warning"), (3, "warning")]
    assert f[0].message == 'Section "Method" has 4 words; the target is 10 to 20.'
    assert f[0].fix_hint == "Add about 6 more words, or lower the target in blueprint.json."
    assert f[1].message == 'Section "Results" has 25 words; more than the target of 10 to 20.'
    assert f[1].fix_hint == "Cut about 5 words, or raise the target in blueprint.json."


def test_template_band_is_the_default_and_custom_has_none():
    files = {"blueprint.json": "{}", "main.tex": f"\\section{{Conclusion}}\n{words(5)}\n"}
    assert "100 to 300" in run("blueprint.words", files, template="article")[0].message
    assert no_targets(run("blueprint.words", files, template="custom")) == [NO_TARGETS]


def test_a_target_naming_no_section_explains_itself_without_the_no_targets_note():
    files = {"blueprint.json": plan(target_words={"Intro": [1, 9]}), "main.tex": f"\\section{{Conclusion}}\n{words(5)}\n"}
    f = run("blueprint.words", files, template="custom")
    assert no_targets(f) == [] and [x.message for x in f] == ['target_words names "Intro", but no section has that title.']


def test_an_invalid_plan_gives_only_its_own_warning():
    files = {"blueprint.json": "{not json", "main.tex": f"\\section{{Conclusion}}\n{words(5)}\n"}
    f = run("blueprint.words", files, template="custom")
    assert [x.severity for x in f] == ["warning"] and no_targets(f) == []


def test_target_naming_no_section_is_info_and_a_second_file_is_read():
    files = {"blueprint.json": plan(target_words={"ghost": [1, 2], "method": [1, 9]}),
             "main.tex": "\\input{sections/m}\n", "sections/m.tex": f"\\section{{Method}}\n{words(3)}\n"}
    f = run("blueprint.words", files)
    assert [(x.severity, x.file, x.message) for x in f] == [
        ("info", "blueprint.json", 'target_words names "ghost", but no section has that title.')]


def test_a_section_whose_body_is_an_input_is_not_warned_about():
    files = {"blueprint.json": plan(target_words={"method": [100, 200]}),
             "main.tex": "\\section{Method}\n\\input{sections/method-body}\n"}
    assert run("blueprint.words", files) == []


def test_math_cites_and_comments_do_not_inflate_the_count():
    cites = ",".join(f"k{i}" for i in range(30))
    body = "% " + words(50) + "\n$" + "x + " * 40 + "y$ \\cite{" + cites + "}\n" + words(5)
    files = {"blueprint.json": plan(target_words={"a": [1, 10]}), "main.tex": f"\\section{{A}}\n{body}\n"}
    f = run("blueprint.words", files)
    assert f == []


def listed(*symbols):
    return plan(notation=[{"symbol": s, "meaning": "m"} for s in symbols])


def test_notation_silent_without_a_list_or_with_an_invalid_file():
    main = "$\\alpha$ here.\n"
    assert run("blueprint.notation", {"main.tex": main}) == []
    assert run("blueprint.notation", {"blueprint.json": "{}", "main.tex": main}) == []
    assert run("blueprint.notation", {"blueprint.json": '{"x":1}', "main.tex": main}) == []


def test_listed_but_unused_and_used_but_unlisted():
    files = {"blueprint.json": listed("\\alpha", "$\\lambda$"),
             "main.tex": "Let $\\alpha + \\beta$ be given.\n"}
    f = run("blueprint.notation", files)
    beta = "\\beta is used in the manuscript but is not in the blueprint's notation list."
    lam = "\\lambda is listed in the blueprint's notation but never used in the manuscript."
    assert [(x.severity, x.file, x.line, x.message) for x in f] == [
        ("info", "blueprint.json", 1, beta),
        ("info", "blueprint.json", 1, lam)]
    assert f[0].fix_hint == "Add it to notation in blueprint.json."
    assert f[1].fix_hint == "Use it, or remove it from the list."


def test_display_only_symbols_are_left_to_the_latex_check():
    # beta: latex.notation_undefined's
    files = {"blueprint.json": listed("\\alpha"), "main.tex": "\\[ \\alpha + \\beta \\]\n"}
    assert run("blueprint.notation", files) == []


def test_symbol_spellings_and_non_greek_and_function_like():
    files = {"blueprint.json": listed("\\alpha_t", "x_i", "\\sigma"),
             "main.tex": "$\\alpha_t$ and $x_i$ and $\\sigma(x)$.\n"}
    f = run("blueprint.notation", files)
    assert [x.message.split()[0] for x in f] == ["\\sigma"]  # listed, used only as a function: unused


NO_TARGETS = ("info", "blueprint.json", 1, "No section has a word target, so section lengths aren't checked.")


def no_targets(findings):
    return [(x.severity, x.file, x.line, x.message) for x in findings if x.message.startswith("No section has")]


def test_a_custom_plan_with_no_targets_says_lengths_are_not_checked():
    files = {"blueprint.json": "{}", "main.tex": f"\\section{{Method}}\n{words(4)}\n"}
    f = run("blueprint.words", files)
    assert no_targets(f) == [NO_TARGETS]
    assert f[0].fix_hint == 'Add targets to target_words in blueprint.json, for example "Introduction": [600, 900].'


def test_one_target_anywhere_means_no_such_note():
    files = {"blueprint.json": plan(target_words={"method": [1, 9]}),
             "main.tex": f"\\section{{Method}}\n{words(4)}\n\\section{{Intro}}\n{words(4)}\n"}
    assert no_targets(run("blueprint.words", files)) == []


def test_a_template_with_bands_needs_no_note_even_with_empty_targets():
    files = {"blueprint.json": "{}", "main.tex": f"\\section{{Introduction}}\n{words(4)}\n"}
    assert no_targets(run("blueprint.words", files, template="acm")) == []


def test_no_note_when_no_section_is_measurable():
    files = {"blueprint.json": "{}", "main.tex": "\\section{Method}\n\\input{sections/m}\n"}
    assert no_targets(run("blueprint.words", files)) == []
