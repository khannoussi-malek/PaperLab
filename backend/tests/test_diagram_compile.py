import os
from pathlib import Path

import pytest

from app.config import settings
from app.core import diagram_compile as dc
from app.core import diagram_tikz as dt
from app.core import latex_compile as lc

pytestmark = pytest.mark.anyio
REAL = bool(os.environ.get("TECTONIC_BIN"))
needs_bin = pytest.mark.skipif(not REAL, reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)")
PIC = "\\begin{tikzpicture}\n\\node {A};\n\\end{tikzpicture}"


@pytest.fixture
def real(monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))


async def test_a_picture_the_guard_rejects_is_never_compiled(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("compiled")

    monkeypatch.setattr(lc, "compile_dir", boom)
    res = await dc.preview([], PIC.replace("{A}", "{\\input{x}}"))
    assert not res.ok and res.friendly == "diagram_invalid" and res.pdf is None


async def test_a_huge_pdf_is_refused(monkeypatch):
    async def fake(workdir, main, *, timeout):
        return lc.CompileResult(True, b"%PDF" + b"x" * dc.MAX_PDF, "", [], None)

    monkeypatch.setattr(lc, "compile_dir", fake)
    res = await dc.preview([], PIC)
    assert not res.ok and res.pdf is None and res.friendly == "diagram_too_large"


async def test_error_lines_point_into_the_picture(monkeypatch):
    async def fake(workdir, main, *, timeout):
        errs = [{"file": "main.tex", "line": 9, "message": "Undefined control sequence", "kind": "error"}]
        return lc.CompileResult(False, None, "", errs, None)

    monkeypatch.setattr(lc, "compile_dir", fake)
    res = await dc.preview(["fit"], PIC)
    assert res.errors == [
        {"line": 2, "message": "Undefined control sequence"}
    ]  # the wrapper has 7 lines before the picture


@needs_bin
async def test_a_valid_picture_compiles(real):
    res = await dc.preview(["fit"], PIC)
    assert res.ok and res.pdf.startswith(b"%PDF") and res.errors == []


@needs_bin
async def test_an_undefined_control_sequence_fails_with_its_line(real):
    res = await dc.preview([], "\\begin{tikzpicture}\n\\node {A};\n\\foo\n\\end{tikzpicture}")
    assert not res.ok and res.pdf is None
    assert {"line": 3, "message": "Undefined control sequence"} in res.errors


@needs_bin
@pytest.mark.parametrize("library", dt.ALLOWED_LIBRARIES)
async def test_every_allowlisted_library_compiles_from_the_cache(real, library):
    res = await dc.preview([library], PIC)
    assert res.ok, (library, res.errors, res.friendly)


@needs_bin
async def test_a_library_outside_the_allowlist_does_not_compile(real, tmp_path):
    (tmp_path / "main.tex").write_text(dt.standalone_document(["external"], PIC))
    res = await lc.compile_dir(tmp_path, "main.tex", timeout=30)
    assert not res.ok and any("did not find the tikz library 'external'" in e["message"] for e in res.errors)
