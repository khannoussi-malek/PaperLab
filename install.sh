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

main() {
  platform >/dev/null
}

[ -n "${PAPERLAB_INSTALL_LIB:-}" ] || main "$@"
