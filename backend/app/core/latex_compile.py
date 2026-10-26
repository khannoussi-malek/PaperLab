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
# Real Tectonic puts this in main.log, not on stderr; natbib words it "Package natbib Warning".
_CITATION = re.compile(
    r"^(?:LaTeX|Package \w+) Warning: (?P<message>Citation .* undefined) on input line (?P<line>\d+)\.$"
)
_ABSOLUTE = "accessing absolute path"


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    pdf: bytes | None
    log: str
    errors: list[dict]
    friendly: str | None


def parse_errors(log: str, main_file: str = "main.tex") -> list[dict]:
    out = []
    for raw in log.splitlines():
        line = raw.strip()
        m = _ERROR.match(line)
        if m:  # the generic "something bad happened" follow-ups carry no file or "!", so they never match
            out.append(_entry(m, "error"))
            continue
        m = _CITATION.match(line)
        if m:
            out.append(
                {"file": main_file, "line": int(m.group("line")), "message": m.group("message"), "kind": "warning"}
            )
    return out


def _entry(m: re.Match, kind: str) -> dict:
    line = m.groupdict().get("line")
    return {"file": m.group("file"), "line": int(line) if line else None, "message": m.group("message"), "kind": kind}


def friendly_message(log: str) -> str | None:
    if _ABSOLUTE in log:
        return "outside_file"
    if "this bundle isn't cached" in log:
        return "needs_download"
    if "Running external tool biber" in log:
        return "biber_unsupported"
    return None


def _clean_log(stderr: str, main_log: str) -> str:
    kept = [ln for ln in stderr.splitlines() if not ln.startswith("Fontconfig error")]
    return ("\n".join(kept) + "\n" + main_log)[:MAX_LOG]


def finish(
    returncode: int, stderr: str, main_log: str, pdf: bytes | None, main_file: str = "main.tex"
) -> CompileResult:
    """Turns a finished run into a result. An absolute-path read voids the PDF even at rc=0 (isolation layer 2)."""
    friendly = friendly_message(stderr)
    ok = returncode == 0 and pdf is not None and _ABSOLUTE not in stderr
    return CompileResult(
        ok=ok,
        pdf=pdf if ok else None,
        log=_clean_log(stderr, main_log),
        errors=parse_errors(stderr + "\n" + main_log, main_file),
        friendly=friendly,
    )


def _env(workdir: Path) -> dict[str, str]:
    """Only these reach Tectonic (isolation layer 1): none of the API's secrets or database URL."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(workdir), "LANG": "C.UTF-8"}
    if settings.tectonic_cache_dir:
        env["TECTONIC_CACHE_DIR"] = str(settings.tectonic_cache_dir)
    return env


def _ids(user: str) -> tuple[int, int]:
    import pwd

    entry = pwd.getpwnam(user)
    return entry.pw_uid, entry.pw_gid


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    os.chown(root, uid, gid)
    for p in root.rglob("*"):
        os.chown(p, uid, gid, follow_symlinks=False)


async def _spawn(argv: list[str], **kwargs):
    return await asyncio.create_subprocess_exec(*argv, **kwargs)


async def compile_dir(workdir: Path, main_file: str, *, timeout: float = COMPILE_TIMEOUT) -> CompileResult:
    parts = main_file.replace("\\", "/").split("/")
    if not main_file or main_file.startswith(("-", "/")) or "\\" in main_file or ".." in parts:
        raise ValueError(f"main_file must be a plain relative path: {main_file!r}")
    argv = [settings.tectonic_bin, "-X", "compile", main_file, "--untrusted", "--keep-logs", "--synctex"]
    if settings.tectonic_only_cached:
        argv.append("-C")
    extra = {}
    if settings.tectonic_user:  # isolation layer 3: the images run it as an account that can't read the app's files
        uid, gid = _ids(settings.tectonic_user)
        await asyncio.to_thread(_chown_tree, workdir, uid, gid)
        extra = {"user": uid, "group": gid, "extra_groups": []}  # drop root's gid 0 and supplementary groups
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
    except BaseException as exc:  # timeout, cancellation or anything else: never leave Tectonic running
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await asyncio.shield(proc.wait())
        if isinstance(exc, TimeoutError):
            return CompileResult(False, None, "", [], "compile_timeout")
        raise
    stem = Path(main_file).stem
    pdf_path, log_path = workdir / f"{stem}.pdf", workdir / f"{stem}.log"
    pdf = pdf_path.read_bytes() if pdf_path.exists() else None
    main_log = log_path.read_text(errors="replace") if log_path.exists() else ""
    return finish(proc.returncode, out.decode(errors="replace"), main_log, pdf, main_file)
