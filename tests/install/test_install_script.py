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


# Docker counts as running once `open -a Docker` has run (it touches $tmp/docker-up).
DOCKER_UP = '[ "$1" = info ] && [ ! -f "$FAKE_STATE/docker-up" ] && exit 1'
OPEN = 'case "$*" in "-a Docker") touch "$FAKE_STATE/docker-up" ;; esac'
# Docker's installer: puts a docker command on PATH, as Docker Desktop's install does.
SUDO_INSTALLS_DOCKER = (
    'case "$*" in *Docker.app/Contents/MacOS/install*) '
    "printf '#!/bin/sh\\nprintf \"%%s\\\\n\" \"docker $*\" >> \"$FAKE_LOG\"\\n" + DOCKER_UP.replace('"', '\\"')
    + "\\nexit 0\\n' > \"$(dirname \"$0\")/docker\"; chmod +x \"$(dirname \"$0\")/docker\" ;; esac"
)


def docker_env(tmp_path: Path, tty: str | None = "\n") -> dict[str, str]:
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    if tty is not None:
        (tmp_path / "tty").write_text(tty)
    return {"FAKE_STATE": str(state)}


def test_working_docker_is_left_alone(tmp_path):
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", {"docker": ""}, **docker_env(tmp_path))
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["[1/5] Docker is ready"]
    assert [c.split()[0] for c in calls(tmp_path)] == ["docker"]  # docker info, nothing else


def test_installed_but_stopped_docker_is_started_not_reinstalled(tmp_path):
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", {"docker": DOCKER_UP, "open": OPEN}, **docker_env(tmp_path))
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["[1/5] Starting Docker…"]
    assert "open -a Docker" in calls(tmp_path)
    assert not any(c.startswith(("hdiutil", "sudo", "curl")) for c in calls(tmp_path))


def test_missing_docker_shows_licence_then_installs_in_order(tmp_path):
    bodies = {"docker": None, "open": OPEN, "sudo": SUDO_INSTALLS_DOCKER}
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", bodies, **docker_env(tmp_path))
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [
        "[1/5] Installing Docker…",
        "Docker Desktop is free for personal use, education and companies under 250 employees and $10M revenue; "
        "larger companies need a paid Docker subscription.",
        "Press Enter to accept Docker's terms and continue, or Ctrl+C to stop.",
        "PaperLab needs your password once, to install Docker.",
    ]
    order = [c.split()[0] if not c.startswith("sudo /") else "install" for c in calls(tmp_path)]
    assert order[:5] == ["curl", "hdiutil", "sudo", "install", "hdiutil"]  # download, attach, sudo -v, install, detach
    log = calls(tmp_path)
    assert any("desktop.docker.com/mac/main/arm64/Docker.dmg" in c for c in log)
    assert any(c.startswith("sudo ") and "--accept-license --user=tester" in c for c in log)
    assert "open -a Docker" in log


def test_intel_mac_gets_the_amd64_docker(tmp_path):
    bodies = {"docker": None, "open": OPEN, "sudo": SUDO_INSTALLS_DOCKER}
    sh_fn(tmp_path, "ensure_docker mac-x64", bodies, **docker_env(tmp_path))
    assert any("desktop.docker.com/mac/main/amd64/Docker.dmg" in c for c in calls(tmp_path))


def test_without_a_terminal_it_stops_before_installing_docker(tmp_path):
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", {"docker": None}, **docker_env(tmp_path, tty=None))
    assert result.returncode == 1
    assert "PaperLab needs a terminal to ask about Docker's terms. Run the command in Terminal." in result.stdout
    assert not any(c.startswith(("hdiutil", "sudo", "curl")) for c in calls(tmp_path))


def test_refusing_the_terms_installs_nothing(tmp_path):
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", {"docker": None}, **docker_env(tmp_path, tty=""))  # EOF
    assert result.returncode == 1
    assert not any(c.startswith(("hdiutil", "sudo", "curl")) for c in calls(tmp_path))


def test_docker_that_never_starts_fails_with_a_sentence(tmp_path):
    result = sh_fn(
        tmp_path, "ensure_docker mac-arm64", {"docker": "exit 1"}, PAPERLAB_DOCKER_WAIT="1", **docker_env(tmp_path)
    )
    assert result.returncode == 1
    assert (
        "Docker didn't start. Open Docker Desktop, finish its window, then run the command again." in result.stdout
    )


# Ollama's API through curl: /api/version answers once Ollama is "up", /api/tags lists $OLLAMA_TAGS, /api/pull streams
# $PULL_STREAM. `open -a Ollama` brings it up.
CURL_OLLAMA = r"""case "$*" in
  *api/version*) [ -f "$FAKE_STATE/ollama-up" ] || exit 7 ;;
  *api/tags*) printf '%s' "${OLLAMA_TAGS:-}" ;;
  *api/pull*) printf '%b' "$PULL_STREAM" ;;
esac"""
OPEN_OLLAMA = 'case "$*" in "-a Ollama") touch "$FAKE_STATE/ollama-up" ;; esac'
PULLED = r'{"status":"pulling manifest"}\n{"status":"pulling abc","total":100,"completed":50}\n{"status":"success"}\n'


def ollama_env(tmp_path: Path, up: bool = False, **extra: str) -> dict[str, str]:
    env = docker_env(tmp_path)
    if up:
        (tmp_path / "state" / "ollama-up").touch()
    return {**env, **extra}


def test_running_ollama_is_left_alone(tmp_path):
    result = sh_fn(tmp_path, "ensure_ollama", {"curl": CURL_OLLAMA}, **ollama_env(tmp_path, up=True))
    assert result.stdout.splitlines() == ["[2/5] Ollama is ready"]
    assert all("api/version" in c for c in calls(tmp_path))


def test_missing_ollama_is_installed_and_opened(tmp_path):
    bodies = {"curl": CURL_OLLAMA, "open": OPEN_OLLAMA}
    result = sh_fn(tmp_path, "ensure_ollama", bodies, **ollama_env(tmp_path))
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == ["[2/5] Installing Ollama…"]
    steps = [c for c in calls(tmp_path) if "api/version" not in c]
    assert "https://ollama.com/download/Ollama.dmg" in steps[0]
    assert steps[1].startswith("hdiutil attach")
    assert steps[2].startswith("ditto ") and steps[2].endswith(f"Ollama.app {tmp_path}/Applications/Ollama.app")
    assert steps[3].startswith("hdiutil detach")
    assert steps[4] == "open -a Ollama"


def test_installed_but_stopped_ollama_is_opened_not_reinstalled(tmp_path):
    (tmp_path / "Applications" / "Ollama.app").mkdir(parents=True)
    result = sh_fn(tmp_path, "ensure_ollama", {"curl": CURL_OLLAMA, "open": OPEN_OLLAMA}, **ollama_env(tmp_path))
    assert result.stdout.splitlines() == ["[2/5] Starting Ollama…"]
    assert not any(c.startswith(("hdiutil", "ditto")) for c in calls(tmp_path))


def test_ollama_that_never_starts_fails_with_a_sentence(tmp_path):
    result = sh_fn(tmp_path, "ensure_ollama", {"curl": CURL_OLLAMA}, PAPERLAB_OLLAMA_WAIT="1", **ollama_env(tmp_path))
    assert result.returncode == 1
    assert "Ollama didn't start. Open Ollama from Applications, then run the command again." in result.stdout


def test_model_already_pulled_is_skipped(tmp_path):
    tags = '{"models":[{"name":"qwen3:4b","model":"qwen3:4b"}]}'
    result = sh_fn(tmp_path, "ensure_model qwen3:4b", {"curl": CURL_OLLAMA}, **ollama_env(tmp_path, True, OLLAMA_TAGS=tags))
    assert result.stdout.splitlines() == ["[3/5] Chat model qwen3:4b is ready"]
    assert not any("api/pull" in c for c in calls(tmp_path))


def test_model_is_pulled_through_the_api(tmp_path):
    result = sh_fn(
        tmp_path, "ensure_model qwen3:8b", {"curl": CURL_OLLAMA}, **ollama_env(tmp_path, True, PULL_STREAM=PULLED)
    )
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == ["[3/5] Downloading the chat model qwen3:8b…"]
    pull = [c for c in calls(tmp_path) if "api/pull" in c]
    assert len(pull) == 1 and '{"model":"qwen3:8b"}' in pull[0]


def test_pull_error_fails_with_a_sentence(tmp_path):
    stream = r'{"status":"pulling manifest"}\n{"error":"connection reset"}\n'
    result = sh_fn(tmp_path, "ensure_model qwen3:8b", {"curl": CURL_OLLAMA}, **ollama_env(tmp_path, True, PULL_STREAM=stream))
    assert result.returncode == 1
    assert "Couldn't download the chat model. Check the internet connection, then run the command again." in result.stdout


def test_low_memory_skips_chat_with_the_sentence(tmp_path):
    result = sh_fn(tmp_path, 'ensure_model ""', {"curl": CURL_OLLAMA}, **ollama_env(tmp_path, True))
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "[3/5] Chat is left off",
        "This Mac has less than 8 GB of memory, so chat is left off. Reading, notes and search work; "
        "add chat later in Settings.",
    ]
    assert calls(tmp_path) == []
