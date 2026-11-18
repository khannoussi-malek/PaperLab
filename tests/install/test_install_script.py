"""install.sh, the one-command macOS install, run with `sh` against fake system commands.

Run from the repository root: `backend/.venv/bin/pytest tests/install -q` (no database, so outside backend/tests,
whose conftest guards the database)."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "install.sh"
GiB = 1024**3

# Every outside command the script may call. Each fake logs "name args" and then runs its body (default: succeed).
FAKED = [
    "uname", "sw_vers", "sysctl", "curl", "docker", "hdiutil", "sudo", "open", "osascript", "pgrep", "ditto",
    "xattr", "sleep",
]


def make_bin(tmp_path: Path, bodies: dict[str, str]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in FAKED:
        if name in bodies and bodies[name] is None:  # None: the command doesn't exist on this Mac
            (bin_dir / name).unlink(missing_ok=True)
            continue
        fake = bin_dir / name
        fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "{name} $*" >> "$FAKE_LOG"\n{bodies.get(name, "")}\nexit 0\n')
        fake.chmod(0o755)
    return bin_dir


def env_for(tmp_path: Path, bodies: dict[str, str], **extra: str) -> dict[str, str]:
    bin_dir = make_bin(tmp_path, bodies)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "USER": "tester",
        "FAKE_LOG": str(tmp_path / "calls.log"),
        "PAPERLAB_LOG": str(tmp_path / "install.log"),
        "PAPERLAB_TTY": str(tmp_path / "tty"),
        "PAPERLAB_APPS_DIR": str(tmp_path / "Applications"),
        "PAPERLAB_DATA_DIR": str(tmp_path / "data"),
        "PAPERLAB_DOCKER_PATHS": "",
        **extra,
    }


def sh_fn(tmp_path: Path, expr: str, bodies: dict[str, str] | None = None, **extra: str):
    """Source install.sh as a library and run one expression."""
    env = env_for(tmp_path, bodies or {}, PAPERLAB_INSTALL_LIB="1", **extra)
    return subprocess.run(
        ["sh", "-c", f'. "{SCRIPT}"; {expr}'], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=30,
    )


def calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def test_pick_model_by_memory(tmp_path):
    assert sh_fn(tmp_path, f"pick_model {8 * GiB - 1}").stdout == ""
    assert sh_fn(tmp_path, f"pick_model {8 * GiB}").stdout.strip() == "qwen3:4b"
    assert sh_fn(tmp_path, f"pick_model {16 * GiB - 1}").stdout.strip() == "qwen3:4b"
    assert sh_fn(tmp_path, f"pick_model {16 * GiB}").stdout.strip() == "qwen3:8b"


def test_memory_bytes_reads_sysctl(tmp_path):
    result = sh_fn(tmp_path, "memory_bytes", {"sysctl": "echo 17179869184"})
    assert result.stdout.strip() == "17179869184"


def mac(arch: str, version: str) -> dict[str, str]:
    return {"uname": f'[ "$1" = -s ] && echo Darwin || echo {arch}', "sw_vers": f"echo {version}"}


def test_platform(tmp_path):
    assert sh_fn(tmp_path, "platform", mac("arm64", "14.5")).stdout.strip() == "mac-arm64"
    assert sh_fn(tmp_path, "platform", mac("x86_64", "13.0")).stdout.strip() == "mac-x64"


def test_platform_refuses_old_macos(tmp_path):
    old = sh_fn(tmp_path, "platform", mac("arm64", "12.7"))
    assert old.returncode == 1
    assert old.stdout.splitlines()[0] == "PaperLab needs macOS 13 or later."


def test_platform_refuses_other_systems(tmp_path):
    linux = sh_fn(tmp_path, "platform", {"uname": '[ "$1" = -s ] && echo Linux || echo x86_64'})
    assert linux.returncode == 1
    assert linux.stdout.splitlines()[0] == "This command installs PaperLab on a Mac. For other systems, see the README."


def test_latest_version_and_asset(tmp_path):
    headers = "HTTP/2 302\r\nlocation: https://github.com/khannoussi-malek/PaperLab/releases/tag/v0.3.1\r\n\r\n"
    got = sh_fn(tmp_path, "latest_version", {"curl": f"printf '{headers}'"})
    assert got.stdout.strip() == "0.3.1"
    assert sh_fn(tmp_path, "app_asset_url 0.3.1 mac-x64").stdout.strip() == (
        "https://github.com/khannoussi-malek/PaperLab/releases/download/v0.3.1/PaperLab-0.3.1-x64.dmg"
    )
    assert sh_fn(tmp_path, "app_asset_url 0.3.1 mac-arm64").stdout.strip().endswith("PaperLab-0.3.1-arm64.dmg")


def test_fail_prints_one_sentence_and_the_log_path(tmp_path):
    result = sh_fn(tmp_path, "run false || fail 'Docker did not start.'")
    assert result.returncode == 1
    assert result.stdout.splitlines() == ["Docker did not start.", f"Details: {tmp_path / 'install.log'}"]


def test_run_sends_output_to_the_log_not_the_screen(tmp_path):
    result = sh_fn(tmp_path, "run echo noisy; run sh -c 'echo loud >&2'")
    assert result.stdout == "" and result.stderr == ""
    assert "noisy" in (tmp_path / "install.log").read_text() and "loud" in (tmp_path / "install.log").read_text()


def test_truncated_script_runs_nothing(tmp_path):
    text = SCRIPT.read_text()
    env = env_for(tmp_path, {})
    for cut in (len(text) // 3, len(text) // 2, len(text) - 20):
        subprocess.run(["sh"], input=text[:cut], env=env, capture_output=True, text=True, timeout=30)
    assert calls(tmp_path) == []


def test_password_asked_once_with_the_reason(tmp_path):
    result = sh_fn(tmp_path, "ask_password")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["PaperLab needs your password once, to install Docker."]
    assert [c for c in calls(tmp_path) if c.startswith("sudo")] == ["sudo -v"]


def test_wrong_or_no_password_stops_with_a_sentence(tmp_path):
    result = sh_fn(tmp_path, "ask_password", {"sudo": "exit 1"})
    assert result.returncode == 1
    assert result.stdout.splitlines()[1] == "PaperLab can't install Docker without your password. Run the command again."
