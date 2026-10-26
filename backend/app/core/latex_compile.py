"""Runs Tectonic on a manuscript folder and reads what it says (M27a). No fastapi here."""

import asyncio
import os
import re
import signal
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

COMPILE_TIMEOUT = 60
MAX_LOG = 200 * 1024

_ERROR = re.compile(r"^error: (?:(?P<file>[^\s:]+):(?P<line>\d+): |!)(?P<message>.+)$")
_WARNING = re.compile(r"^warning: (?P<file>[^\s:]+):(?P<line>\d+): (?P<message>Citation .*undefined.*)$")


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    pdf: bytes | None
    log: str
    errors: list[dict]
    friendly: str | None


def parse_errors(log: str) -> list[dict]:
    out = []
    for raw in log.splitlines():
        line = raw.strip()
        m = _ERROR.match(line)
        if m:  # the generic "something bad happened" follow-ups carry no file or "!", so they never match
            out.append(_entry(m, "error"))
            continue
        m = _WARNING.match(line)
        if m:
            out.append(_entry(m, "warning"))
    return out


def _entry(m: re.Match, kind: str) -> dict:
    line = m.groupdict().get("line")
    return {"file": m.group("file"), "line": int(line) if line else None, "message": m.group("message"), "kind": kind}


def friendly_message(log: str) -> str | None:
    if "this bundle isn't cached" in log:
        return "needs_download"
    if "Running external tool biber" in log:
        return "biber_unsupported"
    if "accessing absolute path" in log:
        return "outside_file"
    return None


def _clean_log(stderr: str, main_log: str) -> str:
    kept = [ln for ln in stderr.splitlines() if not ln.startswith("Fontconfig error")]
    return ("\n".join(kept) + "\n" + main_log)[:MAX_LOG]


def finish(returncode: int, stderr: str, main_log: str, pdf: bytes | None) -> CompileResult:
    """Turns a finished run into a result. An absolute-path read voids the PDF even at rc=0 (isolation layer 2)."""
    friendly = friendly_message(stderr)
    ok = returncode == 0 and pdf is not None and friendly != "outside_file"
    return CompileResult(
        ok=ok,
        pdf=pdf if ok else None,
        log=_clean_log(stderr, main_log),
        errors=parse_errors(stderr),
        friendly=friendly,
    )


def _env(workdir: Path) -> dict[str, str]:
    """Only these reach Tectonic (isolation layer 1): none of the API's secrets or database URL."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(workdir), "LANG": "C.UTF-8"}
    if settings.tectonic_cache_dir:
        env["TECTONIC_CACHE_DIR"] = str(settings.tectonic_cache_dir)
    return env


def _chown_tree(root: Path, user: str) -> None:
    import pwd

    uid = pwd.getpwnam(user).pw_uid
    os.chown(root, uid, -1)
    for p in root.rglob("*"):
        os.chown(p, uid, -1, follow_symlinks=False)


async def _spawn(argv: list[str], **kwargs):
    return await asyncio.create_subprocess_exec(*argv, **kwargs)


async def compile_dir(workdir: Path, main_file: str, *, timeout: float = COMPILE_TIMEOUT) -> CompileResult:
    argv = [settings.tectonic_bin, "-X", "compile", main_file, "--untrusted", "--keep-logs", "--synctex"]
    if settings.tectonic_only_cached:
        argv.append("-C")
    extra = {}
    if settings.tectonic_user:  # isolation layer 3: the images run it as an account that can't read the app's files
        await asyncio.to_thread(_chown_tree, workdir, settings.tectonic_user)
        extra["user"] = settings.tectonic_user
    proc = await _spawn(
        argv,
        cwd=workdir,
        env=_env(workdir),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
        **extra,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()
        return CompileResult(False, None, "", [], "compile_timeout")
    stem = Path(main_file).stem
    pdf_path, log_path = workdir / f"{stem}.pdf", workdir / f"{stem}.log"
    pdf = pdf_path.read_bytes() if pdf_path.exists() else None
    main_log = log_path.read_text(errors="replace") if log_path.exists() else ""
    return finish(proc.returncode, out.decode(errors="replace"), main_log, pdf)
