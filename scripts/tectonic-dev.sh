#!/usr/bin/env bash
# Installs the pinned Tectonic into backend/.tools/ and warms its bundle cache, for the host tests marked `tectonic`.
# Re-run after adding a template to backend/app/manuscript_templates/. Prints the two exports the tests read.
set -euo pipefail
VERSION=0.17.0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/backend/.tools"
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) ASSET=tectonic-$VERSION-aarch64-apple-darwin; SHA=a3f1cac7c5678f01661a92212f58480ae3b0634115d880dbc59e2953ded45667 ;;
  Linux-x86_64) ASSET=tectonic-$VERSION-x86_64-unknown-linux-musl; SHA=8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7 ;;
  Linux-aarch64) ASSET=tectonic-$VERSION-aarch64-unknown-linux-musl; SHA=b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8 ;;
  *) echo "no pinned Tectonic for $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac
mkdir -p "$TOOLS/tectonic-cache"
printf '*\n' > "$TOOLS/.gitignore"
BIN="$TOOLS/tectonic"
if [ ! -x "$BIN" ]; then
  ARCHIVE="$TOOLS/$ASSET.tar.gz"
  curl -fsSL -o "$ARCHIVE" "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40$VERSION/$ASSET.tar.gz"
  GOT="$(shasum -a 256 "$ARCHIVE" | cut -d' ' -f1)"
  if [ "$GOT" != "$SHA" ]; then rm -f "$ARCHIVE"; echo "sha256 mismatch for $ASSET: $GOT" >&2; exit 1; fi
  tar -xzf "$ARCHIVE" -C "$TOOLS" tectonic
  rm -f "$ARCHIVE"
fi
export TECTONIC_CACHE_DIR="$TOOLS/tectonic-cache"
WARM="$(mktemp -d)"
trap 'rm -rf "$WARM"' EXIT
cat > "$WARM/natbib.tex" <<'TEX'
\documentclass{article}
\usepackage{natbib}
\begin{document}
Warm-up \citep{none}.
\bibliographystyle{plainnat}
\end{document}
TEX
(cd "$WARM" && "$BIN" -X compile natbib.tex >/dev/null)
for t in "$ROOT"/backend/app/manuscript_templates/*.tex; do
  [ -e "$t" ] || continue
  cp -R "$(dirname "$t")/." "$WARM/t/" 2>/dev/null || { mkdir -p "$WARM/t"; cp -R "$(dirname "$t")/." "$WARM/t/"; }
  (cd "$WARM/t" && "$BIN" -X compile "$(basename "$t")" >/dev/null) || echo "warm-up failed for $t" >&2
done
echo "export TECTONIC_BIN=$BIN"
echo "export TECTONIC_CACHE_DIR=$TOOLS/tectonic-cache"
