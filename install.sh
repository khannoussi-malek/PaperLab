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

# A temporary file or folder under $TMPDIR (macOS's mktemp ignores TMPDIR without a template).
scratch() { mktemp "$@" "${TMPDIR:-/tmp}/paperlab.XXXXXX" 2>>"$LOG"; }

# Download <url> as <name>.dmg and mount it at $tmp/mnt. A connection that stalls for a minute is retried, then
# given up on, instead of hanging forever.
open_dmg() {
  tmp=$(scratch -d) || fail "Couldn't make a temporary folder for the downloads."
  run curl -fsSL --retry 3 --speed-time 60 --speed-limit 1 -o "$tmp/$2.dmg" "$1" ||
    { rm -rf "$tmp"; fail "Couldn't download $2. Check the internet connection, then run the command again."; }
  run hdiutil attach -nobrowse -quiet -mountpoint "$tmp/mnt" "$tmp/$2.dmg" ||
    { rm -rf "$tmp"; fail "Couldn't open the $2 download. Run the command again."; }
}

# Unmount it and delete the download (Docker's is about 600 MB).
close_dmg() {
  run hdiutil detach -quiet "$tmp/mnt" || true
  rm -rf "$tmp"
}

# Docker's installer runs as root, so it must be Docker's: a valid signature from Docker Inc's team.
signed_by_docker() {
  run codesign --verify --deep --strict "$1" && codesign -dv "$1" 2>&1 | grep -q '^TeamIdentifier=9BNSXJN65R$'
}

# Download first, then the password, then Docker's own silent installer.
install_docker_mac() {
  case $1 in mac-arm64) arch=arm64 ;; *) arch=amd64 ;; esac
  open_dmg "https://desktop.docker.com/mac/main/$arch/Docker.dmg" Docker
  signed_by_docker "$tmp/mnt/Docker.app" ||
    { close_dmg; fail "The Docker download isn't signed by Docker, so it wasn't installed. Run the command again."; }
  ask_password
  run sudo "$tmp/mnt/Docker.app/Contents/MacOS/install" --accept-license --user="$USER" ||
    { close_dmg; fail "Docker's installer stopped. Run the command again."; }
  close_dmg
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
  elif [ -d "$APPS/Docker.app" ]; then
    step 1 "Starting Docker…"
    start_docker_mac
  elif [ -n "$(find_docker)" ]; then
    # Another Docker (Colima, OrbStack, Rancher…): the user knows how to start it; installing a second one would not help.
    fail "Your Docker isn't running. Start it, then run the command again."
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
  open_dmg "https://ollama.com/download/Ollama.dmg" Ollama
  run ditto "$tmp/mnt/Ollama.app" "$APPS/Ollama.app" ||
    { close_dmg; fail "Couldn't copy Ollama to $APPS. Run the command again."; }
  close_dmg
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
  stream=$(scratch) || fail "Couldn't make a temporary folder for the downloads."
  curl -fsSN -X POST "$OLLAMA/api/pull" -d "{\"model\":\"$1\"}" 2>>"$LOG" | tee "$stream" | while IFS= read -r line; do
    total=$(printf '%s' "$line" | sed -n 's/.*"total":\([0-9]*\).*/\1/p')
    done_bytes=$(printf '%s' "$line" | sed -n 's/.*"completed":\([0-9]*\).*/\1/p')
    if [ -t 1 ] && [ -n "$total" ] && [ -n "$done_bytes" ] && [ "$total" -gt 0 ]; then
      printf '\r      %s%%' $((done_bytes * 100 / total))
    fi
  done
  if [ -t 1 ]; then printf '\n'; fi
  cat "$stream" >>"$LOG"
  pulled=yes
  grep -q '"status":"success"' "$stream" || pulled=no
  rm -f "$stream"
  [ "$pulled" = yes ] ||
    fail "Couldn't download the chat model. Check the internet connection, then run the command again."
}

DATA=${PAPERLAB_DATA_DIR:-$HOME/Library/Application Support/PaperLab}

# Quitting PaperLab stops its containers the normal way; the library (Docker volumes) is never touched.
quit_app_mac() {
  pgrep -x PaperLab >/dev/null 2>&1 || return 0
  run osascript -e 'quit app "PaperLab"' || true
  waited=0
  while pgrep -x PaperLab >/dev/null 2>&1; do
    [ "$waited" -lt "${PAPERLAB_QUIT_WAIT:-60}" ] || return 1
    sleep 2
    waited=$((waited + 2))
  done
}

# The release's .dmg, swapped in for any older PaperLab only once the new one is fully copied: a failed download or
# copy leaves the old app in place (and still running). Fetched by curl, it carries no quarantine flag; clearing it
# anyway keeps macOS from asking "are you sure you want to open it?".
install_app_mac() {
  open_dmg "$(app_asset_url "$1" "$2")" PaperLab
  new="$APPS/PaperLab.app.new"
  rm -rf "$new"
  run ditto "$tmp/mnt/PaperLab.app" "$new" ||
    { rm -rf "$new"; close_dmg; fail "Couldn't copy PaperLab to $APPS. Run the command again."; }
  close_dmg
  quit_app_mac || { rm -rf "$new"; fail "PaperLab is still open. Quit it, then run the command again."; }
  rm -rf "$APPS/PaperLab.app"
  mv "$new" "$APPS/PaperLab.app" || fail "Couldn't put PaperLab in $APPS. Run the command again."
  run xattr -dr com.apple.quarantine "$APPS/PaperLab.app" || true
}

# The chat model the backend seeds its first connection with (LLM_MODEL). Only on a first install: an existing .env
# is the user's.
write_model_env() {
  [ -n "$1" ] && [ ! -e "$DATA/.env" ] || return 0
  { mkdir -p "$DATA" && printf 'LLM_MODEL=%s\n' "$1" >"$DATA/.env"; } 2>>"$LOG" ||
    fail "Couldn't save PaperLab's settings in $DATA."
}

# PaperLab's API: the port the app's own settings name (Settings → Desktop app can change it), else 5190.
api_base() {
  if [ -n "${PAPERLAB_API:-}" ]; then
    echo "$PAPERLAB_API"
    return 0
  fi
  port=$(sed -n 's/.*"port": *\([0-9][0-9]*\).*/\1/p' "$DATA/settings.json" 2>/dev/null | head -n 1)
  echo "http://127.0.0.1:${port:-5190}"
}

# Open PaperLab and wait for its API (up to 15 minutes: the first start downloads its images; PAPERLAB_APP_WAIT in
# tests).
wait_for_app() {
  run open -a PaperLab || true
  waited=0
  until run curl -fsS --max-time 5 "$(api_base)/api/setup"; do
    [ "$waited" -lt "${PAPERLAB_APP_WAIT:-900}" ] ||
      fail "PaperLab didn't start. Open it from Applications; if it shows a problem, it says what to do."
    sleep 3
    waited=$((waited + 3))
  done
}

# The built-in search model, through the same API as the setup page's Search step (a server-sent event stream).
ensure_search_model() {
  if curl -fsS --max-time 10 "$(api_base)/api/embedding" 2>>"$LOG" | grep -q '"model_present": *true'; then
    return 0
  fi
  stream=$(scratch) || fail "Couldn't make a temporary folder for the downloads."
  curl -fsSN -X POST "$(api_base)/api/embedding/model" 2>>"$LOG" | tee "$stream" | while IFS= read -r line; do
    case $line in
      data:*'"total"'*)
        total=$(printf '%s' "$line" | sed -n 's/.*"total": *\([0-9]*\).*/\1/p')
        done_bytes=$(printf '%s' "$line" | sed -n 's/.*"completed": *\([0-9]*\).*/\1/p')
        if [ -t 1 ] && [ -n "$total" ] && [ -n "$done_bytes" ] && [ "$total" -gt 0 ]; then
          printf '\r      search model %s%%' $((done_bytes * 100 / total))
        fi
        ;;
    esac
  done
  if [ -t 1 ]; then printf '\n'; fi
  cat "$stream" >>"$LOG"
  fetched=yes
  grep -q '^event: done' "$stream" || fetched=no
  rm -f "$stream"
  [ "$fetched" = yes ] ||
    fail "Couldn't download the search model. Open PaperLab and use Settings → Search to try again."
}

# The setup page has nothing left to ask, so it doesn't open.
finish_setup() {
  run curl -fsS -X PUT -H 'Content-Type: application/json' -d '{"done": true}' "$(api_base)/api/setup" ||
    fail "PaperLab is installed, but couldn't finish its setup. Open it from Applications to finish there."
}

main() {
  # $(…) runs in a subshell, so a refusal's message is printed here.
  plat=$(platform) || { printf '%s\n' "$plat"; exit 1; }
  model=$(pick_model "$(memory_bytes)")
  ensure_docker "$plat"
  ensure_ollama
  ensure_model "$model"
  version=$(latest_version)
  [ -n "$version" ] || fail "Couldn't find PaperLab's latest release. Check the internet connection, then run the command again."
  step 4 "Installing PaperLab $version…"
  install_app_mac "$version" "$plat"
  write_model_env "$model"
  step 5 "Opening PaperLab (the first start downloads about 335 MB)…"
  wait_for_app
  ensure_search_model
  finish_setup
  echo "PaperLab is ready. Next time, open it from Applications."
}

[ -n "${PAPERLAB_INSTALL_LIB:-}" ] || main "$@"
