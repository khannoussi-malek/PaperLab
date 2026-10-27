import asyncio
import os
import stat
from pathlib import Path

import pytest

from app.config import settings
from app.core import latex_compile as lc

pytestmark = pytest.mark.anyio
FIX = Path(__file__).parent / "fixtures" / "tectonic"
REAL = bool(os.environ.get("TECTONIC_BIN"))
tectonic = pytest.mark.tectonic
needs_bin = pytest.mark.skipif(not REAL, reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)")


def _fix(name: str) -> str:
    return (FIX / name).read_text()


def _script(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_parse_errors_undefined_control_sequence():
    errs = lc.parse_errors(_fix("undef.stderr.txt"))
    assert errs == [{"file": "main.tex", "line": 7, "message": "Undefined control sequence", "kind": "error"}]


def test_parse_errors_missing_brace():
    errs = lc.parse_errors(_fix("brace.stderr.txt"))
    assert errs == [
        {"file": None, "line": None, "message": "File ended while scanning use of \\@xdblarg", "kind": "error"}
    ]


def test_undefined_citation_is_a_warning_with_its_line():
    log = _fix("undefcite.main.log")
    assert lc.parse_errors(log, "main.tex") == [
        {"file": "main.tex", "line": 5, "message": "Citation `nobody' on page 1 undefined", "kind": "warning"}
    ]


def test_friendly_biber():
    assert lc.friendly_message(_fix("biblatex.stderr.txt")) == "biber_unsupported"


MISSING = "error: main.tex:2: ! LaTeX Error: File `fontawesome5.sty' not found.\n"


def test_a_missing_package_is_named():
    res = lc.finish(1, MISSING, "", None)
    assert res.friendly == "package_missing"
    assert {"file": "main.tex", "line": None, "message": "fontawesome5", "kind": "package_missing"} in res.errors


def test_a_missing_class_is_a_missing_package_too():
    assert lc.friendly_message("error: main.tex:1: ! LaTeX Error: File `revtex4-2.cls' not found.") == "package_missing"


def test_a_missing_tex_input_is_not_a_package():
    assert lc.friendly_message("error: main.tex:3: ! LaTeX Error: File `chapter1.tex' not found.") is None


@pytest.mark.parametrize("written", ["/tectonic-cache/natbib.sty", "../escape.txt", "sub/../../x.txt"])
def test_a_write_outside_the_project_voids_the_pdf(written):
    res = lc.finish(0, f"note: Writing `{written}` (2 B)\nnote: Writing `main.pdf` (2 KiB)\n", "", b"%PDF")
    assert (res.ok, res.pdf, res.friendly) == (False, None, "outside_file")


def test_writes_inside_the_project_are_fine():
    res = lc.finish(0, "note: Writing `main.pdf` (2 KiB)\nnote: Writing `sub/notes.txt` (2 B)\n", "", b"%PDF")
    assert (res.ok, res.friendly) == (True, None)


def test_log_is_truncated_to_200kb_and_drops_fontconfig():
    res = lc.finish(1, "Fontconfig error: x\n" + "a" * (300 * 1024), "", None)
    assert len(res.log) == lc.MAX_LOG
    assert "Fontconfig" not in res.log


def test_log_appends_main_log():
    res = lc.finish(1, "stderr line", "main log line", None)
    assert res.log == "stderr line\nmain log line"


def test_absolute_read_wins_over_other_friendly_codes():
    stderr = "note: Running external tool biber\nwarning: accessing absolute path `/etc/hosts`; x\n"
    res = lc.finish(0, stderr, "", b"%PDF")
    assert (res.ok, res.pdf, res.friendly) == (False, None, "outside_file")


def test_absolute_read_discards_the_pdf_even_at_rc0():
    res = lc.finish(0, _fix("absread.stderr.txt"), "", b"%PDF")
    assert (res.ok, res.pdf, res.friendly) == (False, None, "outside_file")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _gone(pid: int) -> bool:
    for _ in range(20):
        if not _alive(pid):
            return True
        await asyncio.sleep(0.1)
    return False


SPAWNER = "sleep 30 & echo $! > child.pid\necho $$ > parent.pid\nwait\n"


async def test_timeout_kills_the_whole_group_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", _script(tmp_path / "slow", SPAWNER))
    res = await lc.compile_dir(tmp_path, "main.tex", timeout=1)
    assert (res.ok, res.pdf, res.friendly) == (False, None, "compile_timeout")
    assert await _gone(int((tmp_path / "child.pid").read_text()))


async def test_cancel_kills_the_group_and_propagates(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", _script(tmp_path / "slow", SPAWNER))
    task = asyncio.create_task(lc.compile_dir(tmp_path, "main.tex"))
    for _ in range(50):
        if (tmp_path / "child.pid").exists() and (tmp_path / "parent.pid").exists():
            break
        await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await _gone(int((tmp_path / "parent.pid").read_text()))
    assert await _gone(int((tmp_path / "child.pid").read_text()))


@pytest.mark.parametrize("bad", ["-x.tex", "/etc/hosts", "../a.tex", "a/../b.tex", "a\\b.tex", ""])
async def test_main_file_must_be_a_plain_relative_path(tmp_path, bad):
    with pytest.raises(ValueError):
        await lc.compile_dir(tmp_path, bad)


async def test_tectonic_gets_a_minimal_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLAB_SECRET_SENTINEL", "leak")
    cache = tmp_path / "cache"
    monkeypatch.setattr(settings, "tectonic_cache_dir", cache)
    monkeypatch.setattr(settings, "tectonic_bin", _script(tmp_path / "fake", "env > env.dump\n"))
    work = tmp_path / "work"
    work.mkdir()
    await lc.compile_dir(work, "main.tex")
    got = dict(ln.split("=", 1) for ln in (work / "env.dump").read_text().splitlines() if "=" in ln)
    got.pop("PWD", None)  # the shell adds these itself
    got.pop("SHLVL", None)
    got.pop("_", None)
    assert set(got) == {"PATH", "HOME", "LANG", "TECTONIC_CACHE_DIR"}
    assert got["HOME"] == str(work) and got["TECTONIC_CACHE_DIR"] == str(cache)


async def test_user_is_passed_only_when_configured(tmp_path, monkeypatch):
    seen = []

    class Done:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_spawn(argv, **kw):
        seen.append(kw)
        return Done()

    monkeypatch.setattr(lc, "_spawn", fake_spawn)
    monkeypatch.setattr(lc, "_chown_tree", lambda root, uid, gid: seen.append(("chown", uid, gid)))
    await lc.compile_dir(tmp_path, "main.tex")
    assert not {"user", "group", "extra_groups"} & set(seen[0]) and len(seen) == 1
    monkeypatch.setattr(settings, "tectonic_user", "tex")
    monkeypatch.setattr(lc, "_ids", lambda user: (1001, 1002))
    await lc.compile_dir(tmp_path, "main.tex")
    assert seen[1] == ("chown", 1001, 1002)
    assert (seen[2]["user"], seen[2]["group"], seen[2]["extra_groups"]) == (1001, 1002, [])


@pytest.fixture
def real(monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))


ARTICLE = "\\documentclass{article}\n\\begin{document}\n%s\n\\end{document}\n"


@tectonic
@needs_bin
async def test_compiles_a_minimal_article(real, tmp_path):
    (tmp_path / "main.tex").write_text(ARTICLE % "Hello PaperLab")
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert res.ok and res.pdf.startswith(b"%PDF") and res.errors == []
    assert res.synctex is not None and res.synctex[:2] == b"\x1f\x8b"


@tectonic
@needs_bin
async def test_an_error_gives_file_and_line(real, tmp_path):
    (tmp_path / "main.tex").write_text(ARTICLE % "ok\n\\foo")
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert not res.ok and res.pdf is None
    assert {"file": "main.tex", "line": 4, "message": "Undefined control sequence", "kind": "error"} in res.errors


@tectonic
@needs_bin
async def test_untrusted_cannot_read_outside_the_project(real, tmp_path):
    # Task 1 recorded absolute_read: allowed, so the guard is layer 2: the warning voids the PDF.
    (tmp_path / "main.tex").write_text(ARTICLE % "\\input{/etc/hosts}")
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert (res.ok, res.pdf, res.friendly) == (False, None, "outside_file")


OPENOUT = "\\newwrite\\w\\immediate\\openout\\w=%s\\immediate\\write\\w{x}\\immediate\\closeout\\w\nhi"


@tectonic
@needs_bin
async def test_an_absolute_openout_fails_the_compile(real, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "main.tex").write_text(ARTICLE % (OPENOUT % (tmp_path / "abs-out.txt")))
    res = await lc.compile_dir(work, "main.tex")
    assert (res.ok, res.pdf, res.friendly) == (False, None, "outside_file")


@tectonic
@needs_bin
async def test_a_parent_openout_fails_the_compile(real, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "main.tex").write_text(ARTICLE % (OPENOUT % "../rel-out.txt"))
    res = await lc.compile_dir(work, "main.tex")
    assert (res.ok, res.pdf, res.friendly) == (False, None, "outside_file")


@tectonic
@needs_bin
async def test_a_missing_package_fails_with_its_name(real, tmp_path):
    tex = ARTICLE.replace("\\begin{document}", "\\usepackage{paperlabnosuchpkg}\n\\begin{document}")
    (tmp_path / "main.tex").write_text(tex % "x")
    res = await lc.compile_dir(tmp_path, "main.tex")
    assert (res.ok, res.friendly) == (False, "package_missing")
    assert [e["message"] for e in res.errors if e["kind"] == "package_missing"] == ["paperlabnosuchpkg"]


@tectonic
@needs_bin
async def test_a_nested_main_file_yields_its_pdf_and_log(real, tmp_path):
    (tmp_path / "paper" / "sections").mkdir(parents=True)
    (tmp_path / "paper" / "main.tex").write_text(ARTICLE % "\\input{sections/intro}")
    (tmp_path / "paper" / "sections" / "intro.tex").write_text("Hello nested.")
    res = await lc.compile_dir(tmp_path, "paper/main.tex")
    assert res.ok and res.pdf.startswith(b"%PDF")
    assert "(sections/intro)" in res.log  # from paper/main.log, not a main.log at the root


async def test_a_huge_main_log_is_read_in_bounded_memory(tmp_path, monkeypatch):
    import tracemalloc

    (tmp_path / "tail.txt").write_text("\nLaTeX Warning: Citation `late' on page 9 undefined on input line 77.\n")
    body = "head -c 30000000 /dev/zero | tr '\\0' a > main.log && cat tail.txt >> main.log\n"
    monkeypatch.setattr(settings, "tectonic_bin", _script(tmp_path / "fake", body))
    tracemalloc.start()
    try:
        res = await lc.compile_dir(tmp_path, "main.tex")
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 5 * 1024**2, peak
    assert len(res.log) <= lc.MAX_LOG
    late = {"file": "main.tex", "line": 77, "message": "Citation `late' on page 9 undefined", "kind": "warning"}
    assert late in res.errors


@tectonic
@needs_bin
async def test_relative_traversal_is_recorded(real, tmp_path):
    (tmp_path / "main.tex").write_text(ARTICLE % "\\input{../../../../../../../../etc/hosts}")
    res = await lc.compile_dir(tmp_path, "main.tex")
    print("TRAVERSAL ok=%s friendly=%s errors=%s\n%s" % (res.ok, res.friendly, res.errors, res.log))


def test_parse_errors_adds_tex_to_an_input_file_named_without_it():
    errs = lc.parse_errors("error: sections/x:2: Undefined control sequence")
    assert [(e["file"], e["line"]) for e in errs] == [("sections/x.tex", 2)]
