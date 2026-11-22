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
    "xattr", "sleep", "codesign",
]
# Bodies every test gets unless it says otherwise: Docker's download is signed by Docker's team.
# ditto creates its target, as the real one does.
DEFAULT_BODIES = {
    "codesign": 'case "$1" in -dv) echo "TeamIdentifier=9BNSXJN65R" >&2 ;; esac',
    "ditto": 'mkdir -p "$2"',
}


def make_bin(tmp_path: Path, bodies: dict[str, str]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in FAKED:
        if name in bodies and bodies[name] is None:  # None: the command doesn't exist on this Mac
            (bin_dir / name).unlink(missing_ok=True)
            continue
        fake = bin_dir / name
        fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "{name} $*" >> "$FAKE_LOG"\n{bodies.get(name, DEFAULT_BODIES.get(name, ""))}\nexit 0\n')
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
        "PAPERLAB_OLLAMA_LINK": str(tmp_path / "usr-local-bin" / "ollama"),
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


# Docker counts as running once `open <Applications>/Docker.app` has run (it touches $tmp/docker-up).
DOCKER_UP = '[ "$1" = info ] && [ ! -f "$FAKE_STATE/docker-up" ] && exit 1'
OPEN = 'case "$*" in */Docker.app) touch "$FAKE_STATE/docker-up" ;; esac'
# Docker's installer: puts a docker command on PATH, as Docker Desktop's install does.
SUDO_INSTALLS_DOCKER = (
    'case "$*" in *Docker.app/Contents/MacOS/install*) '
    "printf '#!/bin/sh\\nprintf \"%%s\\\\n\" \"docker $*\" >> \"$FAKE_LOG\"\\n" + DOCKER_UP.replace('"', '\\"')
    + "\\nexit 0\\n' > \"$(dirname \"$0\")/docker\"; chmod +x \"$(dirname \"$0\")/docker\" ;; esac"
)


def docker_env(tmp_path: Path, tty: str | None = "\n\n") -> dict[str, str]:
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
    (tmp_path / "Applications" / "Docker.app").mkdir(parents=True)
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", {"docker": DOCKER_UP, "open": OPEN}, **docker_env(tmp_path))
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["[1/5] Starting Docker…"]
    assert f"open {tmp_path}/Applications/Docker.app" in calls(tmp_path)
    assert not any(c.startswith(("hdiutil", "sudo", "curl")) for c in calls(tmp_path))


def test_missing_docker_installs_in_order(tmp_path):
    bodies = {"docker": None, "open": OPEN, "sudo": SUDO_INSTALLS_DOCKER}
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", bodies, **docker_env(tmp_path))
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == ["[1/5] Installing Docker…", "PaperLab needs your password once, to install Docker."]
    order = [c.split()[0] if not c.startswith("sudo /") else "install" for c in calls(tmp_path)]
    # download, attach, signature, password, install, detach
    assert order[:7] == ["curl", "hdiutil", "codesign", "codesign", "sudo", "install", "hdiutil"]
    log = calls(tmp_path)
    assert any("desktop.docker.com/mac/main/arm64/Docker.dmg" in c for c in log)
    assert any(c.startswith("sudo ") and "--accept-license --user=tester" in c for c in log)
    assert f"open {tmp_path}/Applications/Docker.app" in log


def test_intel_mac_gets_the_amd64_docker(tmp_path):
    bodies = {"docker": None, "open": OPEN, "sudo": SUDO_INSTALLS_DOCKER}
    sh_fn(tmp_path, "ensure_docker mac-x64", bodies, **docker_env(tmp_path))
    assert any("desktop.docker.com/mac/main/amd64/Docker.dmg" in c for c in calls(tmp_path))


def test_without_a_terminal_it_stops_before_installing_anything(tmp_path):
    result = run_main(tmp_path, world(), tty=None)
    assert result.returncode == 1
    assert "PaperLab needs a terminal to ask before installing. Run the command in Terminal." in result.stdout
    assert not any(c.startswith(("hdiutil", "sudo", "ditto")) or "api/pull" in c for c in calls(tmp_path))


def test_stopping_at_the_plan_installs_nothing(tmp_path):
    result = run_main(tmp_path, world(), tty="")  # Ctrl+D / EOF instead of an answer
    assert result.returncode == 1
    assert not any(c.startswith(("hdiutil", "sudo", "ditto")) or "api/pull" in c for c in calls(tmp_path))


def test_docker_that_never_starts_fails_with_a_sentence(tmp_path):
    (tmp_path / "Applications" / "Docker.app").mkdir(parents=True)
    result = sh_fn(
        tmp_path, "ensure_docker mac-arm64", {"docker": "exit 1"}, PAPERLAB_DOCKER_WAIT="1", **docker_env(tmp_path)
    )
    assert result.returncode == 1
    assert (
        "Docker didn't start. Open Docker Desktop, finish its window, then run the command again." in result.stdout
    )


# Ollama's API through curl: /api/version answers once Ollama is "up", /api/tags lists $OLLAMA_TAGS, /api/pull streams
# $PULL_STREAM. `open <Applications>/Ollama.app` brings it up.
CURL_OLLAMA = r"""case "$*" in
  *api/version*) [ -f "$FAKE_STATE/ollama-up" ] || exit 7 ;;
  *api/tags*) printf '%s' "${OLLAMA_TAGS:-}" ;;
  *api/pull*) printf '%b' "$PULL_STREAM" ;;
esac"""
OPEN_OLLAMA = 'case "$*" in */Ollama.app) touch "$FAKE_STATE/ollama-up" ;; esac'
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
    assert steps[-1] == f"open {tmp_path}/Applications/Ollama.app"


def test_installed_but_stopped_ollama_is_opened_not_reinstalled(tmp_path):
    (tmp_path / "Applications" / "Ollama.app").mkdir(parents=True)
    result = sh_fn(tmp_path, "ensure_ollama", {"curl": CURL_OLLAMA, "open": OPEN_OLLAMA}, **ollama_env(tmp_path))
    assert result.stdout.splitlines() == ["[2/5] Starting Ollama…"]
    assert not any(c.startswith(("hdiutil", "ditto")) for c in calls(tmp_path))


def test_ollama_that_never_starts_fails_with_a_sentence(tmp_path):
    result = sh_fn(tmp_path, "ensure_ollama", {"curl": CURL_OLLAMA}, PAPERLAB_OLLAMA_WAIT="1", **ollama_env(tmp_path))
    assert result.returncode == 1
    assert "Ollama didn't start. Open Ollama from Applications, then run the command again." in result.stdout


# Ollama's first start asks for the password in a window of its own to link its `ollama` command, and its server
# doesn't answer until someone does (a clean-Mac run waited out the minute on that window).
def test_ollama_command_is_linked_in_the_terminal_before_ollama_first_opens(tmp_path):
    result = sh_fn(tmp_path, "ensure_ollama", {"curl": CURL_OLLAMA, "open": OPEN_OLLAMA}, **ollama_env(tmp_path))
    assert result.returncode == 0, result.stdout
    steps = calls(tmp_path)
    link = f"sudo ln -sf {tmp_path}/Applications/Ollama.app/Contents/Resources/ollama {tmp_path}/usr-local-bin/ollama"
    assert f"sudo mkdir -p {tmp_path}/usr-local-bin" in steps
    assert steps.index(link) < steps.index(f"open {tmp_path}/Applications/Ollama.app")


def test_existing_ollama_command_is_left_alone(tmp_path):
    link = tmp_path / "usr-local-bin" / "ollama"
    link.parent.mkdir()
    link.touch()
    (tmp_path / "Applications" / "Ollama.app").mkdir(parents=True)
    result = sh_fn(tmp_path, "ensure_ollama", {"curl": CURL_OLLAMA, "open": OPEN_OLLAMA}, **ollama_env(tmp_path))
    assert result.returncode == 0, result.stdout
    assert not any(c.startswith("sudo") for c in calls(tmp_path))


def test_refused_password_still_opens_ollama_and_says_where_it_will_ask(tmp_path):
    (tmp_path / "Applications" / "Ollama.app").mkdir(parents=True)
    bodies = {"curl": CURL_OLLAMA, "open": OPEN_OLLAMA, "sudo": "exit 1"}
    result = sh_fn(tmp_path, "ensure_ollama", bodies, **ollama_env(tmp_path))
    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines() == [
        "[2/5] Starting Ollama…",
        "PaperLab needs your password to set up Ollama.",
        "Ollama will ask for it in a window of its own instead; answer it there.",
    ]
    assert f"open {tmp_path}/Applications/Ollama.app" in calls(tmp_path)


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


def test_env_written_when_absent(tmp_path):
    sh_fn(tmp_path, "write_model_env qwen3:4b")
    assert (tmp_path / "data" / ".env").read_text() == "LLM_MODEL=qwen3:4b\n"


def test_existing_env_is_never_changed(tmp_path):
    env = tmp_path / "data" / ".env"
    env.parent.mkdir(parents=True)
    env.write_bytes(b"LLM_MODEL=llama3\nOTHER=1")
    sh_fn(tmp_path, "write_model_env qwen3:8b")
    assert env.read_bytes() == b"LLM_MODEL=llama3\nOTHER=1"


def test_no_env_without_a_model(tmp_path):
    sh_fn(tmp_path, 'write_model_env ""')
    assert not (tmp_path / "data" / ".env").exists()


# PaperLab is running until `osascript … quit` has run.
PGREP_RUNNING = '[ -f "$FAKE_STATE/quit" ] && exit 1'
OSASCRIPT_QUITS = 'touch "$FAKE_STATE/quit"'


def test_running_app_is_quit_before_it_is_replaced(tmp_path):
    bodies = {"pgrep": PGREP_RUNNING, "osascript": OSASCRIPT_QUITS}
    result = sh_fn(tmp_path, "install_app_mac 0.3.1 mac-arm64", bodies, **docker_env(tmp_path))
    assert result.returncode == 0, result.stdout
    assert "osascript -e quit app \"PaperLab\"" in calls(tmp_path)
    # Downloaded and copied first, so PaperLab is closed only for the swap.
    names = [c.split()[0] for c in calls(tmp_path)]
    assert names.index("ditto") < names.index("osascript")
    assert (tmp_path / "Applications" / "PaperLab.app").is_dir()
    assert not (tmp_path / "Applications" / "PaperLab.app.new").exists()


def test_app_that_is_not_running_is_not_quit(tmp_path):
    sh_fn(tmp_path, "install_app_mac 0.3.1 mac-arm64", {"pgrep": "exit 1"}, **docker_env(tmp_path))
    assert not any(c.startswith("osascript") for c in calls(tmp_path))


def test_app_downloaded_copied_and_quarantine_cleared(tmp_path):
    old = tmp_path / "Applications" / "PaperLab.app" / "old-file"
    old.parent.mkdir(parents=True)
    old.touch()
    result = sh_fn(tmp_path, "install_app_mac 0.3.1 mac-x64", {"pgrep": "exit 1"}, **docker_env(tmp_path))
    assert result.returncode == 0, result.stdout
    log = calls(tmp_path)
    assert any(c.startswith("curl") and c.endswith("/v0.3.1/PaperLab-0.3.1-x64.dmg") for c in log)
    app = f"{tmp_path}/Applications/PaperLab.app"
    assert any(c.startswith("ditto ") and c.endswith(f"PaperLab.app {app}.new") for c in log)
    assert f"xattr -dr com.apple.quarantine {app}" in log
    assert not old.exists()  # the old bundle is replaced, not merged into


def test_app_that_will_not_quit_stops_with_a_sentence(tmp_path):
    result = sh_fn(
        tmp_path, "install_app_mac 0.3.1 mac-arm64", {"pgrep": ""}, PAPERLAB_QUIT_WAIT="1", **docker_env(tmp_path)
    )
    assert result.returncode == 1
    assert "PaperLab is still open. Quit it, then run the command again." in result.stdout
    assert not (tmp_path / "Applications" / "PaperLab.app.new").exists()


# The whole outside world through curl: GitHub's latest-release redirect, the three downloads, Ollama's API and
# PaperLab's API. The app answers once `open <Applications>/PaperLab.app` has run.
CURL_WORLD = r"""case "$*" in
  *releases/latest*) printf 'HTTP/2 302\r\nlocation: https://github.com/khannoussi-malek/PaperLab/releases/tag/v0.3.1\r\n\r\n' ;;
  *api/version*) [ -f "$FAKE_STATE/ollama-up" ] || exit 7 ;;
  *api/tags*) printf '%s' "${OLLAMA_TAGS:-}" ;;
  *api/pull*) printf '%b' '{"status":"success"}\n' ;;
  *api/setup*) [ -f "$FAKE_STATE/app-up" ] || exit 7 ;;
  *api/embedding/model*) printf '%b' "$SEARCH_STREAM" ;;
  *api/embedding*) printf '{"model_present":%s}' "${MODEL_PRESENT:-false}" ;;
esac"""
OPEN_ANY = 'case "$*" in */Docker.app) touch "$FAKE_STATE/docker-up" ;; */Ollama.app) touch "$FAKE_STATE/ollama-up" ;; */PaperLab.app) touch "$FAKE_STATE/app-up" ;; esac'


def world(**overrides: str | None) -> dict[str, str | None]:
    return {
        **mac("arm64", "15.1"), "sysctl": f"echo {16 * GiB}", "curl": CURL_WORLD, "open": OPEN_ANY,
        "docker": None, "sudo": SUDO_INSTALLS_DOCKER, "pgrep": "exit 1", **overrides,
    }


SEARCH_DONE = r'event: progress\ndata: {"completed":1,"total":2}\n\nevent: done\ndata: {"papers_queued":0}\n\n'


def run_main(tmp_path: Path, bodies: dict, tty: str | None = "\n\n", **extra: str):
    env = env_for(tmp_path, bodies, **docker_env(tmp_path, tty), **{"SEARCH_STREAM": SEARCH_DONE, **extra})
    return subprocess.run(["sh", str(SCRIPT)], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


DOCKER_TERMS = (
    "Docker Desktop is free for personal use, education and companies under 250 employees and $10M revenue; "
    "larger companies need a paid Docker subscription. Starting accepts its terms."
)
PLAN_EMPTY_MAC = [
    "PaperLab runs on this Mac. Here is what it needs:",
    "  Docker Desktop  runs PaperLab's database and search in the background. Will install (about 550 MB).",
    "  PaperLab        the app itself. Will install (about 120 MB; its first start downloads about 335 MB more).",
    "",
    "PaperLab's chat needs a language model to answer questions about your papers. Where should it run?",
    "  1) On this Mac: free, and your papers and questions never leave it.",
    "     Ollama runs the model. Will install (about 220 MB).",
    "     The model, qwen3:8b. Will download (about 5.2 GB).",
    "  2) A cloud service you have an API key for (OpenAI, Anthropic, …): nothing more to download.",
    "     You paste the key in PaperLab when it opens, never in this window.",
]


def test_full_install_on_an_empty_mac(tmp_path):
    result = run_main(tmp_path, world())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        *PLAN_EMPTY_MAC,
        "Choose 1 or 2 [1]: ",
        DOCKER_TERMS,
        "Your Mac's password is asked once, to install Docker and set up Ollama.",
        "Press Enter to start, or Ctrl+C to stop.",
        "[1/5] Installing Docker…",
        "PaperLab needs your password once, to install Docker.",
        "[2/5] Installing Ollama…",
        "[3/5] Downloading the chat model qwen3:8b…",
        "[4/5] Installing PaperLab 0.3.1…",
        "[5/5] Opening PaperLab (the first start downloads about 335 MB)…",
        "PaperLab is ready. Next time, open it from Applications.",
    ]
    assert (tmp_path / "data" / ".env").read_text() == "LLM_MODEL=qwen3:8b\n"
    last = calls(tmp_path)[-1]
    assert last.startswith("curl") and "-X PUT" in last and '{"done": true}' in last and last.endswith("/api/setup")


# sudo forgets the password after 5 minutes, and Docker's start plus Ollama's download can take longer: Ollama's
# command is linked while Docker's password is still fresh, so the plan's "asked once" holds.
def test_ollama_command_is_linked_right_after_dockers_installer(tmp_path):
    result = run_main(tmp_path, world())
    assert result.returncode == 0, result.stdout + result.stderr
    log = calls(tmp_path)
    docker_installer = next(i for i, c in enumerate(log) if "--accept-license" in c)
    link = next(i for i, c in enumerate(log) if c.startswith("sudo ln -sf"))
    assert docker_installer < link < log.index(f"open {tmp_path}/Applications/Docker.app")


def test_cloud_choice_skips_ollama_and_leaves_the_chat_step_open(tmp_path):
    result = run_main(tmp_path, world(), tty="2\n\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        *PLAN_EMPTY_MAC,
        "Choose 1 or 2 [1]: ",
        DOCKER_TERMS,
        "Your Mac's password is asked once, to install Docker.",
        "Press Enter to start, or Ctrl+C to stop.",
        "[1/5] Installing Docker…",
        "PaperLab needs your password once, to install Docker.",
        "[2/5] Ollama isn't needed: chat will use your cloud service",
        "[3/5] No chat model to download",
        "[4/5] Installing PaperLab 0.3.1…",
        "[5/5] Opening PaperLab (the first start downloads about 335 MB)…",
        "PaperLab is open on its chat step: add your cloud service and its API key there.",
    ]
    log = calls(tmp_path)
    assert not any("Ollama" in c or "api/pull" in c for c in log)
    assert not any("-X PUT" in c and "api/setup" in c for c in log)  # setup stays open on the chat step
    assert any("api/embedding/model" in c for c in log)  # search is still set up
    assert not (tmp_path / "data" / ".env").exists()


def test_an_answer_other_than_1_or_2_is_asked_again(tmp_path):
    result = run_main(tmp_path, world(), tty="3\n2\n\n")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert "Choose 1 or 2 [1]: Type 1 or 2." in lines
    assert "[2/5] Ollama isn't needed: chat will use your cloud service" in lines


def test_low_memory_offers_only_a_cloud_service(tmp_path):
    result = run_main(tmp_path, world(sysctl=f"echo {4 * GiB}"), tty="\n")  # only the Enter to start
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[4:7] == [
        "PaperLab's chat needs a language model to answer questions about your papers. This Mac has less than 8 GB of",
        "memory, too little to run one well, so chat can use a cloud service you have an API key for (OpenAI, Anthropic,",
        "…). You paste the key in PaperLab when it opens, or skip chat there.",
    ]
    assert not any(line.startswith("Choose") for line in lines)
    assert "[2/5] Ollama isn't needed: chat will use your cloud service" in lines
    assert not any("Ollama" in c or "api/pull" in c for c in calls(tmp_path))


# macOS's /bin/sh in a UTF-8 Terminal (the default) reads "$version…" as a variable named version plus the first byte
# of "…", which `set -u` stops on (a clean-Mac run died at step 4).
def test_full_install_in_a_utf8_terminal(tmp_path):
    result = run_main(tmp_path, world(), LC_ALL="en_US.UTF-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[4/5] Installing PaperLab 0.3.1…" in result.stdout.splitlines()


def test_rerun_with_everything_installed_only_updates_the_app(tmp_path):
    env_file = tmp_path / "data" / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("LLM_MODEL=llama3\n")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "ollama-up").touch()
    tags = '{"models":[{"name":"qwen3:8b"}]}'
    result = run_main(tmp_path, world(docker=""), OLLAMA_TAGS=tags, MODEL_PRESENT="true")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "PaperLab runs on this Mac. Here is what it needs:",
        "  Docker Desktop  runs PaperLab's database and search in the background. Already here.",
        "  PaperLab        the app itself. Will install (about 120 MB; its first start downloads about 335 MB more).",
        "",
        "PaperLab's chat needs a language model to answer questions about your papers. Where should it run?",
        "  1) On this Mac: free, and your papers and questions never leave it.",
        "     Ollama runs the model. Already here.",
        "     The model, qwen3:8b. Already here.",
        "  2) A cloud service you have an API key for (OpenAI, Anthropic, …): nothing more to download.",
        "     You paste the key in PaperLab when it opens, never in this window.",
        "Choose 1 or 2 [1]: ",
        "Press Enter to start, or Ctrl+C to stop.",
        "[1/5] Docker is ready",
        "[2/5] Ollama is ready",
        "[3/5] Chat model qwen3:8b is ready",
        "[4/5] Installing PaperLab 0.3.1…",
        "[5/5] Opening PaperLab (the first start downloads about 335 MB)…",
        "PaperLab is ready. Next time, open it from Applications.",
    ]
    log = calls(tmp_path)
    assert not any(c.startswith("sudo") for c in log)
    assert not any("Docker.dmg" in c or "Ollama.dmg" in c or "api/pull" in c or "embedding/model" in c for c in log)
    assert any(c.endswith("PaperLab-0.3.1-arm64.dmg") for c in log)
    assert env_file.read_text() == "LLM_MODEL=llama3\n"


def test_plan_says_an_installed_paperlab_will_be_updated(tmp_path):
    (tmp_path / "Applications" / "PaperLab.app").mkdir(parents=True)
    result = run_main(tmp_path, world())
    assert "  PaperLab        the app itself. Will update to the latest version." in result.stdout.splitlines()


def test_search_download_error_fails_and_leaves_setup_open(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "ollama-up").touch()
    stream = r'event: error\ndata: {"detail":"disk full"}\n\n'
    result = run_main(tmp_path, world(docker=""), OLLAMA_TAGS='{"models":[{"name":"qwen3:8b"}]}', SEARCH_STREAM=stream)
    assert result.returncode == 1
    assert "Couldn't download the search model. Open PaperLab and use Settings → Search to try again." in result.stdout
    assert not any("-X PUT" in c for c in calls(tmp_path))


def test_app_that_never_answers_fails_with_a_sentence(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "ollama-up").touch()
    bodies = world(docker="", open="")  # opening PaperLab never brings its API up
    result = run_main(tmp_path, bodies, OLLAMA_TAGS='{"models":[{"name":"qwen3:8b"}]}', PAPERLAB_APP_WAIT="1")
    assert result.returncode == 1
    assert "PaperLab didn't start. Open it from Applications; if it shows a problem, it says what to do." in result.stdout


def test_unsupported_system_says_so_from_main(tmp_path):
    result = run_main(tmp_path, world(**mac("arm64", "12.6")))
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == "PaperLab needs macOS 13 or later."
    assert not any(c.startswith(("curl", "hdiutil", "sudo")) for c in calls(tmp_path))


def test_app_port_comes_from_the_apps_settings(tmp_path):
    settings = tmp_path / "data" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{\n  "keepRunning": true,\n  "port": 5299,\n  "updatesEnabled": true\n}\n')
    assert sh_fn(tmp_path, "api_base").stdout.strip() == "http://127.0.0.1:5299"
    settings.unlink()
    assert sh_fn(tmp_path, "api_base").stdout.strip() == "http://127.0.0.1:5190"


def test_docker_installer_signed_by_someone_else_is_not_run(tmp_path):
    bodies = {
        "docker": None, "open": OPEN, "sudo": SUDO_INSTALLS_DOCKER,
        "codesign": 'case "$1" in -dv) echo "TeamIdentifier=EVIL123" >&2 ;; esac',
    }
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", bodies, **docker_env(tmp_path))
    assert result.returncode == 1
    assert "The Docker download isn't signed by Docker, so it wasn't installed. Run the command again." in result.stdout
    log = calls(tmp_path)
    assert not any(c.startswith("sudo") for c in log)  # neither the password nor the installer
    assert log[-1].startswith("hdiutil detach")


def test_downloads_give_up_on_a_stalled_connection(tmp_path):
    bodies = {"docker": None, "open": OPEN, "sudo": SUDO_INSTALLS_DOCKER, "pgrep": "exit 1"}
    sh_fn(tmp_path, "ensure_docker mac-arm64; install_ollama_mac; install_app_mac 0.3.1 mac-arm64", bodies, **docker_env(tmp_path))
    downloads = [c for c in calls(tmp_path) if c.startswith("curl") and " -o " in c]
    assert len(downloads) == 3
    assert all("--retry 3" in c and "--speed-time 60 --speed-limit 1" in c for c in downloads)


def test_stopped_docker_without_docker_desktop_says_start_it(tmp_path):
    result = sh_fn(tmp_path, "ensure_docker mac-arm64", {"docker": DOCKER_UP, "open": OPEN}, **docker_env(tmp_path))
    assert result.returncode == 1
    assert "Your Docker isn't running. Start it, then run the command again." in result.stdout
    assert not any("Docker.app" in c and c.startswith("open") for c in calls(tmp_path))


def old_app(tmp_path: Path) -> Path:
    marker = tmp_path / "Applications" / "PaperLab.app" / "old-file"
    marker.parent.mkdir(parents=True)
    marker.touch()
    return marker


def test_failed_download_leaves_the_running_app_alone(tmp_path):
    marker = old_app(tmp_path)
    bodies = {"pgrep": PGREP_RUNNING, "osascript": OSASCRIPT_QUITS, "curl": 'case "$*" in *PaperLab-*) exit 22 ;; esac'}
    result = sh_fn(tmp_path, "install_app_mac 0.3.1 mac-arm64", bodies, **docker_env(tmp_path))
    assert result.returncode == 1
    assert not any(c.startswith("osascript") for c in calls(tmp_path))
    assert marker.exists()


def test_failed_copy_keeps_the_old_app(tmp_path):
    marker = old_app(tmp_path)
    result = sh_fn(tmp_path, "install_app_mac 0.3.1 mac-arm64", {"pgrep": "exit 1", "ditto": "exit 1"}, **docker_env(tmp_path))
    assert result.returncode == 1
    assert marker.exists()


def test_unwritable_data_folder_fails_with_a_sentence(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    result = sh_fn(tmp_path, "write_model_env qwen3:4b", PAPERLAB_DATA_DIR=str(blocker / "data"))
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == f"Couldn't save PaperLab's settings in {blocker / 'data'}."


def test_no_temporary_folder_fails_with_a_sentence(tmp_path):
    result = sh_fn(tmp_path, "install_app_mac 0.3.1 mac-arm64", {"pgrep": "exit 1"}, TMPDIR=str(tmp_path / "missing"))
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == "Couldn't make a temporary folder for the downloads."


def test_downloads_are_removed_after_install(tmp_path):
    scratch = tmp_path / "t"
    scratch.mkdir()
    bodies = {"docker": None, "open": OPEN, "sudo": SUDO_INSTALLS_DOCKER, "pgrep": "exit 1"}
    expr = "ensure_docker mac-arm64; install_ollama_mac; install_app_mac 0.3.1 mac-arm64"
    result = sh_fn(tmp_path, expr, bodies, TMPDIR=str(scratch), **docker_env(tmp_path))
    assert result.returncode == 0, result.stdout
    assert list(scratch.iterdir()) == []
