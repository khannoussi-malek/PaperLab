from types import MappingProxyType

from app.core.manuscript_checks import references
from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo
from app.core.manuscript_checks.bibparse import parse_bib
from app.core.manuscript_paths import RESERVED

INFO = ManuscriptInfo("m", "main.tex", "never", None, None, None)


def run(name, files):
    if isinstance(files, str):
        files = {"main.tex": files}
    check = next(c for c in references.CHECKS if c.name == name)
    return check.run(CheckContext(MappingProxyType(files), frozenset(), INFO))


SAMPLE = '''@article{a2020,
  author = {Smith, Jo and {Big Group}},
  title = "A {Nested} Title",
  year = 2020,
  Journal = {J. Things}
  }

@comment{ignored}
@string{x = "y"}
@book{b1, author={B}, title={T}, publisher={P}, year={1999}}
'''


def test_parse_bib_reads_bare_numbers_quotes_nesting_and_an_indented_close():
    entries = parse_bib(SAMPLE)
    assert [(e.key, e.kind, e.line) for e in entries] == [("a2020", "article", 1), ("b1", "book", 10)]
    a = entries[0].fields
    assert a["year"] == "2020" and a["journal"] == "J. Things"
    assert a["title"] == "A {Nested} Title" and a["author"] == "Smith, Jo and {Big Group}"


def test_duplicate_keys_within_and_across_files_ignoring_case():
    files = {"a.bib": "@article{Smith20, title={T}}\n@article{smith20, title={U}}\n",
             "b.bib": "@misc{SMITH20, title={V}}\n"}
    found = run("references.duplicate_key", files)
    assert [(f.file, f.line, f.severity) for f in found] == [("a.bib", 2, "warning"), ("b.bib", 1, "warning")]
    assert found[0].message == "Key smith20 is defined twice (first at a.bib:1); BibTeX uses the first."
    assert found[0].fix_hint == ("Delete or rename one of the entries. If both are the same paper, keep one key and "
                                 "fix the cites.")


def test_the_generated_bib_is_never_read():
    assert run("references.duplicate_key", {RESERVED: "@misc{a, title={T}}\n@misc{a, title={T}}\n"}) == []
    assert run("references.stub_entry", {RESERVED: "@misc{a, title={T}}\n"}) == []


def test_stub_entry_lists_what_is_missing():
    [f, g] = run("references.stub_entry", {"r.bib": "@misc{k, title={Only a title}}\n"})
    assert (f.file, f.line, f.severity) == ("r.bib", 1, "warning")
    assert f.message == "Entry k is missing: author, year."
    assert f.fix_hint == ("Fill the missing fields, or replace the entry with one added from your library "
                          "(it has full metadata).")
    # never a warning: it must not feed the badge
    assert (g.severity, g.message) == ("info", "Entry k has no DOI or URL.")
    assert g.fix_hint == "Add the DOI or URL so readers (and Check DOIs online) can find it."
    [h] = run("references.stub_entry", {"r.bib": "@article{a, author={A}, year={2020}, journal={J}, doi={10.1/x}}\n"})
    assert h.message == "Entry a is missing: title."


def test_complete_entries_of_every_kind_are_silent():
    bib = ("@book{b, author={A}, title={T}, publisher={P}, year={1999}}\n"
           "@phdthesis{t, author={A}, title={T}, school={S}, year={2001}}\n"
           "@article{u, author={A}, title={T}, journal={J}, year={2020}, url={https://x.org}}\n"
           "@inproceedings{d, editor={E}, title={T}, booktitle={B}, date={2020-01-01}, doi={10.1/y}}\n"
           "@article{n, author={A}, title={T}, journal={J}, year=2016, eprint={1234.5678}}\n"
           "@article{old, author={A}, title={T}, journal={J}, year={1995}}\n"
           "@misc{w, author={A}, title={T}, year={2021}, howpublished={\\url{https://x.org}}}\n"
           "@misc{v, author={A}, title={T}, year={2021}, note={Accessed at http://x.org}}\n")
    assert run("references.stub_entry", {"r.bib": bib}) == []


def test_an_article_without_a_doi_is_only_info():
    [f] = run("references.stub_entry", {"r.bib": "@article{a, author={A}, title={T}, journal={J}, year={2012}}\n"})
    assert f.severity == "info"


def test_unused_entries_are_info_and_comments_do_not_count():
    files = {"r.bib": "@misc{a, title={A}}\n@misc{b, title={B}}\n@misc{c, title={C}}\n",
             "main.tex": "See \\citep{a, C}.\n% \\cite{b}\n"}
    [f] = run("references.unused_entry", files)
    assert (f.file, f.line, f.severity, f.message) == ("r.bib", 2, "info", "Entry b is never cited.")
    assert f.fix_hint == "Delete it, or cite it if it belongs in the paper."


def test_nocite_star_silences_and_nocite_key_counts():
    bib = "@misc{a, title={A}}\n@misc{b, title={B}}\n"
    assert run("references.unused_entry", {"r.bib": bib, "main.tex": "\\nocite{*}\n"}) == []
    assert [f.message for f in run("references.unused_entry", {"r.bib": bib, "main.tex": "\\nocite{a}\n"})] == [
        "Entry b is never cited."]


WORDS = " ".join(["word"] * 45)


def test_a_body_section_with_no_cites_is_flagged_at_its_heading():
    text = f"\\section{{Introduction}}\n{WORDS}.\n"
    [f] = run("references.zero_cite_section", text)
    assert (f.file, f.line, f.severity) == ("main.tex", 1, "warning")
    assert f.message == 'Section "Introduction" cites nothing.'
    assert f.fix_hint == ("Related work and introductions normally cite the work they build on; add citations or "
                          "confirm this is intended.")


def test_starred_headings_and_per_section_counting():
    text = f"\\section*{{Related Work}}\n{WORDS}.\n\\section{{Conclusion}}\nSee \\cite{{a}}.\n"
    [f] = run("references.zero_cite_section", text)
    assert f.message == 'Section "Related Work" cites nothing.'  # the cite in the next section does not count


def test_cited_short_input_and_own_method_sections_are_silent():
    assert run("references.zero_cite_section", f"\\section{{Introduction}}\n{WORDS} \\citep{{a}}.\n") == []
    assert run("references.zero_cite_section", "\\section{Introduction}\nTo write.\n") == []
    assert run("references.zero_cite_section", f"\\section{{Background}}\n{WORDS}\n\\input{{sections/bg}}\n") == []
    assert run("references.zero_cite_section", f"\\section{{Method}}\n{WORDS}.\n") == []
    assert run("references.zero_cite_section", f"\\section{{Introduction}}\n{WORDS}\n% \\cite{{a}}\n") != []
