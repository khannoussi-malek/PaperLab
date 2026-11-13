from types import MappingProxyType

from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo
from app.core.manuscript_checks import citations
from app.core.manuscript_checks.citations import CHECKS, suggest

INFO = ManuscriptInfo("m", "main.tex", "never", None, None, None)
CHECK = CHECKS[0]


def run(files, known=()):
    return CHECK.run(CheckContext(MappingProxyType(files), frozenset(known), INFO))


def test_name_and_cost():
    assert (CHECK.name, CHECK.cost) == ("citations.missing_keys", "cheap")


def test_known_key_is_silent():
    assert run({"main.tex": "See \\cite{a}."}, known={"a"}) == []


def test_unknown_key_gives_file_line_message_and_hint():
    [x] = run({"main.tex": "Hi.\nSee \\cite{nowhere}.\n"})
    assert (x.check, x.severity, x.file, x.line) == ("citations.missing_keys", "error", "main.tex", 2)
    assert x.message == "Cited key nowhere matches no paper in your library or your .bib files, so LaTeX prints [?]."
    assert x.fix_hint == "Add the paper to the workspace, pin it, or add the entry to a .bib file; or fix the key."


def test_only_tex_files_are_scanned_and_files_come_in_path_order():
    files = {"refs.bib": "\\cite{inbib}", "sections/b.tex": "\\cite{k2}", "main.tex": "\\cite{k1}"}
    assert [(x.file, x.message.split()[2]) for x in run(files)] == [("main.tex", "k1"), ("sections/b.tex", "k2")]


def test_a_near_miss_key_suggests_the_known_one():
    [x] = run({"main.tex": "See \\cite{formal2021splade}."}, known={"formal2021spladea", "formal2021spladeb"})
    assert x.fix_hint == (
        "Did you mean formal2021spladea or formal2021spladeb? "
        "Add the paper to the workspace, pin it, or add the entry to a .bib file; or fix the key."
    )


def test_a_key_that_differs_only_by_case_is_suggested():
    [x] = run({"main.tex": "\\cite{Smith2020}"}, known={"smith2020"})
    assert x.fix_hint.startswith("Did you mean smith2020? Add the paper")


def test_an_unrelated_key_gets_no_suggestion():
    [x] = run({"main.tex": "\\cite{vaswani2017attention}"}, known={"devlin2019bert", "brown2020gpt3"})
    assert x.fix_hint == ("Add the paper to the workspace, pin it, or add the entry to a .bib file; or fix the key.")


def test_suggest_orders_case_then_suffix_then_close_and_caps_at_three():
    known = ["formal2021spladea", "formal2021spladeb", "formal2021splad", "FORMAL2021SPLADE", "other"]
    # case match, then the a/b suffixes; the close spelling is cut at three
    assert suggest("formal2021splade", known) == ["FORMAL2021SPLADE", "formal2021spladea", "formal2021spladeb"]
    assert suggest("formal2021splade", ["formal2021spladea"]) == ["formal2021spladea"]
    assert suggest("zzz", ["formal2021splade"]) == []


def test_suggest_stays_quick_with_a_large_library():
    known = [f"author{i}{2000 + i % 25}topic" for i in range(200)]
    assert suggest("vaswani2017attention", known) == []


def test_a_key_cited_many_times_is_matched_once(monkeypatch):
    calls = []
    real = citations.suggest
    monkeypatch.setattr(citations, "suggest", lambda key, known: calls.append(key) or real(key, known))
    tex = "\\cite{gone2020}. " * 40 + "\\cite{alsogone}"
    found = run({"main.tex": tex}, known={"gone2020a"})
    assert len(found) == 41 and sorted(calls) == ["alsogone", "gone2020"]
