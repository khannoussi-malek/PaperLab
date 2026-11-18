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

OLLAMA=${OLLAMA_API:-http://127.0.0.1:11434}

ollama_ready() { run curl -fsS --max-time 5 "$OLLAMA/api/version"; }

# Wait until Ollama answers (up to a minute; PAPERLAB_OLLAMA_WAIT in tests).
wait_for_ollama() {
  waited=0
  until ollama_ready; do
    [ "$waited" -lt "${PAPERLAB_OLLAMA_WAIT:-60}" ] ||
      fail "Ollama didn't start. Open Ollama from Applications, then run the command again."
    sleep 2
    waited=$((waited + 2))
  done
}

install_ollama_mac() {
  tmp=$(mktemp -d)
  run curl -fsSL -o "$tmp/Ollama.dmg" "https://ollama.com/download/Ollama.dmg" ||
    fail "Couldn't download Ollama. Check the internet connection, then run the command again."
  run hdiutil attach -nobrowse -quiet -mountpoint "$tmp/mnt" "$tmp/Ollama.dmg" || fail "Couldn't open the Ollama download."
  run ditto "$tmp/mnt/Ollama.app" "$APPS/Ollama.app" ||
    { run hdiutil detach -quiet "$tmp/mnt"; fail "Couldn't copy Ollama to $APPS."; }
  run hdiutil detach -quiet "$tmp/mnt" || true
}

# An Ollama that answers is left alone (whatever installed it); an installed one is opened; otherwise it is installed.
ensure_ollama() {
  if ollama_ready; then
    step 2 "Ollama is ready"
    return 0
  elif [ -d "$APPS/Ollama.app" ]; then
    step 2 "Starting Ollama…"
  else
    step 2 "Installing Ollama…"
    install_ollama_mac
  fi
  run open -a Ollama || true
  wait_for_ollama
}

# The chat model through Ollama's API (no ollama command needed on PATH). Progress shows only on a terminal.
ensure_model() {
  if [ -z "$1" ]; then
    step 3 "Chat is left off"
    echo "This Mac has less than 8 GB of memory, so chat is left off. Reading, notes and search work; add chat later in Settings."
    return 0
  fi
  if curl -fsS --max-time 10 "$OLLAMA/api/tags" 2>>"$LOG" | grep -q "\"name\":\"$1\""; then
    step 3 "Chat model $1 is ready"
    return 0
  fi
  step 3 "Downloading the chat model $1…"
  stream=$(mktemp)
  curl -fsSN -X POST "$OLLAMA/api/pull" -d "{\"model\":\"$1\"}" 2>>"$LOG" | tee "$stream" | while IFS= read -r line; do
    total=$(printf '%s' "$line" | sed -n 's/.*"total":\([0-9]*\).*/\1/p')
    done_bytes=$(printf '%s' "$line" | sed -n 's/.*"completed":\([0-9]*\).*/\1/p')
    if [ -t 1 ] && [ -n "$total" ] && [ -n "$done_bytes" ] && [ "$total" -gt 0 ]; then
      printf '\r      %s%%' $((done_bytes * 100 / total))
    fi
  done
  if [ -t 1 ]; then printf '\n'; fi
  cat "$stream" >>"$LOG"
  grep -q '"status":"success"' "$stream" ||
    fail "Couldn't download the chat model. Check the internet connection, then run the command again."
}

main() {
  platform >/dev/null
}

[ -n "${PAPERLAB_INSTALL_LIB:-}" ] || main "$@"
