"""Checks that a manuscript can't read the app's code or the user's data through Tectonic (M27a isolation layer 3).

Run as root inside an image, with the worker's setting:
`TECTONIC_USER=tex python -m app.scripts.tectonic_sandbox_check`.
`absolute` is stopped by Tectonic's own absolute-path check (layer 2, `outside_file`); the relative probes are stopped
by the unprivileged `tex` user, and `relative-pdf-dir` also by the folder lock the worker applies before its first
compile (`_lock_pdf_dir`, which this script calls). Each read probe compiles a manuscript that `\\verbatiminput`s a
file it must not see, and looks for that file's distinctive text in the PDF. Each write probe `\\openout`s a file it
must not write: into the package cache (a new file, and over a cached package another project loads), the app's code
and the PDF folder, where the file must not change; and `../` out of the workdir, where the compile must fail
(`outside_file`; /tmp itself is writable to anyone, and harmless).
Prints `probe <name>: blocked|LEAKED (<detail>)`; exit code 1 if any probe leaked.
"""

import asyncio
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pymupdf

from app.config import settings
from app.core.latex_compile import compile_dir
from app.workers.manuscripts import _lock_pdf_dir

CANARY = "SANDBOXCANARY7731"
CODE = Path("/src/app/config.py")
CODE_MARKER = "tectonic_user"  # a setting name that appears in config.py


def _text(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return re.sub(r"\s+", "", "".join(page.get_text() for page in doc))


async def _probe(workdir: Path, target: str, marker: str) -> tuple[bool, str]:
    """(leaked, detail) for a manuscript that prints `target`."""
    (workdir / "main.tex").write_text(
        "\\documentclass{article}\\usepackage{verbatim}\\begin{document}\n"
        f"\\verbatiminput{{{target}}}\n\\end{{document}}\n"
    )
    result = await compile_dir(workdir, "main.tex")
    if result.pdf is not None and marker in _text(result.pdf):
        return True, "its text is in the PDF"
    return False, "compile ok, text absent" if result.ok else f"compile failed: {result.friendly or 'see log'}"


def _write_tex(target: str) -> str:
    return (
        "\\documentclass{article}\\begin{document}\n"
        f"\\newwrite\\w\\immediate\\openout\\w={target}\\immediate\\write\\w{{{CANARY}}}\\immediate\\closeout\\w\n"
        "x\n\\end{document}\n"
    )


def _content(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


async def _write_probe(workdir: Path, target: str, *, must_fail: bool) -> tuple[bool, str]:
    """(leaked, detail) for a manuscript that writes CANARY to `target`. A protected file must not change; with
    `must_fail`, the compile must fail too."""
    path = Path(target) if target.startswith("/") else (workdir / target).resolve()
    before = _content(path)
    (workdir / "main.tex").write_text(_write_tex(target))
    result = await compile_dir(workdir, "main.tex")
    after = _content(path)
    changed = after != before and after is not None and CANARY.encode() in after
    if changed:  # undo it (root can), so a leak found here harms nothing
        path.unlink() if before is None else path.write_bytes(before)
    outcome = "compile ok" if result.ok else f"compile failed: {result.friendly or 'see log'}"
    detail = f"{outcome}, file {'WRITTEN' if changed else 'unchanged'}"
    return (result.ok if must_fail else changed), detail


def _cached_package() -> Path | None:
    """natbib.sty in Tectonic's cache, the file the final review's poisoning rewrote; every template loads it."""
    root = settings.tectonic_cache_dir
    return next(root.rglob("natbib.sty"), None) if root else None


async def main() -> int:
    leaked = False
    secret_dir = pdf_secret = None
    try:
        secret_dir = Path(tempfile.mkdtemp())  # outside every workdir
        secret = secret_dir / "root-only.txt"
        secret.write_text(CANARY)
        secret.chmod(0o600)
        settings.pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_secret = settings.pdf_dir / "sandbox-check.txt"
        pdf_secret.write_text(CANARY)  # default mode, like a real PDF: only the folder lock protects it
        _lock_pdf_dir()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "own.txt").write_text(CANARY)
            probes = [
                ("control", "own.txt", CANARY),  # readable, so it must show up, or the rest prove nothing
                ("absolute", str(secret), CANARY),
                ("relative-root-file", os.path.relpath(secret, work), CANARY),
                ("relative-app-code", os.path.relpath(CODE, work), CODE_MARKER),
                ("relative-pdf-dir", os.path.relpath(pdf_secret, work), CANARY),
            ]
            for name, target, marker in probes:
                hit, detail = await _probe(work, target, marker)
                if name == "control":
                    print(f"probe control: {'ok' if hit else 'BROKEN'} ({detail})")
                    leaked = leaked or not hit
                else:
                    print(f"probe {name}: {'LEAKED' if hit else 'blocked'} ({detail})")
                    leaked = leaked or hit
            cache = settings.tectonic_cache_dir
            package = _cached_package()
            writes = [
                ("write-cache-new", f"{cache}/sandbox-probe.sty" if cache else None, False),
                ("write-cache-package", str(package) if package else None, False),
                ("write-app-code", "/src/sandbox-probe.txt", False),
                ("write-pdf-dir", str(settings.pdf_dir / "sandbox-probe.txt"), False),
                ("write-parent", "../sandbox-probe.txt", True),
            ]
            for name, target, must_fail in writes:
                if target is None:
                    print(f"probe {name}: BROKEN (no Tectonic cache configured)")
                    leaked = True
                    continue
                hit, detail = await _write_probe(work, target, must_fail=must_fail)
                print(f"probe {name}: {'LEAKED' if hit else 'blocked'} ({detail})")
                leaked = leaked or hit
    finally:
        if pdf_secret is not None:
            pdf_secret.unlink(missing_ok=True)
        if secret_dir is not None:
            shutil.rmtree(secret_dir, ignore_errors=True)
    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
