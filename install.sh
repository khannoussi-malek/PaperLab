#!/bin/sh
# PaperLab's one-command install for macOS:
#   curl -fsSL https://raw.githubusercontent.com/khannoussi-malek/PaperLab/main/install.sh | sh
# It installs what's missing (Docker Desktop, Ollama, a chat model, PaperLab), leaves what already works alone, and
# opens PaperLab ready to use. Running it again updates PaperLab. Details go to ~/paperlab-install.log.
#
# Everything is in functions and `main` is the last line, so a download cut off halfway runs nothing.
# Tests source it with PAPERLAB_INSTALL_LIB=1 and fake system commands (tests/install/).
set -eu

REPO=khannoussi-malek/PaperLab
LOG=${PAPERLAB_LOG:-$HOME/paperlab-install.log}
GIB=1073741824

# One step line on the screen.
step() { printf '[%s/5] %s\n' "$1" "$2"; }

# A command whose output only the log sees.
run() { "$@" >>"$LOG" 2>&1; }

# One plain sentence, where to read more, and stop.
fail() {
  printf '%s\nDetails: %s\n' "$1" "$LOG"
  exit 1
}

# mac-arm64 or mac-x64; anything else stops here.
platform() {
  [ "$(uname -s)" = Darwin ] || fail "This command installs PaperLab on a Mac. For other systems, see the README."
  major=$(sw_vers -productVersion | cut -d. -f1)
  [ "$major" -ge 13 ] || fail "PaperLab needs macOS 13 or later."
  case $(uname -m) in
    arm64) echo mac-arm64 ;;
    x86_64) echo mac-x64 ;;
    *) fail "PaperLab runs on Apple silicon and Intel Macs only." ;;
  esac
}

memory_bytes() { sysctl -n hw.memsize; }

# The chat model this much memory runs well: none under 8 GB, the small one under 16 GB.
pick_model() {
  if [ "$1" -lt $((8 * GIB)) ]; then
    return 0
  elif [ "$1" -lt $((16 * GIB)) ]; then
    echo qwen3:4b
  else
    echo qwen3:8b
  fi
}

# The latest release's number, from where /releases/latest redirects (no API call, so no rate limit).
latest_version() {
  curl -fsSI "https://github.com/$REPO/releases/latest" | tr -d '\r' |
    sed -n 's|^[Ll]ocation: .*/releases/tag/v\(.*\)$|\1|p'
}

app_asset_url() {
  arch=${2#mac-}
  echo "https://github.com/$REPO/releases/download/v$1/PaperLab-$1-$arch.dmg"
}

# Only Docker's own installer needs admin rights (Ollama and PaperLab go into /Applications without them), so this
# runs just before it and needs no keep-alive. sudo reads the password from the terminal even under `curl | sh`.
ask_password() {
  echo "PaperLab needs your password once, to install Docker."
  sudo -v || fail "PaperLab can't install Docker without your password. Run the command again."
}

APPS=${PAPERLAB_APPS_DIR:-/Applications}

# Where a Mac's docker command may be. Apps started outside a shell don't get its PATH. The list and its order match
# scripts/paperlab-mcp; PAPERLAB_DOCKER_PATHS replaces them (tests; empty for none).
find_docker() {
  fallbacks=${PAPERLAB_DOCKER_PATHS-"$HOME/.docker/bin/docker $HOME/.rd/bin/docker /usr/local/bin/docker /opt/homebrew/bin/docker /usr/bin/docker $HOME/.orbstack/bin/docker /Applications/Docker.app/Contents/Resources/bin/docker"}
  for candidate in "$(command -v docker || true)" $fallbacks; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
}

docker_ready() {
  bin=$(find_docker)
  [ -n "$bin" ] && run "$bin" info
}

# Docker Desktop's terms, shown before anything is accepted for the user. Enter comes from the terminal: under
# `curl | sh` the script itself is standard input.
accept_docker_licence() {
  echo "Docker Desktop is free for personal use, education and companies under 250 employees and \$10M revenue; larger companies need a paid Docker subscription."
  echo "Press Enter to accept Docker's terms and continue, or Ctrl+C to stop."
  { read -r _ <"${PAPERLAB_TTY:-/dev/tty}"; } 2>/dev/null ||
    fail "PaperLab needs a terminal to ask about Docker's terms. Run the command in Terminal."
}

# Download first, then the password, then Docker's own silent installer.
install_docker_mac() {
  case $1 in mac-arm64) arch=arm64 ;; *) arch=amd64 ;; esac
  tmp=$(mktemp -d)
  run curl -fsSL -o "$tmp/Docker.dmg" "https://desktop.docker.com/mac/main/$arch/Docker.dmg" ||
    fail "Couldn't download Docker. Check the internet connection, then run the command again."
  run hdiutil attach -nobrowse -quiet -mountpoint "$tmp/mnt" "$tmp/Docker.dmg" || fail "Couldn't open the Docker download."
  ask_password
  run sudo "$tmp/mnt/Docker.app/Contents/MacOS/install" --accept-license --user="$USER" ||
    { run hdiutil detach -quiet "$tmp/mnt"; fail "Docker's installer stopped."; }
  run hdiutil detach -quiet "$tmp/mnt" || true
}

# Open Docker and wait until it answers (up to 5 minutes; PAPERLAB_DOCKER_WAIT in tests).
start_docker_mac() {
  run open -a Docker || true
  waited=0
  until docker_ready; do
    [ "$waited" -lt "${PAPERLAB_DOCKER_WAIT:-300}" ] ||
      fail "Docker didn't start. Open Docker Desktop, finish its window, then run the command again."
    sleep 3
    waited=$((waited + 3))
  done
}

# A Docker that answers is left alone; an installed one is started; otherwise Docker Desktop is installed.
ensure_docker() {
  if docker_ready; then
    step 1 "Docker is ready"
  elif [ -n "$(find_docker)" ] || [ -d "$APPS/Docker.app" ]; then
    step 1 "Starting Docker…"
    start_docker_mac
  else
    step 1 "Installing Docker…"
    accept_docker_licence
    install_docker_mac "$1"
    start_docker_mac
  fi
}

main() {
  platform >/dev/null
}

[ -n "${PAPERLAB_INSTALL_LIB:-}" ] || main "$@"
