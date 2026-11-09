from types import MappingProxyType

from app.core.manuscript_checks.base import CheckContext, ManuscriptInfo
from app.core.manuscript_checks.citations import CHECKS

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
