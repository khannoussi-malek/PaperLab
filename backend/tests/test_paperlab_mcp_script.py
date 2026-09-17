"""scripts/paperlab-mcp, the launcher MCP clients start on macOS, Linux and WSL, run with `sh` against a fake docker."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "paperlab-mcp"

# The api image holds only backend/, so there is no checkout around this file there.
pytestmark = pytest.mark.skipif(not (ROOT / "docker-compose.yml").exists(), reason="needs the repository checkout")

FAKE_DOCKER = """#!/bin/sh
printf '%s|%s\\n' "$(pwd)" "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "compose ps") printf '%s' "$FAKE_PS"; printf '%s' "$FAKE_PS_ERR" >&2; exit "${FAKE_PS_STATUS:-0}" ;;
  "compose exec") echo "the server's own output" ;;
esac
"""


def run_script(tmp_path: Path, **fake) -> tuple[subprocess.CompletedProcess, list[str]]:
    docker = tmp_path / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    log = tmp_path / "calls.log"
    env = {**os.environ, "PAPERLAB_DOCKER": str(docker), "FAKE_LOG": str(log), **fake}
    result = subprocess.run(
        ["sh", str(SCRIPT)], cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30
    )
    return result, log.read_text().splitlines() if log.exists() else []


def test_with_api_running_it_execs_the_server_in_the_api_container_from_the_repository_root(tmp_path):
    result, calls = run_script(tmp_path, FAKE_PS="db\nredis\napi\nworker\nfrontend\n")

    assert calls == [
        f"{ROOT}|compose ps --status running --services",
        f"{ROOT}|compose exec -T api python -m mcp_server",
    ]
    assert (result.returncode, result.stdout, result.stderr) == (0, "the server's own output\n", "")


def test_with_api_not_running_it_says_how_to_start_paperlab(tmp_path):
    result, calls = run_script(tmp_path, FAKE_PS="db\nredis\nworker\n")

    assert len(calls) == 1
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == f'paperlab-mcp: PaperLab isn\'t running. Start it with "docker compose up -d" in {ROOT}.\n'


def test_when_docker_refuses_access_it_names_the_docker_group(tmp_path):
    refused = "permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock"
    result, calls = run_script(tmp_path, FAKE_PS_ERR=refused, FAKE_PS_STATUS="1")

    assert len(calls) == 1
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == (
        "paperlab-mcp: Docker refused access (permission denied). On Linux, add your user to the docker group: "
        "sudo usermod -aG docker $USER, then log out and back in.\n"
    )


def test_when_docker_is_not_found_it_says_how_to_install_it(tmp_path):
    result = subprocess.run(
        ["sh", str(SCRIPT)],
        cwd=tmp_path,
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",  # Keep sh but no docker
            "PAPERLAB_DOCKER_PATHS": "",  # Disable the fallback paths
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == (
        "paperlab-mcp: docker was not found. Install Docker, or set PAPERLAB_DOCKER to its full path.\n"
    )


def test_the_script_is_executable_and_checked_out_with_lf_line_endings():
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    assert b"\r" not in SCRIPT.read_bytes()
    assert "scripts/paperlab-mcp text eol=lf" in (ROOT / ".gitattributes").read_text().splitlines()
