"""Checks that a manuscript can't read the app's code or the user's data through Tectonic (M27a isolation layer 3).

Run as root inside an image, with the worker's setting:
`TECTONIC_USER=tex python -m app.scripts.tectonic_sandbox_check`.
`absolute` is stopped by Tectonic's own absolute-path check (layer 2, `outside_file`); the relative probes are stopped
by the unprivileged `tex` user, and `relative-pdf-dir` also by the folder lock the worker applies before its first
compile (`_lock_pdf_dir`, which this script calls). Each probe compiles a manuscript that `\\verbatiminput`s a
file it must not see, and looks for that file's distinctive text in the PDF.
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
    finally:
        if pdf_secret is not None:
            pdf_secret.unlink(missing_ok=True)
        if secret_dir is not None:
            shutil.rmtree(secret_dir, ignore_errors=True)
    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
