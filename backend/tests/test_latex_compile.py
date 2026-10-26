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


def test_friendly_needs_download():
    assert lc.friendly_message(_fix("offline-cold.stderr.txt")) == "needs_download"


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


@tectonic
@needs_bin
async def test_relative_traversal_is_recorded(real, tmp_path):
    (tmp_path / "main.tex").write_text(ARTICLE % "\\input{../../../../../../../../etc/hosts}")
    res = await lc.compile_dir(tmp_path, "main.tex")
    print("TRAVERSAL ok=%s friendly=%s errors=%s\n%s" % (res.ok, res.friendly, res.errors, res.log))
